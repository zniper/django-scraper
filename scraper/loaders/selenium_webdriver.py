import logging

from selenium import webdriver
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary
from selenium.webdriver.firefox.firefox_profile import FirefoxProfile
from selenium.common.exceptions import WebDriverException

from django.conf import settings


logger = logging.getLogger('scraper')


def get_profile():
    profile = FirefoxProfile()
    profile.set_preference('permissions.default.stylesheet', 2)
    profile.set_preference('permissions.default.image', 2)
    profile.set_preference('dom.ipc.plugins.enabled.libflashplayer.so',
                           'false')
    return profile


def get_source(url, headers=[], proxies=[]):
    """ Get HTML content of page at given URL """
    firefox_binary = None
    if settings.SELENIUM_FIREFOX_BINARY:
        firefox_binary = FirefoxBinary(settings.SELENIUM_FIREFOX_BINARY)
    try:
        driver = webdriver.Firefox(firefox_profile=get_profile(),
                                   firefox_binary=firefox_binary)
        driver.get(url)
        return driver.page_source
    except WebDriverException:
        logger.exception('Unable to browse page: {0}'.format(url))
    finally:
        driver.quit()
