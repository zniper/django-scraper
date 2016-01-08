import uuid
import os
import simplejson as json

from datetime import datetime
from os.path import join
from jsonfield.fields import JSONField
from shutil import rmtree
from itertools import chain

from django.db import models
from django.db.models.signals import pre_delete
from django.utils.log import getLogger
from django.utils.translation import ugettext_lazy as _
from django.core.files.storage import default_storage as storage
from django.dispatch.dispatcher import receiver

from .config import (DATA_TYPES, PROTOCOLS, INDEX_JSON, COMPRESS_RESULT,
                     TEMP_DIR, NO_TASK_PREFIX)
from .base import BaseCrawl, ExtractorMixin
from .utils import (
    SimpleArchive, Datum, Data, write_storage_file, move_to_storage,
    download_batch)
from .signals import post_scrape


logger = getLogger('scraper')


class Collector(ExtractorMixin, models.Model):
    """This could be a single site or part of a site which contains wanted
    content"""
    name = models.CharField(max_length=256)
    selectors = models.ManyToManyField('Selector', blank=True)
    get_image = models.BooleanField(
        default=True,
        help_text='Download images found inside extracted content')
    # Dict of replacing rules (regex & new value):
    #    replace_rules = [('\<ul\>.*?\<ul\>', ''), ...]
    replace_rules = JSONField(
        help_text='List of Regex rules will be applied to refine data')
    # Extra settings
    black_words = models.CharField(max_length=256, blank=True, null=True)

    def __unicode__(self):
        return u'Collector: {0}'.format(self.name)

    def get_page(self, **kwargs):
        return Datum(content=self.extractor._html)

    def get_links(self, **kwargs):
        return Datum(content=self.extractor.extract_links())

    def get_article(self, **kwargs):
        return Datum(content=self.extractor.extract_article())

    def get_content(self, explore=None, **kwargs):
        """ Extract content of a page specified by URL, using linked selectors
        Args:
            explore - A dict, for retrieving inclusive target and expand links
                {'target': ['//a'], 'expand': ['//div/a']}
        Returns:
            Datum object
        """
        data, result_path = self.extractor.extract_content(
            get_image=self.get_image,
            selectors=self.selector_dict,
            replace_rules=self.replace_rules,
        )
        if not os.path.exists(result_path):
            os.makedirs(result_path)
        with open(join(result_path, INDEX_JSON), 'w') as index_file:
            index_file.write(json.dumps(data))
        extras = {'path': result_path}
        if explore:
            # In case of having exploring rules, additional information
            # like other target/expand links will also be collected
            for rule in explore.keys():
                extras[rule] = []
                for link in self.extractor.extract_links(explore[rule]):
                    extras[rule].append(link['url'])
            extras['uuid'] = self.extractor._uuid
        data.update(extras)
        return Datum(**data)

    @property
    def selector_dict(self):
        """Convert the self.selectors into dict of XPaths"""
        data_xpaths = {}
        for sel in self.selectors.all():
            data_xpaths[sel.key] = (sel.xpath, sel.data_type)
        return data_xpaths


class Spider(ExtractorMixin, BaseCrawl):
    """ This does work of collecting wanted pages' address, it will auto jump
    to another page and continue finding."""
    name = models.CharField(max_length=256, blank=True, null=True)
    crawl_root = models.BooleanField(
        _('Extract data from starting page'), default=False)
    # Link to different pages, all are XPath
    target_links = JSONField(help_text='XPaths toward links to pages with content \
        to be extracted')
    expand_links = JSONField(help_text='List of links (as XPaths) to other pages \
        holding target links (will not be extracted)')
    crawl_depth = models.PositiveIntegerField(default=1, help_text='Set this > 1 \
        in case of crawling from this page')
    collectors = models.ManyToManyField(
        Collector, blank=True, related_name='spider')

    depths = None
    crawl_links = None
    _task = None
    _work = None

    def operate(self, operations, task_id=None):
        """Performs all given operations on spider URL
        Args:
            operations - [
                {'action': 'get', 'target': 'content'},
                {'action': 'get', 'target': 'links'}
                ...
                ]
            task_id - Will be generated if missing
        Returns: Result object
        """
        self._set_extractor()
        has_files = False
        self._task = task_id
        data = Data(url=self.url, uuid=self.extractor._uuid, task_id=task_id)
        for operation in operations:
            datum = self._perform(**operation)
            data.add_result(datum)
            if 'path' in datum.extras and not has_files:
                has_files = True
        result = create_result(data.dict, self._task)
        if has_files:
            result.other = self._finalize(data)
            result.save()
        return result

    def _perform(self, action, target, **kwargs):
        """Perform operation based on given parameters. At the moment, only
        one collector is supported"""
        if action == 'get':
            operator = self.collectors.first()
            operator.extractor = self.extractor
        else:
            operator = self
        method = getattr(operator, action+'_'+target)
        data = method(**kwargs)
        data.extras['action'] = action
        data.extras['target'] = target
        # Content extracting needs some more refinements
        post_scrape.send(self.__class__, result=data.json)
        return data

    def _set_extractor(self, force=False):
        if force or self._extractor is None:
            self.extractor = self._new_extractor(self.url)
        return self.extractor

    def crawl_content(self, **kwargs):
        """ Extract all found links then scrape those pages
        Arguments:
        Returns:
            (result, path) - Result and path to collected content (dir or ZIP)
        """
        logger.info('[{0}] START CRAWLING: {1}'.format(
            self._task, self.url))

        # Collect all target links from level 0
        self.depths = {'target': {}, 'expand': {}}
        self.crawl_links = {'target': [], 'expand': []}
        if self.crawl_root:
            self.crawl_links['target'].append(self.url)
            self.depths['target'][self.url] = 0
        self.aggregate_links(self.get_links(self.extractor), 1)
        logger.info('Found: {0} targets, {1} expansions'.format(
            len(self.crawl_links['target']), len(self.crawl_links['expand'])))

        combined_json = {}
        result_paths = []
        page_sources = {}
        while self.crawl_links['target'] or self.crawl_links['expand']:
            # Perform bulk download
            page_sources.update(download_batch(
                self.crawl_links['target'] + self.crawl_links['expand']))

            # Collect data and links from targeted links
            while self.crawl_links['target']:
                url = self.crawl_links['target'].pop()
                data = self.process_target(url, page_sources[url])
                data_id = data.extras['uuid']
                single_content = {
                    'content': data.content,
                    'url': data.extras['url']
                }
                combined_json[data_id] = single_content
                result_paths.append(data.extras['path'])
            # ... and only links from expand links
            while self.crawl_links['expand']:
                url = self.crawl_links['expand'].pop()
                depth = self.depths['expand'][url]
                # Is this redundant check?
                if depth >= self.crawl_depth:
                    continue
                # Only extract target & expand links, so collector is not
                # necessary
                extr = self._new_extractor(url, page_sources[url])
                self.aggregate_links(self.get_links(extr), depth + 1)

        # Create the aggregated Result
        extras = {'path': result_paths}
        return Datum(content=combined_json, **extras)

    def _finalize(self, data):
        """Should be called at final step in operate(). This finalizes and
        move collected data to storage if having files downloaded"""
        crawl_id = self.extractor._uuid
        logger.info('[{0}] Finalizing result [{1}]'.format(
            self._task, crawl_id))

        data_paths = []
        for datum in data.results:
            if 'path' in datum.get('extras', {}):
                data_paths.extend(datum['extras']['path'])
        if COMPRESS_RESULT:
            archive = SimpleArchive(
                crawl_id + '.zip',
                join(TEMP_DIR, self.storage_location))
            archive.write(INDEX_JSON, data.json)
            # Collect all content files from operations
            # Move those dirs into spider dir
            for d_path in data_paths:
                d_id = os.path.basename(d_path)
                for item in os.listdir(d_path):
                    archive.write(join(d_id, item),
                                  open(join(d_path, item), 'r').read())
            storage_path = archive.move_to_storage(
                storage, self.storage_location)
        else:
            storage_path = join(self.storage_location, crawl_id)
            write_storage_file(
                storage, join(storage_path, 'index.json'), data.json)
            for d_path in data_paths:
                move_to_storage(storage, d_path, storage_path)

        # Assign LocalContent object
        local_content = LocalContent(url=self.url, local_path=storage_path)
        local_content.save()

        for path in data_paths:
            try:
                rmtree(path)
            except OSError:
                logger.info('Unable to remove temp dir: {0}'.format(path))
        logger.info('[{0}] Result location: {1}'.format(
            self._task, storage_path))
        return local_content

    def process_target(self, url, source=''):
        """ Perform collecting data in specific target url
        Args:
            content - source of the target page
        Returns: JSON of collected data
            {
                'content':
                'extras': {
                    'path':
                    'target':
                    'expand':
                },
                ...
            }
        """
        collector = self.collectors.first()
        collector.extractor = self._new_extractor(url, source)
        data = collector.get_content(explore={
            'target': self.target_links,
            'expand': self.expand_links
        })
        # Handle the extracted links (target & expand). Bind those  with the
        # depth if still in limit
        data.extras['url'] = url
        extras = data.extras
        depth = self.depths['target'][url]
        if depth < self.crawl_depth:
            self.aggregate_links({'target': extras['target']}, depth+1)
            if depth < self.crawl_depth - 1:
                self.aggregate_links({'expand': extras['expand']}, depth+1)
        return data

    def aggregate_links(self, links, depth):
        """ Aggregate given links (with target & expand) into
        self.craw_links """
        for key in links:
            if key == 'expand' and depth == self.crawl_depth:
                continue
            for url in links[key]:
                if url in self.depths[key] and self.depths[key][url] <= depth:
                    continue
                self.crawl_links[key].append(url)
                self.depths[key][url] = depth

    def get_links(self, extractor):
        """ Return target and expand links of current extractor """
        links = {}
        for key in ('target', 'expand'):
            urls = [_['url'] for _ in extractor.extract_links(
                xpaths=getattr(self, key+'_links'))]
            links[key] = urls
        return links

    def __unicode__(self):
        return 'Spider: {0}'.format(self.name)


class Selector(models.Model):
    """docstring for DataElement"""
    key = models.SlugField()
    xpath = models.CharField(max_length=512)
    data_type = models.CharField(max_length=64, choices=DATA_TYPES)

    def __unicode__(self):
        return u'Selector: {0}'.format(self.key)


class Result(models.Model):
    """ This model holds specific ouput information processed by Source.
    It is implemented for better adapts when called by queuing system. """
    task_id = models.CharField(max_length=64, blank=True, null=True)
    data = JSONField()
    other = models.ForeignKey('LocalContent', blank=True, null=True,
                              on_delete=models.SET_NULL)

    def __unicode__(self):
        return u'Task Result <{0}>'.format(self.task_id)

    def get_data(self, clean=False):
        """Return self.data. If clean is True, only data content will be
        returned (time, url, ID,... will be excluded)."""
        if clean:
            content = []
            for result in self.data['results']:
                action = result['extras']['action']
                res_content = result['content']
                if action == 'crawl':
                    items = [v['content'] for v in res_content.values()]
                else:
                    items = res_content
                content.extend(items)
            return content
        return self.data


def create_result(data, task_id=None, local_content=None):
    """ This will create and return the Result object. It binds with a task ID
    if provided.
    Arguments:
        data - Result data as dict or string value
        task_id - (optional) ID of related task
        local_content - (optional) related local content object
    """
    # If no task_id (from queuing system) provided, new unique ID
    # with prefix will be generated and used
    if task_id is None:
        duplicated = True
        while duplicated:
            task_id = NO_TASK_PREFIX + str(uuid.uuid4())
            if not Result.objects.filter(task_id=task_id).exists():
                break
    res = Result(task_id=task_id, data=data)
    if local_content:
        res.other = local_content
    res.save()
    return res


class LocalContent(models.Model):
    """ Store scrapped content in local, this could be used to prevent
        redownloading
    """
    url = models.CharField(max_length=256)
    local_path = models.CharField(max_length=256)
    created_time = models.DateTimeField(
        default=datetime.now, blank=True, null=True)
    state = models.IntegerField(default=0)

    def __unicode__(self):
        return u'Content (at {0}) of: {1}'.format(self.created_time, self.url)

    def remove_files(self):
        """Remove all files in storage of this LocalContent instance"""
        self.fresh = False
        if not storage.exists(self.local_path):
            return
        try:
            if os.path.isdir(self.local_path):
                dirs, files = storage.listdir(self.local_path)
                for fn in files:
                    storage.delete(join(self.local_path, fn))
            else:
                storage.delete(self.local_path)
        except OSError:
            logger.error('Error when deleting: {0}'.format(
                self.local_path))
        self.local_path = ''
        self.state = 1
        self.save()


class UserAgent(models.Model):
    """ Define a specific user agent for being used in Source """
    name = models.CharField(_('UA Name'), max_length=64)
    value = models.CharField(_('User Agent String'), max_length=256)

    def __unicode__(self):
        return u'User Agent: %s' % self.name


class ProxyServer(models.Model):
    """ Stores information of proxy server """
    name = models.CharField(_('Proxy Server Name'), max_length=64)
    address = models.CharField(_('Address'), max_length=128)
    port = models.IntegerField(_('Port'))
    protocol = models.CharField(_('Protocol'), choices=PROTOCOLS,
                                max_length=16)

    def get_dict(self):
        return {self.protocol: '%s://%s:%d' % (
            self.protocol, self.address, self.port)}

    def __unicode__(self):
        return u'Proxy Server: %s' % self.name


# TODO it will be best if these below could be placed into separate module


@receiver(pre_delete, sender=LocalContent)
def clear_local_files(sender, instance, *args, **kwargs):
    """Ensure all files saved into media dir will be deleted as well"""
    instance.remove_files()


@receiver(pre_delete, sender=Result)
def remove_result(sender, **kwargs):
    """Ensure all related local content will be deleted"""
    result = kwargs['instance']
    if result.other:
        result.other.delete()
