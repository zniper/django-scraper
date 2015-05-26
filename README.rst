.. image:: https://travis-ci.org/zniper/django-scraper.svg?branch=master
          :target: https://travis-ci.org/zniper/django-scraper

.. image:: https://coveralls.io/repos/zniper/django-scraper/badge.svg?branch=master 
          :target: https://coveralls.io/r/zniper/django-scraper?branch=master

**django-scraper** is a Django application for collecting online content following user-defined instructions

Features
========

* Extract content of given online website/pages and stored under JSON data
* Crawl then extract content in multiple pages, with given depth.
* Can download media files present in page
* Have option for storing data under ZIP file
* Support standard file system and AWS S3 storage
* Customisable crawling requests for different scenarios
* Process can be started from Django management command (~cron job) or with Python code
* Support extracting multiple content (text, html, images, binary files) in the same page
* Have content refinement (replacement) rules and black words filtering
* Support custom proxy servers, and user-agents

*Support Django 1.6, 1.7, and 1.8*

Installation
============
This application requires some other tools installed first::
    
    lxml
    requests


**django-scraper** installation can be made using `pip`::

    pip install django-scraper

For more and latest information about configuration or usage, please visit the repository in github: https://github.com/zniper/django-scraper

Support
=======
If you have any questions about this application, please email to: me@zniper.net
