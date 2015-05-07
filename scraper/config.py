import re

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
