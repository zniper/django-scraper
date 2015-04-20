import os
import logging

from datetime import datetime
from shutil import rmtree
from jsonfield.fields import JSONField

from django.db import models
from django.conf import settings
from django.utils.translation import ugettext_lazy as _

from utils import Extractor


logger = logging.getLogger(__name__)


class Source(models.Model):
    """ This could be a single site or part of a site which contains wanted
        content
    """
    url = models.CharField(max_length=256)
    name = models.CharField(max_length=256, blank=True, null=True)
    # Links section
    link_xpath = models.CharField(max_length=255)
    expand_rules = models.TextField(blank=True, null=True)
    crawl_depth = models.PositiveIntegerField(default=1)
    # Content section
    content_xpath = models.CharField(max_length=255, blank=True, null=True)
    content_type = models.ForeignKey('ContentType', blank=True, null=True)
    meta_xpath = models.TextField(default='', blank=True)
    extra_xpath = models.TextField(default='', blank=True)
    refine_rules = models.TextField(default='', blank=True)
    active = models.BooleanField(default=True)
    download_image = models.BooleanField(default=True)
    # Extra settings
    black_words = models.ForeignKey('WordSet', blank=True, null=True)
    proxy = models.ForeignKey('ProxyServer', blank=True, null=True)
    user_agent = models.ForeignKey('UserAgent', blank=True, null=True)

    __extractor = None

    def __unicode__(self):
        return '%s' % (self.name or self.url)

    @property
    def extractor(self):
        if self.__extractor is None:
            self.__extractor = Extractor(
                self.url, settings.CRAWL_ROOT,
                proxies=self.get_proxy(), user_agent=self.get_ua())
        return self.__extractor

    def get_proxy(self):
        return self.proxy.get_dict() if self.proxy else None

    def get_ua(self):
        return self.user_agent.value if self.user_agent else None

    def get_page(self, html_only=True, task_id=None):
        page = self.extractor._html
        return create_result(page, task_id)

    def get_links(self, internal_only=True, task_id=None):
        links = self.extractor.extract_links()
        return create_result(links, task_id)

    def crawl(self, download=True):
        logger.info('')
        logger.info('Start crawling %s (%s)' % (self.name, self.url))

        # Custom definitions
        metapath = eval(self.meta_xpath) if self.meta_xpath else None
        expand_rules = self.expand_rules.split('\n') \
            if self.expand_rules else None
        refine_rules = [item.strip() for item in self.refine_rules.split('\n')
                        if item.strip()]
        extrapath = [item.strip() for item in self.extra_xpath.split('\n')
                     if item.strip()]

        make_root = False
        if self.link_xpath.startswith('/+'):
            make_root = True
            self.link_xpath = self.link_xpath[2:]

        all_links = self.extractor.extract_links(
            xpath=self.link_xpath,
            expand_rules=expand_rules,
            depth=self.crawl_depth,
            make_root=make_root)
        logger.info('%d link(s) found' % len(all_links))

        # Just dry running or real download
        if download:
            blacklist = []
            local_content = []
            if self.black_words:
                blacklist = self.black_words.words.split('\n')
            for link in all_links:
                try:
                    link_url = link['url']
                    if LocalContent.objects.filter(url=link_url).count():
                        logger.info('Bypass %s' % link_url)
                        continue
                    logger.info('Download %s' % link_url)
                    location = datetime.now().strftime('%Y/%m/%d')
                    location = os.path.join(settings.CRAWL_ROOT, location)
                    sub_extr = Extractor(link_url, location, self.get_proxy())
                    if self.content_type:
                        base_meta = {'type': self.content_type.name}
                    else:
                        base_meta = None
                    local_path = sub_extr.extract_content(
                        self.content_xpath,
                        with_image=self.download_image,
                        metapath=metapath,
                        extrapath=extrapath,
                        custom_rules=refine_rules,
                        blacklist=blacklist,
                        metadata=base_meta)
                    content = LocalContent(url=link_url, source=self,
                                           local_path=local_path)
                    content.save()
                    local_content.append(content)
                except:
                    logger.exception('Error when extracting %s' % link['url'])
            paths = [lc.local_path for lc in local_content]
            return paths
        else:
            return all_links


class Result(models.Model):
    """This model holds specific ouput information processed by Source.
    It is implemented for better adapts when called by queuing system."""
    task_id = models.CharField(max_length=64)
    data = JSONField()
    other = models.ForeignKey('LocalContent', null=True, blank=True,
                              on_delete=models.DO_NOTHING)

    def __unicode__(self):
        return "Task Result <{}>".format(self.task_id)


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
    source = models.ForeignKey('Source', related_name='content',
                               blank=True, null=True)
    local_path = models.CharField(max_length=256)
    created_time = models.DateTimeField(default=datetime.now,
                                        blank=True, null=True)
    state = models.IntegerField(default=0)

    def __unicode__(self):
        return 'Local Content: %s' % self.url

    def remove_files(self):
        self.fresh = False
        try:
            rmtree(self.local_path)
        except OSError:
            pass
        self.local_path = ''
        self.state = 1
        self.save()

    def delete(self, **kwargs):
        self.remove_files()
        super(LocalContent, self).delete(**kwargs)


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
        return 'Words: %s' % self.name


class ContentType(models.Model):
    """ Type assigned to the crawled content. This is not strictly required """
    name = models.CharField(max_length=64)
    description = models.TextField(blank=True, null=True)

    def __unicode__(self):
        return 'Type: %s' % self.name


class UserAgent(models.Model):
    """ Define a specific user agent for being used in Source """
    name = models.CharField(_('UA Name'), max_length=64)
    value = models.CharField(_('User Agent String'), max_length=256)

    def __unicode__(self):
        return 'User Agent: %s' % self.name


PROTOCOLS = (
    ('http', 'HTTP'),
    ('https', 'HTTPS'),
)


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
        return 'Proxy Server: %s' % self.name
