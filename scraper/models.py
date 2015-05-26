import uuid
import os

from datetime import datetime
from os.path import join
from jsonfield.fields import JSONField
from shutil import rmtree

from django.db import models
from django.db.models.signals import pre_delete
from django.utils.log import getLogger
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from django.core.files.storage import default_storage as storage
from django.dispatch.dispatcher import receiver

import base

from .config import DATA_TYPES, PROTOCOLS, COMPRESS_RESULT, INDEX_JSON
from .signals import post_crawl, post_scrape
from .utils import (
    SimpleArchive, JSONResult, write_storage_file, move_to_storage)


logger = getLogger('scraper')


class Collector(base.BaseCrawl):
    """This could be a single site or part of a site which contains wanted
    content"""
    # Basic infomation
    name = models.CharField(max_length=256)
    selectors = models.ManyToManyField('Selector', blank=True)
    get_image = models.BooleanField(
        default=True,
        help_text='Download images found inside extracted content')
    # Dict of replacing rules (regex & new value):
    #    replace_rules = [('\<ul\>.*?\<ul\>', ''), ...]
    replace_rules = JSONField(
        default={},
        help_text='List of Regex rules will be applied to refine data')
    # Extra settings
    black_words = models.CharField(max_length=256, blank=True, null=True)

    def __unicode__(self):
        return u'Collector: {0}'.format(self.name)

    def get_page(self, url, task_id=None):
        res = JSONResult(action='get_page', url=url, task_id=task_id)
        extractor = self.get_extractor(url)
        res.content = extractor._html
        result = create_result(res.dict, task_id)
        post_scrape.send(self.__class__, result=result)
        return result

    def get_links(self, url, task_id=None):
        res = JSONResult(action='get_links', url=url, task_id=task_id)
        extractor = self.get_extractor(url)
        res.content = extractor.extract_links(unique=False)
        result = create_result(res.dict, task_id)
        post_scrape.send(self.__class__, result=result)
        return result

    def get_content(self, url, task_id=None, spider=None):
        """ Download the content of a page specified by URL.
        Arguments:
            url - Address of the page to be processed
            task_id - ID of the (Celery) task
            spider - Work independently or under spider
        Returns:
            (result, path) - Result and path to collected content
                If crawl=False: result is content dictionary
                If crawl=True: result is a Result object
        """
        jres = JSONResult(action='get_content', url=url, task_id=task_id)
        logger.info('Scraping: %s' % url)

        # Determine local files location. It musts be unique by collector.
        extractor = self.get_extractor(url)

        # Extract content from target pages, so target_xpaths and
        # expand_xpaths are redundant
        data, result_path = extractor.extract_content(
            get_image=self.get_image,
            selectors=self.selector_dict,
            replace_rules=self.replace_rules,
        )
        jres.update(**data)

        # Write index.json file
        if not os.path.exists(result_path):
            os.makedirs(result_path)
        with open(join(result_path, INDEX_JSON), 'w') as index_file:
            index_file.write(jres.json)

        op_result = jres.dict
        extras = {}
        if not spider:
            # Run independently: create LocalContent and Result objects
            final_path = self.finalize_result(result_path)
            content = LocalContent(url=url, local_path=final_path)
            content.save()
            create_result(op_result, task_id, content)
            extras['path'] = final_path
        else:
            # In case of running under spider, additional information
            # like other target/expand links will also be collected
            extras.update({'target': [], 'expand': []})
            for link_type in ('target', 'expand'):
                xpaths = getattr(spider, link_type + '_links')
                for link in extractor.extract_links(xpaths, True):
                    extras[link_type].append(link['url'])
            logger.info('Found links: {0} targets, {1} expansions'.format(
                len(extras['target']), len(extras['expand'])))
            extras['path'] = result_path

        op_result['extras'] = extras
        post_scrape.send(self.__class__, result=op_result['id'])
        return op_result

    def finalize_result(self, result_path):
        """ Compress and move the result to location in default storage """
        result_id = os.path.basename(result_path)
        logger.info('Finalizing result [{0}]'.format(result_id))

        # Compress result if needed, then move it to storage
        local_path = ''
        if COMPRESS_RESULT:
            archive = SimpleArchive(result_path + '.zip')
            for item in os.listdir(result_path):
                archive.write(
                    item, open(join(result_path, item), 'r').read())
            archive.finish()
            local_path = archive.move_to_storage(
                storage, self.storage_location)
        else:
            local_path = join(self.storage_location, result_id)
            for item in os.listdir(result_path):
                write_storage_file(
                    storage, join(local_path, item),
                    open(join(result_path, item), 'r').read())
        try:
            rmtree(result_path)
        except OSError:
            pass

        logger.info('Result location: {0}'.format(result_path))
        return local_path

    @property
    def selector_dict(self):
        """Convert the self.selectors into dict of XPaths"""
        data_xpaths = {}
        for sel in self.selectors.all():
            data_xpaths[sel.key] = (sel.xpath, sel.data_type)
        return data_xpaths


class Spider(base.BaseCrawl):
    """ This does work of collecting wanted pages' address, it will auto jump
    to another page and continue finding."""
    name = models.CharField(max_length=256, blank=True, null=True)
    url = models.URLField(_('Start URL'), max_length=256, help_text='URL of \
        the starting page')
    crawl_root = models.BooleanField(
        _('Extract data from starting page'), default=False)
    # Link to different pages, all are XPath
    target_links = JSONField(help_text='XPaths toward links to pages with content \
        to be extracted')
    expand_links = JSONField(help_text='List of links (as XPaths) to other pages \
        holding target links (will not be extracted)')
    crawl_depth = models.PositiveIntegerField(default=1, help_text='Set this > 1 \
        in case of crawling from this page')
    collectors = models.ManyToManyField(Collector, blank=True)

    depths = None
    task_id = None
    crawl_links = None

    def crawl_content(self, task_id=None):
        """ Extract all found links then scrape those pages
        Arguments:
            task_id - ID of the (Celery) task, will be genenrated if missing
        Returns:
            (result, path) - Result and path to collected content (dir or ZIP)
        """
        self.task_id = task_id or \
            settings.SCRAPER_NO_TASK_ID_PREFIX + str(uuid.uuid4())

        logger.info('[{0}] START CRAWLING: {1}'.format(
            self.task_id, self.url))

        # Collect all target links from level 0
        self.depths = {'target': {}, 'expand': {}}
        self.crawl_links = {'target': [], 'expand': []}
        if self.crawl_root:
            self.crawl_links['target'].append(self.url)
            self.depths['target'][self.url] = 0
        extractor = self.get_extractor(self.url)
        self.aggregate_links(self.get_links(extractor), 1)
        logger.info('Found links: {0} targets, {1} expansions'.format(
            len(self.crawl_links['target']), len(self.crawl_links['expand'])))

        jres = JSONResult('crawl_content', uuid=extractor._uuid,
                          url=self.url, task_id=self.task_id)
        combined_json = {}
        result_paths = {}
        while self.crawl_links['target'] or self.crawl_links['expand']:
            # Collect data and links from targeted links
            while self.crawl_links['target']:
                target_url = self.crawl_links['target'].pop()
                res = self.process_target(target_url)
                extras = res.pop('extras')
                combined_json[res['id']] = res
                result_paths[res['id']] = extras['path']
            # ... and only links from expand links
            while self.crawl_links['expand']:
                expand_url = self.crawl_links['expand'].pop()
                depth = self.depths['expand'][expand_url]
                # Is this redundant check?
                if depth >= self.crawl_depth:
                    continue
                # Only extract target & expand links, so collector is not
                # necessary
                extr = self.get_extractor(expand_url)
                self.aggregate_links(self.get_links(extr), depth + 1)

        # Create the aggregated Result
        jres.update(content=combined_json)
        crawl_json = jres.json
        crawl_result = create_result(crawl_json, self.task_id)

        # Finalize and move to storage
        storage_path = self.finalize_result(
            crawl_result, crawl_json, result_paths)
        post_crawl.send(self.__class__, task_id=self.task_id)
        return (crawl_result, storage_path)

    def finalize_result(self, crawl_result, crawl_json, result_paths):
        """ Finalize and move collected data to storage """
        crawl_id = crawl_result.data['id']
        logger.info('[{0}] Finalizing result [{1}]'.format(
            self.task_id, crawl_id))
        if COMPRESS_RESULT:
            archive = SimpleArchive(
                crawl_id + '.zip',
                join(settings.SCRAPER_TEMP_DIR, self.storage_location))
            archive.write(INDEX_JSON, crawl_json)
            # Write result files
            for res_id in result_paths:
                res_path = result_paths[res_id]
                for item in os.listdir(res_path):
                    archive.write(
                        join(res_id, item),
                        open(join(res_path, item), 'r').read())
            storage_path = archive.move_to_storage(
                storage, self.storage_location)
        else:
            storage_path = join(self.storage_location, crawl_id)
            write_storage_file(
                storage, join(storage_path, 'index.json'), crawl_json)
            for res_id in result_paths:
                move_to_storage(
                    storage, result_paths[res_id], storage_path)

        # Assign LocalContent object
        content = LocalContent(url=self.url, local_path=storage_path)
        content.save()
        crawl_result.other = content
        crawl_result.save()

        for path in result_paths:
            try:
                rmtree(path)
            except OSError:
                pass

        logger.info('[{0}] Result location: {1}'.format(
            self.task_id, storage_path))
        return storage_path

    def process_target(self, url):
        """ Perform collecting data in specific target url
        Args:
            url - Address of the page to be collected
        Returns:
            JSON of collected data
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
        depth = self.depths['target'][url]
        collector = self.collectors.first()
        res = collector.get_content(url, task_id=self.task_id, spider=self)
        extras = res['extras']
        # Handle the extracted links (target & expand). Bind those
        # with the depth if still in limit
        if depth < self.crawl_depth:
            self.aggregate_links({'target': extras['target']}, depth + 1)
            if depth < self.crawl_depth - 1:
                self.aggregate_links({'expand': extras['expand']}, depth + 1)
        return res

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
    other = models.ForeignKey('LocalContent', null=True, blank=True,
                              on_delete=models.SET_NULL)

    def __unicode__(self):
        return u'Task Result <{0}>'.format(self.task_id)

    def download(self):
        pass


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
            task_id = settings.SCRAPER_NO_TASK_ID_PREFIX + str(uuid.uuid4())
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
        try:
            dirs, files = storage.listdir(self.local_path)
            for fn in files:
                storage.delete(join(self.local_path, fn))
        except OSError:
            logger.error('Error when deleting local files in {0}'.format(
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


# IT WILL BE BEST IF THESE BELOW COULD BE PLACED INTO SEPARATE MODULE


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
