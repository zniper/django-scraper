import os
import logging

from datetime import datetime
from shutil import rmtree

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
    content_xpath = models.CharField(max_length=255)
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

    def __unicode__(self):
        return 'Source: %s' % self.name

    def crawl(self, download=True):
        logger.info('')
        logger.info('Start crawling %s (%s)' % (self.name, self.url))

        # Custom definitions
        metapath = eval(self.meta_xpath)
        rules = [item.strip() for item in self.refine_rules.split('\n')
                 if item.strip()]
        extrapath = [item.strip() for item in self.extra_xpath.split('\n')
                     if item.strip()]
        proxy = {}
        if self.proxy:
            logger.info('Use proxy server: %s' % self.proxy.address)
            proxy = self.proxy.get_dict()
        else:
            proxy = None
        if self.user_agent:
            logger.info('Use user agent: %s' % self.user_agent.name)
            ua = self.user_agent.value
        else:
            ua = None
        extractor = Extractor(self.url, settings.CRAWL_ROOT, 
                              proxies=proxy, user_agent=ua)
        make_root = False
        if self.link_xpath.startswith('/+'):
            make_root = True
            self.link_xpath = self.link_xpath[2:] 
        all_links = extractor.extract_links(
            xpath=self.link_xpath,
            expand_rules=self.expand_rules.split('\n'),
            depth=self.crawl_depth,
            make_root=make_root)
        logger.info('%d link(s) found' % len(all_links))

        if download:
            blacklist = []
            if self.black_words:
                blacklist = self.black_words.words.split('\n')
            for link in all_links:
                try:
                    link_url = link['url']
                    print link_url
                    if LocalContent.objects.filter(url=link_url).count():
                        logger.info('Bypass %s' % link_url)
                        continue
                    logger.info('Download %s' % link_url)
                    location = datetime.now().strftime('%Y/%m/%d')
                    location = os.path.join(settings.CRAWL_ROOT, location)
                    sub_extr = Extractor(link_url, location, proxy)
                    if self.content_type:
                        base_meta = {'type': self.content_type.name}
                    else:
                        base_meta = None
                    local_path = sub_extr.extract_content(
                        self.content_xpath,
                        with_image=self.download_image,
                        metapath=metapath,
                        extrapath=extrapath,
                        custom_rules=rules,
                        blacklist=blacklist,
                        metadata=base_meta)
                    content = LocalContent(url=link_url, source=self,
                                           local_path=local_path)
                    content.save()
                except:
                    logger.exception('Error when extracting %s' % link['url'])
        else:
            return all_links


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


class ProxyServer(models.Model):
    """ Stores information of proxy server """
    PROTOCOLS = (
        ('http', 'HTTP'),
        ('https', 'HTTPS'),
    )
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
