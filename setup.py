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
    packages=['scraper', 'scraper.management.commands', 'scraper.migrations', 'tests'],
    keywords='crawl scraper spider',
    install_requires=[
        'requests',
        'lxml',
        ],

)
