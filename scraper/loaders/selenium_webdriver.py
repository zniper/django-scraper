import logging

from selenium import webdriver
from selenium.webdriver.firefox.firefox_profile import FirefoxProfile
from selenium.common.exceptions import WebDriverException


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
    try:
        driver = webdriver.Firefox(firefox_profile=get_profile())
        driver.get(url)
        return driver.page_source
    except WebDriverException:
        logger.exception('Unable to browse page: {0}'.format(url))
    finally:
        driver.quit()
