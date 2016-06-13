#!/usr/bin/env python

import os
import sys

import django

os.environ['DJANGO_SETTINGS_MODULE'] = 'test_settings.settings'
os.environ["DJANGO_LIVE_TEST_SERVER_ADDRESS"] = "127.0.0.1:9999"

if hasattr(django, "setup"):
    django.setup()

from django_nose import NoseTestSuiteRunner

test_runner = NoseTestSuiteRunner(verbosity=1)
failures = test_runner.run_tests(["scraper"])

if failures:
    sys.exit(failures)
