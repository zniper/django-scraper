import os
import logging

from datetime import datetime
from shutil import rmtree
from jsonfield.fields import JSONField

from django.db import models
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from django.core.files.storage import default_storage as storage

from .utils import Extractor
from .base import BaseCrawl


logger = logging.getLogger(__name__)

DATA_TYPES = (
    ('text', 'Text content'),
    ('html', 'HTML content'),
    ('binary', 'Binary content'),
)

PROTOCOLS = (
    ('http', 'HTTP'),
    ('https', 'HTTPS'),
)


class Collector(BaseCrawl):
    """This could be a single site or part of a site which contains wanted
    content"""
    # Basic infomation
    name = models.CharField(max_length=256)
    selectors = models.ManyToManyField('Selector', blank=True)
    get_image = models.BooleanField(default=True, help_text='Download images found \
        inside extracted content')
    # Dict of replacing rules (regex & new value):
    #    replace_rules = [('\<ul\>.*?\<ul\>', ''), ...]
    replace_rules = JSONField(help_text='List of Regex rules will be applied to \
        refine data')
    # Extra settings
    black_words = models.ForeignKey(
        'WordSet', blank=True, null=True, on_delete=models.PROTECT)

    def __unicode__(self):
        return u'Collector: {}'.format(self.name)

    def get_page(self, url, html_only=True, task_id=None):
        extractor = self.get_extractor(url)
        page = extractor._html
        return create_result(page, task_id)

    def get_links(self, url, task_id=None):
        extractor = self.get_extractor(url)
        links = extractor.extract_links()
        return create_result(links, task_id)

    def get_content(self, url, task_id=None, force=False):
        """Download the content of a page specified by URL"""
        # Skip the operation if the local content is present
        if not force:
            queryset = LocalContent.objects
            if queryset.filter(url=url, collector__pk=self.pk).exists():
                logger.info('Content exists. Bypass %s' % url)
                return

        logger.info('Download %s' % url)

        # Determine local files location. It musts be unique by collector.
        collector_id = 'co_{}'.format(self.pk)
        location = datetime.now().strftime('%Y/%m/%d')
        location = os.path.join(settings.CRAWL_ROOT, location, collector_id)
        extractor = self.get_extractor(url, location)

        # Extract content from target pages, so target_xpaths and
        # expand_xpaths are redundant
        result_path = extractor.extract_content(
            get_image=self.get_image,
            selectors=self.selector_dict,
            replace_rules=self.replace_rules)

        content = LocalContent(url=url, collector=self, local_path=result_path)
        content.save()
        return create_result(content.pk, task_id)

    @property
    def selector_dict(self):
        """Convert the self.selectors into dict of XPaths"""
        data_xpaths = {}
        for sel in self.selectors.all():
            data_xpaths[sel.key] = (sel.xpath, sel.data_type)
        return data_xpaths


class Spider(BaseCrawl):
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

    def crawl(self, download=True):
        logger.info('\nStart crawling %s (%s)' % (self.name, self.url))

        extractor = self.get_extractor(self.url)

        all_links = extractor.extract_links(
            link_xpaths=self.target_links,
            expand_xpaths=self.expand_links,
            depth=self.crawl_depth
        )

        logger.info('%d link(s) found' % len(all_links))

        # Just dry running or real download
        if download:
            all_content = []
            collectors = self.collectors.all()
            for link in all_links:
                url = link['url']
                for collector in collectors:
                    content = collector.get_content(url)
                    if content:
                        all_content.append(content)
            return all_content
        else:
            return all_links

    def __unicode__(self):
        return 'Spider: {}'.format(self.name)


class Selector(models.Model):
    """docstring for DataElement"""
    key = models.SlugField()
    xpath = models.CharField(max_length=512)
    data_type = models.CharField(max_length=64, choices=DATA_TYPES)

    def __unicode__(self):
        return u'Selector: {}'.format(self.key)


class Result(models.Model):
    """This model holds specific ouput information processed by Source.
    It is implemented for better adapts when called by queuing system."""
    task_id = models.CharField(max_length=64)
    data = JSONField()
    other = models.ForeignKey('LocalContent', null=True, blank=True,
                              on_delete=models.DO_NOTHING)

    def __unicode__(self):
        return u'Task Result <{}>'.format(self.task_id)


def create_result(data, task_id=None, local=None):
    """This will create and return the Result object if task_id is present.
    Otherwise, the data will be returned."""
    if task_id:
        if not isinstance(data, dict):
            data_dict = {'result': data}
        res = Result(task_id=task_id, data=data_dict)
        if local:
            res.other = local
        res.save()
        return res
    return data


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
                storage.delete(os.path.join(self.local_path, fn))
        except OSError:
            logger.error('Error when deleting local files in {}'.format(
                self.local_path))
        self.local_path = ''
        self.state = 1
        self.save()


class WordSet(models.Model):
    """ Class words in to set for filtering purposes """
    name = models.CharField(max_length=64)
    words = models.TextField()

    def save(self, *args, **kwargs):
        """ Normalize all words in set """
        good_list = []
        for word in self.words.lower().split('\n'):
            word = word.strip()
            if word and word not in good_list:
                good_list.append(word)
        self.words = '\n'.join(good_list)
        return super(WordSet, self).save(*args, **kwargs)

    def __unicode__(self):
        return u'Words: %s' % self.name


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
