import os
import sys

import django

from django.conf import settings


current_dir = os.path.dirname(os.path.realpath(__file__))

settings.configure(
    DEBUG=True,
    USE_TZ=True,
    DATABASES={
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
        }
    },
    ROOT_URLCONF="scraper.urls",
    INSTALLED_APPS=[
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "django.contrib.sites",
        "scraper",
    ],
    MIDDLEWARE_CLASSES=(
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
        ),
    SITE_ID=1,
    TEMPLATE_DIRS=[
        os.path.abspath(os.path.join(
            os.path.dirname(__file__), "scraper", "tests", "templates")),
    ],
    SCRAPER_SETTINGS={
        'CRAWL_ROOT': 'crawl/',
        'COMPRESS_RESULT': False,
        'TEMP_DIR': 'tmp/',
        'NO_TASK_ID_PREFIX': '00-',
        'CUSTOM_LOADER': '',
    },
    LOGGING = {
        'version': 1,
        'handlers': {
            'null': {
                'level': 'DEBUG',
                'class': 'django.utils.log.NullHandler',
            },
        },
        'loggers': {
            'django.db.backends': {
                'handlers': ['null'],
                'propagate': False,
                'level': 'DEBUG',
            },
        }
    },
)


if hasattr(django, "setup"):
    django.setup()


from django_nose import NoseTestSuiteRunner


test_runner = NoseTestSuiteRunner(verbosity=1)
failures = test_runner.run_tests(["scraper"])

if failures:
    sys.exit(failures)
