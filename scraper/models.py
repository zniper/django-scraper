import logging
import uuid

from datetime import datetime
from os import path
from jsonfield.fields import JSONField

from django.db import models
from django.db.models.signals import pre_delete
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from django.core.files.storage import default_storage as storage
from django.dispatch.dispatcher import receiver

import base

from .config import DATA_TYPES, PROTOCOLS
from .signals import post_crawl, post_scrape
from .utils import SimpleArchive, get_uuid


logger = logging.getLogger(__name__)


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
        extractor = self.get_extractor(url)
        page = extractor._html
        result = create_result(page)
        post_scrape.send(self.__class__, result=result)
        return result

    def get_links(self, url, task_id=None):
        extractor = self.get_extractor(url)
        links = extractor.extract_links()
        result = create_result(links)
        post_scrape.send(self.__class__, result=result)
        return result

    def get_content(self, url, force=False, task_id=None, archive=None):
        """Download the content of a page specified by URL"""
        # Skip the operation if the local content is present
        if not force:
            queryset = LocalContent.objects
            if queryset.filter(url=url, collector__pk=self.pk).exists():
                logger.info('Content exists. Bypass %s' % url)
                return

        logger.info('Download %s' % url)

        # Determine local files location. It musts be unique by collector.
        collector_id = 'co_{0}'.format(self.pk)
        location = datetime.now().strftime('%Y/%m/%d')
        location = path.join(location, collector_id)
        extractor = self.get_extractor(url, location)

        # Extract content from target pages, so target_xpaths and
        # expand_xpaths are redundant
        result_path, json_data = extractor.extract_content(
            get_image=self.get_image,
            selectors=self.selector_dict,
            replace_rules=self.replace_rules,
            archive=archive)

        content = LocalContent(url=url, collector=self, local_path=result_path)
        content.save()
        result = create_result(
            data=json_data, local_content=content, task_id=task_id)

        post_scrape.send(self.__class__, result=result)

        return result

    @property
    def selector_dict(self):
        """Convert the self.selectors into dict of XPaths"""
        data_xpaths = {}
        for sel in self.selectors.all():
            data_xpaths[sel.key] = (sel.xpath, sel.data_type)
        return data_xpaths


class Spider(base.BaseCrawl):
    """This does work of collecting wanted pages' address, it will auto jump
    to another page and continue finding. The operation is limited by:
        crawl_depth: maximum depth of the operation
        expand_links: list of XPaths to links where searches will be performed
    """
    name = models.CharField(max_length=256, blank=True, null=True)
    url = models.URLField(_('Start URL'), max_length=256, help_text='URL of \
        the starting page')
    # Link to different pages, all are XPath
    target_links = JSONField(help_text='XPaths toward links to pages with content \
        to be extracted')
    expand_links = JSONField(help_text='List of links (as XPaths) to other pages \
        holding target links (will not be extracted)')
    crawl_depth = models.PositiveIntegerField(default=1, help_text='Set this > 1 \
        in case of crawling from this page')
    collectors = models.ManyToManyField(Collector, blank=True)

    def crawl_content(self, download=True, task_id=None):
        logger.info('\nStart crawling %s (%s)' % (self.name, self.url))

        extractor = self.get_extractor(self.url)

        all_links = extractor.extract_links(
            link_xpaths=self.target_links,
            expand_xpaths=self.expand_links,
            depth=self.crawl_depth
        )

        logger.info('%d link(s) found' % len(all_links))

        if download:
            # Create a temp SimpleArchive for storing all crawled files
            if settings.SCRAPER_COMPRESS_RESULT:
                archive = SimpleArchive(get_uuid(self.url)+'.zip')
            else:
                archive = None

            results = []
            collectors = self.collectors.all()
            if task_id is None:
                task_id = settings.SCRAPER_NO_TASK_ID_PREFIX + \
                    str(uuid.uuid4())
            for link in all_links:
                url = link['url']
                for collector in collectors:
                    result = collector.get_content(
                        url, task_id=task_id, archive=archive)
                    if result:
                        results.append(result)

            # move the archive
            if settings.SCRAPER_COMPRESS_RESULT and archive:
                storage_location = path.join(
                    datetime.now().strftime('%Y/%m/%d'))
                storage_path = archive.move_to_storage(
                    storage, storage_location)

                # Update local path of results
                local_ids = [res.other.pk for res in results]
                LocalContent.objects.filter(pk__in=local_ids).update(
                    local_path=storage_path)

            return results
        else:
            return all_links

        # Notify some receivers
        post_crawl.send(self.__class__, task_id=task_id)

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
    """This model holds specific ouput information processed by Source.
    It is implemented for better adapts when called by queuing system."""
    task_id = models.CharField(max_length=64, blank=True, null=True)
    data = JSONField()
    other = models.ForeignKey('LocalContent', null=True, blank=True,
                              on_delete=models.SET_NULL)

    def __unicode__(self):
        return u'Task Result <{0}>'.format(self.task_id)

    def download(self):
        pass


def create_result(data, task_id=None, local_content=None):
    """This will create and return the Result object"""
    if not isinstance(data, dict):
        data_dict = {'result': data}
    # If no task_id (from queuing system) provided, new unique ID
    # with prefix will be generated and used
    if task_id is None:
        task_id = settings.SCRAPER_NO_TASK_ID_PREFIX + str(uuid.uuid4())
    res = Result(task_id=task_id, data=data_dict)
    if local_content:
        res.other = local_content
    res.save()
    return res


class LocalContent(models.Model):
    """ Store scrapped content in local, this could be used to prevent
        redownloading
    """
    url = models.CharField(max_length=256)
    collector = models.ForeignKey('Collector')
    local_path = models.CharField(max_length=256)
    created_time = models.DateTimeField(
        default=datetime.now, blank=True, null=True)
    state = models.IntegerField(default=0)

    def __unicode__(self):
        return u'Local Content: %s' % self.url

    def remove_files(self):
        """Remove all files in storage of this LocalContent instance"""
        self.fresh = False
        try:
            dirs, files = storage.listdir(self.local_path)
            for fn in files:
                storage.delete(path.join(self.local_path, fn))
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
