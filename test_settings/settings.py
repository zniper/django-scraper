import  os

import scraper

try:
    from logging import NullHandler

    null_handler = 'logging.NullHandler'
except ImportError:
    null_handler = 'django.utils.log.NullHandler'

STATIC_URL = "/static/"

STATIC_ROOT = "/static/"

DEBUG = True

USE_TZ = True

SECRET_KEY = "not-so-secret"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3"
    }
}

ROOT_URLCONF = "test_settings.urls"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sites",
    "scraper",
]

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
)

SITE_ID = 1

TEMPLATE_DIRS = [
    os.path.abspath(os.path.join(
        os.path.dirname(__file__), "scraper", "tests",
        "templates")),
]

SCRAPER_SETTINGS = {
    'CRAWL_ROOT': 'crawl/',
    'COMPRESS_RESULT': False,
    'TEMP_DIR': 'tmp/',
    'NO_TASK_ID_PREFIX': '00-',
    'CUSTOM_LOADER': '',
}

LOGGING = {
    'version': 1,
    'handlers': {
        'null': {
            'level': 'DEBUG',
            'class': null_handler,
        },
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['null'],
            'propagate': False,
            'level': 'DEBUG',
        },
    }
}

TEST_DATA_URL = "/test_data/"

TEST_DATA_DIR = scraper.__path__[0] + "/test_data/"