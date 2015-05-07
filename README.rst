.. image:: https://travis-ci.org/zniper/django-scraper.svg?branch=master
          :target: https://travis-ci.org/zniper/django-scraper

.. image:: https://coveralls.io/repos/zniper/django-scraper/badge.svg?branch=master 
          :target: https://coveralls.io/r/zniper/django-scraper?branch=master

**django-scraper** is a Django application which crawls and downloads online content following configurable instructions.

Features
========

* Extract content of given online website/pages and stored under JSON format
* [new] Having option for compressing crawled data
* [new] Transparently support AWS S3 storage 
* [new] Customisable crawling requests for different use cases
* Process can be started from Django management command (~cron job) or with Python code 
* Browse and download content in linked pages, with given depth.
* Support extracting multiple content (text, html, images, binary files) in the same page
* Have content refinement (replacement) rules and black words filtering
* Store and prevent duplication of downloaded content
* Support proxy servers, and user-agents

*The application is successfully tested with Django 1.6 and 1.7 (under Python 2.6, 2.7)*

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
