import logging

from os.path import dirname, abspath

from selenium import webdriver
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary
from selenium.webdriver.firefox.firefox_profile import FirefoxProfile
from selenium.common.exceptions import WebDriverException

from django.conf import settings


logger = logging.getLogger('scraper')


def get_profile():
    base_dir = dirname(abspath(__file__))
    profile = FirefoxProfile()
    profile.add_extension(base_dir + "/quickjava-2.1.0-fx.xpi")
    profile.set_preference("thatoneguydotnet.QuickJava.curVersion",
                           "2.1.0")
    profile.set_preference("thatoneguydotnet.QuickJava.startupStatus.Images",
                           2)
    profile.set_preference(
        "thatoneguydotnet.QuickJava.startupStatus.AnimatedImage", 2)
    profile.set_preference("thatoneguydotnet.QuickJava.startupStatus.CSS", 2)
    profile.set_preference("thatoneguydotnet.QuickJava.startupStatus.Flash", 2)
    profile.set_preference("thatoneguydotnet.QuickJava.startupStatus.Java", 2)
    profile.set_preference(
        "thatoneguydotnet.QuickJava.startupStatus.Silverlight", 2)
    profile.set_preference('permissions.default.stylesheet', 2)
    profile.set_preference('permissions.default.image', 2)
    profile.set_preference('dom.ipc.plugins.enabled.libflashplayer.so',
                           'false')
    return profile


class Loader(object):
    """Implements a custom loader using selenium firefox webdriver."""

    def __init__(self, url='', headers=None, proxies=None):
        self.url = url
        self.headers = headers
        self.proxies = proxies
        self.timeout = 20   # Set the default timeout to 20
        kwargs = {}
        if settings.SELENIUM_FIREFOX_BINARY:
            kwargs['firefox_binary'] = FirefoxBinary(
                settings.SELENIUM_FIREFOX_BINARY)
        self.driver = webdriver.Firefox(firefox_profile=get_profile(),
                                        **kwargs)
        self.driver.set_page_load_timeout(self.timeout)

    def load(self):
        """ Get HTML content of page at given URL """
        try:
            self.driver.get(self.url)
            return self.driver.page_source
        except WebDriverException:
            logger.exception('Unable to browse page: {0}'.format(self.url))
        finally:
            self.driver.quit()
