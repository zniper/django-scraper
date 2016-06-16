#!/usr/bin/env python

import os
import sys
from django_nose import NoseTestSuiteRunner


os.environ['DJANGO_SETTINGS_MODULE'] = 'scraper.tests.settings'
os.environ["DJANGO_LIVE_TEST_SERVER_ADDRESS"] = "127.0.0.1:9999"

test_runner = NoseTestSuiteRunner(verbosity=1)
failures = test_runner.run_tests(["scraper"])

if failures:
    sys.exit(failures)
