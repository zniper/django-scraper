import urlparse
from django.db import models

from utils import Extractor


class BaseCrawl(models.Model):
    """Provides base class for crawling and extracting classes"""
    proxy = models.ForeignKey(
        'ProxyServer', blank=True, null=True, on_delete=models.PROTECT)
    user_agent = models.ForeignKey(
        'UserAgent', blank=True, null=True, on_delete=models.PROTECT)

    def get_extractor(self, url, base_dir=''):
        """Return Extractor instance with given URL. If URL invalid, None will be
        returned"""
        splitted_url = urlparse.urlsplit(url)
        if splitted_url.scheme and splitted_url.netloc:
            extractor = Extractor(
                url,
                base_dir=base_dir,
                proxies=self.get_proxy(),
                user_agent=self.get_ua()
            )
            return extractor

    def get_proxy(self):
        return self.proxy.get_dict() if self.proxy else None

    def get_ua(self):
        return self.user_agent.value if self.user_agent else None
