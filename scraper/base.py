import urlparse
import os

from datetime import datetime

from django.db import models
from django.utils.log import getLogger

from .extractor import Extractor
from .config import CRAWL_ROOT, TEMP_DIR

logger = getLogger('scraper')


class BaseCrawl(models.Model):
    """Provides base class for crawling and extracting classes"""
    proxy = models.ForeignKey(
        'ProxyServer', blank=True, null=True, on_delete=models.PROTECT)
    user_agent = models.ForeignKey(
        'UserAgent', blank=True, null=True, on_delete=models.PROTECT)
    _storage_location = None

    def get_extractor(self, url):
        """Return Extractor instance with given URL. If URL invalid, None will be
        returned"""
        splitted_url = urlparse.urlsplit(url)
        if splitted_url.scheme and splitted_url.netloc:
            extractor = Extractor(
                url,
                base_dir=os.path.join(TEMP_DIR, self.storage_location),
                proxies=self.get_proxy(),
                user_agent=self.get_ua()
            )
            return extractor
        else:
            logger.error('Cannot get Extractor due to invalid URL: {0}'.format(
                url))

    @property
    def storage_location(self):
        """docstring for storage_location"""
        if not self._storage_location:
            self._storage_location = os.path.join(
                CRAWL_ROOT, datetime.now().strftime('%Y/%m/%d'))
        return self._storage_location

    def get_proxy(self):
        return self.proxy.get_dict() if self.proxy else None

    def get_ua(self):
        return self.user_agent.value if self.user_agent else None
