from selenium import webdriver
from selenium.webdriver.firefox.firefox_profile import FirefoxProfile
from selenium.common.exceptions import WebDriverException

from django.utils.log import getLogger


logger = getLogger('scraper')

firefoxProfile = FirefoxProfile()
firefoxProfile.set_preference('permissions.default.stylesheet', 2)
firefoxProfile.set_preference('permissions.default.image', 2)
firefoxProfile.set_preference('dom.ipc.plugins.enabled.libflashplayer.so',
                              'false')


def get_source(url, headers=[], proxies=[]):
    """ Get HTML content of page at given URL """
    try:
        driver = webdriver.Firefox(firefox_profile=firefoxProfile)
        driver.get(url)
        return driver.page_source
    except WebDriverException:
        logger.exception('Unable to browse page: {0}'.format(url))
    finally:
        driver.close()
