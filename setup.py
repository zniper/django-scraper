import scraper

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


version = scraper.__version__

setup(
    name='django-scraper',
    version=version,
    description='Django application which crawls and downloads online content'
                ' following instructions',
    long_description=open('README.rst').read(),
    license='The MIT License (MIT)',
    url='https://github.com/zniper/django-scraper',
    author='Ha Pham',
    author_email='me@zniper.net',
    packages=['scraper', 'scraper.management', 'scraper.management.commands',
              'scraper.migrations'],
    keywords='crawl scraper spider web pages data extract collect',
    install_requires=[
        'requests',
        'lxml',
        'simplejson==3.6.5',
        'django-jsonfield==0.9.13'
        ],

)
