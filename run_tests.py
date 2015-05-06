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
    SCRAPER_CRAWL_ROOT=os.path.join(current_dir, 'crawl'),
    SCRAPER_TEMP_DIR=os.path.join(current_dir, '/tmp'),
    SCRAPER_NO_TASK_ID_PREFIX='00-',
    SCRAPER_COMPRESS_RESULT=False,
)


if hasattr(django, "setup"):
    django.setup()


from django_nose import NoseTestSuiteRunner


test_runner = NoseTestSuiteRunner(verbosity=1)
failures = test_runner.run_tests(["scraper"])

if failures:
    sys.exit(failures)
