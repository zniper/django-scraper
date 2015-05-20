import re
from django.conf import settings

EXCLUDED_ATTRIBS = ('html')

INDEX_JSON = 'index.json'

DATETIME_FORMAT = '%Y/%m/%d %H:%I:%S'

DEFAULT_REPLACE_RULES = [
    re.compile(r'\s+(class|id)=".*?"', re.IGNORECASE),
    re.compile(r'<script.*?</script>', re.IGNORECASE),
    re.compile(r'<a .*?>|</a>', re.IGNORECASE),
    re.compile(r'<h\d.*</h\d>', re.IGNORECASE),
]

DATA_TYPES = (
    ('text', 'Text content'),
    ('html', 'HTML content'),
    ('binary', 'Binary content'),
)

PROTOCOLS = (
    ('http', 'HTTP'),
    ('https', 'HTTPS'),
)

COMPRESS_RESULT = getattr(settings, 'SCRAPER_COMPRESS_RESULT', False)
TEMP_DIR = getattr(settings, 'SCRAPER_TEMP_DIR', '')
CRAWL_ROOT = getattr(settings, 'SCRAPER_CRAWL_ROOT', '')
