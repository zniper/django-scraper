from selenium import webdriver
from selenium.common.exceptions import WebDriverException

from django.utils.log import getLogger


logger = getLogger('scraper')


def get_source(url, headers=[], proxies=[]):
    """ Get HTML content of page at given URL """
    try:
        driver = webdriver.Firefox()
        driver.get(url)
        return driver.page_source
    except WebDriverException:
        logger.exception('Unable to browse page: {0}'.format(url))
    finally:
        driver.close()
