import re
import logging

from django.conf import settings
from django.utils.translation import ugettext_lazy as _


logger = logging.getLogger(__name__)

EXCLUDED_ATTRIBS = ('html')

INDEX_JSON = 'index.json'

DATETIME_FORMAT = '%Y/%m/%d %H:%I:%S'

DEFAULT_REPLACE_RULES = [
    re.compile(r'\s+(class|id)=".*?"', re.IGNORECASE),
    re.compile(r'<script.*?</script>', re.IGNORECASE),
    re.compile(r'<a .*?>|</a>', re.IGNORECASE),
    re.compile(r'<h\d.*</h\d>', re.IGNORECASE),
]

MODE_CRAWL = 'crawl'            # Crawl and scraping data
MODE_EXTRACT = 'extract'        # Single extracting from one page
MODE_READ = 'read'              # Get readable content

WORK_MODE_CHOICES = (
    (MODE_CRAWL, _('crawl & scrape data')),
    (MODE_EXTRACT, _('extract from single page')),
    (MODE_READ, _('get readable content'))
)

DATA_TYPES = (
    ('text', 'Text content'),
    ('html', 'HTML content'),
    ('binary', 'Binary content'),
)

INVALID_DATA = -1

PROTOCOLS = (
    ('http', 'HTTP'),
    ('https', 'HTTPS'),
)

SETTINGS = getattr(settings, 'SCRAPER_SETTINGS', {})

COMPRESS_RESULT = SETTINGS.get('COMPRESS_RESULT', False)
TEMP_DIR = SETTINGS.get('TEMP_DIR', '/tmp/scraper')
CRAWL_ROOT = SETTINGS.get('CRAWL_ROOT', '')
NO_TASK_PREFIX = SETTINGS.get('NO_TASK_ID_PREFIX', '')

CONCURRENT_DOWNLOADS = SETTINGS.get('CONCURRENT_DOWNLOADS', 4)
QUEUE_WAIT_PERIOD = 1

custom_loader = None
if SETTINGS.get('CUSTOM_LOADER', None):
    try:
        module_path = SETTINGS['CUSTOM_LOADER']
        from django.utils.importlib import import_module
        custom_loader = import_module(module_path)
    except:
        logger.exception('Cannot load module {0}'.format(module_path))
