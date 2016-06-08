from __future__ import unicode_literals
from copy import deepcopy
from os.path import join
from jsonfield.fields import JSONField
from shutil import rmtree

import uuid
import urlparse
import itertools
import os
import logging

from django.core.files.storage import default_storage as storage
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch.dispatcher import receiver
from django.utils.encoding import force_text
from django.utils.six import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _
from django.utils.timezone import now

from scraper.runner import SpiderRunner
from .config import (DATA_TYPES, PROTOCOLS, INDEX_JSON, COMPRESS_RESULT,
                     TEMP_DIR, NO_TASK_PREFIX, CRAWL_ROOT)
from .mixins import ExtractorMixin
from .utils import SimpleArchive, Data, write_storage_file, move_to_storage
from .signals import post_scrape
from .extractor import Extractor
try:
    xrange
except NameError:
    xrange = range

logger = logging.getLogger(__name__)


@python_2_unicode_compatible
class Spider(ExtractorMixin, models.Model):
    """ This does work of collecting wanted pages' address, it will auto jump
    to another page and continue finding."""
    name = models.CharField(max_length=256, blank=True, null=True)
    # Link to different pages, all are XPath
    expand_links = JSONField(
        help_text=_('List of links (as XPaths) to other pages holding target '
                    'links (will not be extracted)'))
    crawl_depth = models.PositiveIntegerField(
        default=1,
        help_text=_('Set this > 1 in case of crawling from this page'))
    headers = JSONField(
        verbose_name=_("Headers"),
        help_text=_("Define custom headers when download pages."),
        null=True, blank=True)
    proxy = models.ForeignKey(
        'ProxyServer', blank=True, null=True, on_delete=models.PROTECT)
    depths = None
    crawl_links = None
    _storage_location = None
    _task = None
    _work = None

    @property
    def storage_location(self):
        """docstring for storage_location"""
        if not self._storage_location:
            self._storage_location = os.path.join(
                CRAWL_ROOT, now().strftime('%Y/%m/%d'))
        return self._storage_location

    def get_proxy(self):
        return self.proxy.get_dict() if self.proxy else None

    def get_ua(self):
        return self.user_agent.value if self.user_agent else None

    def _new_extractor(self, url, source=''):
        """Return Extractor instance with given URL. If URL invalid, None will be
        returned"""
        splitted_url = urlparse.urlsplit(url)
        if splitted_url.scheme and splitted_url.netloc:
            extractor = Extractor(
                url,
                base_dir=os.path.join(TEMP_DIR, self.storage_location),
                proxies=self.get_proxy(),
                user_agent=self.get_ua(),
                html=source
            )
            return extractor
        else:
            logger.error('Cannot get Extractor due to invalid URL: {0}'.format(
                url))

    def get_root_urls(self):
        """Returns all root urls."""
        urls = []
        for craw_url in self.urls.all():
            urls = itertools.chain(urls, craw_url.generate_urls())
        return urls

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
        # self._set_extractor()
        has_files = False
        if not task_id:
            task_id = SpiderRunner.generate_task_id()
        self._task = task_id
        data = Data(spider=self.id, task_id=task_id)
        for operation in operations:
            datum = self._perform(**operation)
            data.add_result(datum)
            if 'path' in datum.extras and not has_files:
                has_files = True
        result = self.create_result(data.dict, self._task)
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
        method = getattr(operator, action + '_' + target)
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
        runner = SpiderRunner(spider=self, task_id=self._task)
        return runner.run()

    def create_result(self, data, task_id=None, local_content=None):
        """ This will create and return the Result object. It binds with a task ID
        if provided.
        Arguments:
            data - Result data as dict or string value
            task_id - (optional) ID of related task
            local_content - (optional) related local content object
        """
        # If no task_id (from queuing system) provided, new unique ID
        # with prefix will be generated and used
        data = deepcopy(data)
        # Remove extras's path information from datum since it's should not be
        # stored in result
        for datum in data["results"]:
            if "path" in datum.get("extras", {}):
                datum["extras"].pop("path")
        if task_id is None:
            duplicated = True
            while duplicated:
                task_id = NO_TASK_PREFIX + str(uuid.uuid4())
                if not Result.objects.filter(task_id=task_id).exists():
                    break
        res = Result(task_id=task_id, data=data, spider=self)
        if local_content:
            res.other = local_content
        res.save()
        return res

    def _finalize(self, data):
        """Should be called at final step in operate(). This finalizes and
        move collected data to storage if having files downloaded"""
        logger.info('[{0}] Finalizing result'.format(self._task))

        data_paths = []
        for datum in data.results:
            if 'path' in datum.get('extras', {}):
                data_paths.extend(datum['extras']['path'])
            if "extras" in datum:
                datum.pop("extras")
        if COMPRESS_RESULT:
            archive = SimpleArchive(
                self._task + '.zip',
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
            storage_path = join(self.storage_location, self._task)
            write_storage_file(
                storage, join(storage_path, 'index.json'), data.json)
            for d_path in data_paths:
                move_to_storage(storage, d_path, storage_path)

        # Assign LocalContent object
        local_content = LocalContent(local_path=storage_path)
        local_content.save()

        for path in data_paths:
            if os.path.exists(path):
                try:
                    rmtree(path)
                except OSError:
                    logger.info('Unable to remove temp dir: {0}'.format(path))
        logger.info('[{0}] Result location: {1}'.format(
            self._task, storage_path))
        return local_content

    def __str__(self):
        return _('Spider: {0}').format(self.name)


@python_2_unicode_compatible
class CrawlUrl(models.Model):
    """Hold information of crawling urls."""
    base = models.URLField(max_length=256, verbose_name=_("Base URL"),
                           help_text=_("Base url for the crawled target. "
                                       "Placeholder {0} could be used if "
                                       "url patterns is given."))
    number_pattern = JSONField(verbose_name=_("URL number pattern"),
                               help_text=_("Number pattern must be in"
                                           "(start, stop, step) format."),
                               null=True, blank=True)
    text_pattern = JSONField(verbose_name=_("URL text pattern"),
                             help_text=_("Define a list of texts that will be "
                                         "replaced for placeholder {0} to "
                                         "generate crawling URLs."),
                             null=True, blank=True)
    spider = models.ForeignKey(Spider, verbose_name=_("Spider"),
                               related_name="urls")

    def __str__(self):
        return self.base

    def generate_urls(self):
        """Generate crawling urls from base & patterns."""
        urls = []
        if "{0}" in self.base:
            if self.number_pattern:
                number_urls = (self.base.format(idx) for idx in
                               xrange(*self.number_pattern))
                urls = itertools.chain(urls, number_urls)
            if self.text_pattern:
                text_urls = (self.base.format(item) for item in
                             self.text_pattern)
                urls = itertools.chain(urls, text_urls)
            return urls
        return [self.base]


@python_2_unicode_compatible
class DataItem(models.Model):
    """Hold definition for data that will be extracted."""
    name = models.CharField(max_length=50, verbose_name=_("Name"),
                            help_text=_("Data's name. E.g: Article, News, "
                                        "Video, etc..."))
    base = models.CharField(
        max_length=512, verbose_name=_("Base XPath"),
        help_text=_("Base XPath to target's data container in page. Empty "
                    "means whole document."),
        null=True, blank=True)
    spider = models.ForeignKey(Spider, verbose_name=_("Spider"),
                               related_name="data_items")

    def __str__(self):
        return "{} - {}".format(self.spider.name, self.name)


@python_2_unicode_compatible
class Collector(models.Model):
    """This could be a single site or part of a site which contains wanted
    content"""
    # name = models.CharField(max_length=256)
    link = models.CharField(max_length=512, verbose_name=_("Link"),
                            help_text=_("Relative xpath from DataItem's base "
                                        "to the link that contains data's "
                                        "information. Empty means information "
                                        "is inside base."),
                            null=True, blank=True)
    get_image = models.BooleanField(
        default=True,
        help_text=_('Download images found inside extracted content'))
    # Dict of replacing rules (regex & new value):
    #    replace_rules = [('\<ul\>.*?\<ul\>', ''), ...]
    replace_rules = JSONField(
        help_text=_('List of Regex rules will be applied to refine data'),
        null=True, blank=True
    )
    # Extra settings
    # black_words = models.CharField(max_length=256, blank=True, null=True)
    data_item = models.ForeignKey(DataItem, verbose_name=_("Data item"),
                                  related_name="collectors")

    def __str__(self):
        return _('Collector: {0}-{1}').format(force_text(self.data_item),
                                              self.link)

    @property
    def selector_dict(self):
        """Convert the self.selectors into dict of XPaths"""
        data_xpaths = {}
        for sel in self.selectors.all():
            data_xpaths[sel.key] = sel.to_dict()
        return data_xpaths


@python_2_unicode_compatible
class Selector(models.Model):
    """docstring for DataElement"""
    key = models.SlugField()
    xpath = models.CharField(max_length=512)
    attribute = models.CharField(
        max_length=50, verbose_name=_("Attribute"),
        help_text=_("Name of element's attribute. If given, element's "
                    "attribute will be returned instead of element's "
                    "content."),
        null=True, blank=True)
    data_type = models.CharField(max_length=64, choices=DATA_TYPES)
    required_words = JSONField(verbose_name=_("Required words"),
                               help_text=_("Only store item if value returned "
                                           "by this selector contains given "
                                           "words."),
                               null=True, blank=True)
    black_words = JSONField(verbose_name=_("Black words"),
                            help_text=_("Skip item if value returned by this "
                                        "selector contains one of given words."
                                        ),
                            null=True, blank=True)
    collector = models.ForeignKey(Collector, verbose_name=_("Collector"),
                                  related_name="selectors")

    def __str__(self):
        return _('Selector: {0} - Collector: {1}').format(
            self.key,
            force_text(self.collector)
        )

    def to_dict(self):
        return {
            "key": self.key,
            "xpath": self.xpath,
            "attribute": self.attribute,
            "data_type": self.data_type,
            "required_words": self.required_words,
            "black_words": self.black_words
        }


@python_2_unicode_compatible
class Result(models.Model):
    """ This model holds specific ouput information processed by Source.
    It is implemented for better adapts when called by queuing system. """
    task_id = models.CharField(max_length=64, blank=True, null=True)
    data = JSONField()
    other = models.ForeignKey('LocalContent', blank=True, null=True,
                              on_delete=models.SET_NULL)
    spider = models.ForeignKey(Spider, verbose_name=_("Spider"),
                               related_name="results")

    def __str__(self):
        return _('Task Result <{0}>').format(self.task_id)

    def get_data(self, clean=False):
        """Return self.data. If clean is True, only data content will be
        returned (time, url, ID,... will be excluded)."""
        if clean:
            content = {}
            for result in self.data['results']:
                data_items = result['content']
                for data_item, items_list in data_items.items():
                    if data_item not in content:
                        content[data_item] = []
                    content[data_item].extend(items_list)
            return content
        return self.data


@python_2_unicode_compatible
class LocalContent(models.Model):
    """ Store scrapped content in local, this could be used to prevent
        redownloading
    """
    local_path = models.CharField(max_length=256)
    created_time = models.DateTimeField(
        auto_now_add=True, blank=True, null=True)
    state = models.IntegerField(default=0)

    def __str__(self):
        return _('Content (at {0}) of: {1}').format(self.created_time,
                                                    self.result_set.first())

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


@python_2_unicode_compatible
class UserAgent(models.Model):
    """ Define a specific user agent for being used in Source """
    name = models.CharField(_('UA Name'), max_length=64)
    value = models.CharField(_('User Agent String'), max_length=256)

    def __str__(self):
        return _('User Agent: {0}').format(self.name)


@python_2_unicode_compatible
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

    def __str__(self):
        return _('Proxy Server: {0}').format(self.name)


# TODO it will be best if these below could be placed into separate module


@receiver(pre_delete, sender=LocalContent)
def clear_local_files(sender, instance, *args, **kwargs):
    """Ensure all files saved into media dir will be deleted as well"""
    instance.remove_files()


@receiver(pre_delete, sender=Result)
def remove_result(sender, **kwargs):
    """Ensure all related local content will be deleted."""
    result = kwargs['instance']
    if result.other:
        result.other.delete()
