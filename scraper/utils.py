import os
import logging
import urlparse

import signal
import simplejson as json
import itertools
import requests

from copy import deepcopy
from time import sleep
from os.path import join
from uuid import uuid4
from zipfile import ZipFile
from datetime import datetime
from lxml import etree
from shutil import rmtree
from Queue import Queue
from threading import Thread

from django.utils.functional import cached_property

from .config import (
    custom_loader, DATETIME_FORMAT, CONCURRENT_DOWNLOADS, QUEUE_WAIT_PERIOD
)

logger = logging.getLogger(__name__)

DATA_TEXT = ['html', 'text']


class Data(object):
    """Stores ouput data collected from set of operations, with additional
    information"""

    def __init__(self, *args, **kwargs):
        # self.uuid = kwargs.get('uuid') or kwargs.get('id')
        self.task = kwargs.get('task_id')
        self.spider = kwargs.get('spider')
        self.start = kwargs.get('start') or datetime.now()
        self.end = kwargs.get('end') or None
        self.results = []

    @property
    def dict(self):
        if self.end is None:
            self.end = datetime.now()
        result = {
            # 'id': self.uuid,
            'task': self.task,
            'spider': self.spider,
            'start': print_time(self.start),
            'end': print_time(self.end),
            'results': self.results,
        }
        return result

    def update(self, **kwargs):
        """ Update this object data with provided dictionary """
        for key in kwargs:
            self.__setattr__(key, kwargs[key])

    def add_result(self, result):
        self.results.append(result.dict)

    @cached_property
    def json(self):
        """ Return as pretty JSON """
        return json.dumps(self.dict, indent=2)


class Datum(object):
    """Holds ouput of a single operation, supports export to JSON.
        ...
        extras - Holds non-result information"""

    def __init__(self, content, media=None, images=None, **kwargs):
        self.content = content
        self.media = media or []
        self.images = images or []
        self.extras = kwargs

    @property
    def dict(self):
        return self.__dict__

    @property
    def json(self):
        return json.dumps(self.__dict__, indent=2)


def complete_url(base, link):
    """Test and complete an URL with scheme, domain, base path if missing.
    If base doesn't have scheme, it will be auto added."""
    url = link['url'] if isinstance(link, dict) else link
    elements = urlparse.urlsplit(url)
    if not elements.scheme:
        url = urlparse.urljoin(base, url)
    if isinstance(link, dict):
        link['url'] = url
    else:
        link = url
    return link


def get_link_info(link, make_root=False):
    """Extract basic information from a given link (as etree Element),
    and return a dictionary:
        {
            'url': '...',
            'text': '...',
        }
    In case of having invalid URL, the function will return None
    """
    if isinstance(link, etree._Element):
        href = link.get('href') if not make_root else '/' + link.get('href')
        text = link.text.strip() if isinstance(link.text, basestring) else ''
        if href:
            return {'url': href.strip(), 'text': text}


def get_single_content(element, data_type):
    """Return the processed content of given element"""
    if isinstance(element, basestring) or \
            isinstance(element, etree._ElementStringResult) or \
            isinstance(element, etree._ElementUnicodeResult):
        return element
    if data_type == 'text':
        # Return element.text or ''
        return etree.tounicode(element, method='text').strip()
    elif data_type == 'html':
        return etree.tounicode(element, pretty_print=True).strip()


def get_content(elements, data_type='html'):
    """Receive XPath result and returns appropriate content"""
    # Eliminate empty string elements
    items = []
    if hasattr(elements, '__iter__'):
        items = [get_single_content(el, data_type) for el in elements]
    else:
        items = get_single_content(elements, data_type)
    if data_type in DATA_TEXT:
        [items.remove(val) for val in items if not val]
        return items


def print_time(atime=None, with_time=True):
    """Return string friendly value of given time"""
    if isinstance(atime, basestring):
        return atime
    atime = atime or datetime.now()
    try:
        return atime.strftime(DATETIME_FORMAT)
    except AttributeError:
        pass
    return ''


def get_uuid(url='', base_dir='', size=8):
    """ Return whole new and unique ID and make sure not being duplicated
    if base_dir is provided
        url (optional) - Address of related page
        base_dir (optional) - Directory path to check for duplication
        size (optional) - Size of the UUID prefix
    """
    netloc = urlparse.urlsplit(url).netloc
    duplicated = True
    while duplicated:
        value = uuid4().get_hex()[:size]
        uuid = '{0}-{1}'.format(value, netloc) if netloc else value
        if base_dir:
            duplicated = os.path.exists(join(base_dir, uuid))
        else:
            duplicated = False
    return uuid


def write_storage_file(storage, file_path, content):
    """ Write a file with path and content into given storage. This
    merely tries to support both FileSystem and S3 storage

    Arguments:
        storage - Django file storage
        file_path - relative path to the file
        content - content of file to be written
    """
    try:
        mfile = storage.open(file_path, 'w')
        mfile.write(content)
        mfile.close()
    except IOError:
        # When directories are not auto being created, exception raised.
        # Then try to rewrite using the FileSystemStorage
        location = join(storage.base_location, os.path.dirname(file_path))
        if not os.path.exists(location):
            os.makedirs(location)
        mfile = storage.open(file_path, 'w')
        mfile.write(content)
        mfile.close()
    return file_path


def move_to_storage(storage, source, location):
    """ Move single file or whole directory to storage. Empty directory
    will not be moved.
    Arguments:
        storage: Instance of the file storage (FileSystemStorage,...)
        source: File or directory to be moved
        location: Relative path where the file/dir will be placed into.
    Returns:
        Path of file in storage
    """
    source = source.strip().rstrip('/')
    if os.path.isfile(source):
        saved_path = write_storage_file(
            storage, join(location, os.path.basename(source)),
            open(source, 'r').read())
    else:
        blank_size = len(source.rsplit('/', 1)[0]) + 1
        for items in os.walk(source):
            loc = join(location, items[0][blank_size:])
            for item in items[2]:
                write_storage_file(
                    storage, join(loc, item),
                    open(join(items[0], item), 'r').read())
        saved_path = join(location, os.path.basename(source))

    # Nuke old file/dir
    try:
        if os.path.isfile(source):
            os.remove(source)
        else:
            rmtree(source)
    except OSError:
        logger.exception('Error when deleting: {0}'.format(source))

    return saved_path


class SimpleArchive(object):
    """ This class provides functionalities to create and maintain archive
    file, which is normally used for storing results. """

    _file = None

    def __init__(self, file_path='', base_dir='', *args, **kwargs):
        # Generate new file in case of duplicate or missing
        if not file_path:
            file_path = get_uuid(base_dir=base_dir)
        self.file_path = join(base_dir, file_path)

        # Create directories if not existing
        location = os.path.dirname(self.file_path)
        if not os.path.exists(location):
            os.makedirs(location)

        if os.path.exists(self.file_path):
            os.remove(self.file_path)
        self._file = ZipFile(self.file_path, 'w')

    def write(self, file_name, content):
        """ Write file with content into current archive """
        self._file.writestr(file_name, content)

    def finish(self):
        self._file.close()

    def move_to_storage(self, storage, location, remove=True):
        """ Move the current archive to given location (directory) in storage.
        Arguments:
            storage: Instance of the file storage (FileSystemStorage,...)
            location: Absolute path where the file will be placed into.
            remove: Option to remove the current file after moved or not.
        Returns:
            Path of file in storage
        """
        self.finish()

        content = open(self._file.filename, 'r').read()
        file_path = join(location, os.path.basename(self._file.filename))
        saved_path = write_storage_file(storage, file_path, content)

        # Remove file if successful
        if remove and saved_path:
            try:
                os.remove(self._file.filename)
                self._file = None
            except OSError:
                logger.error('Error when removing temporary file: {0}'.format(
                    self._file.filename))
        return saved_path

    def __str__(self):
        dsc = self._file.filename if self._file else '_REMOVED_'
        return 'SimpleArchive ({0})'.format(dsc)


def interval_to_list(interval):
    """Convert interval string to list of number
        '1-4'
    Returns:
        [1, 2, 3, 4]
    """
    elements = [e.strip().split('-') for e in interval.split(',')]
    return [n for r in elements for n in range(int(r[0]), int(r[-1]) + 1)]


def generate_urls(base_url, elements=None):
    """Returns every URL base on the starting URL and other values
        base_url = 'http://domain/class-{0}/?name={1}'
        elements = ((1, 2), ('jane', 'john'))
    Returns:
        [
            'http://domain/class-1/?name=jane'
            'http://domain/class-1/?name=john'
            'http://domain/class-2/?name=jane'
            'http://domain/class-2/?name=john'
        ]
    """
    # Convert the intervals into lists
    refined = []
    for element in elements:
        full_list = []
        for i, value in enumerate(element):
            if isinstance(value, basestring) and '-' in value:
                full_list.extend(interval_to_list(value))
            else:
                full_list.append(value)
        refined.append(full_list)
    for comb in itertools.product(*refined):
        yield base_url.format(*comb)


class DownloadThread(Thread):
    """A thread that will handle downloading pages from a given queue of urls.
    """

    def __init__(self, queue, results, *args, **kwargs):
        """
        Initialize the thread
        Args:
            queue: a Queue object with urls inside.
            results: Dictionary for holding downloaded sources.
        """
        self.queue = queue
        self.results = results
        self.kwargs = kwargs
        self.loader = None
        super(DownloadThread, self).__init__(**kwargs)

    def run(self):
        """Keep waiting and perform download when having url inside queue.
        """
        while not self.queue.empty():
            url = self.queue.get()
            kwargs = deepcopy(self.kwargs)
            try:
                kwargs['url'] = url
                if custom_loader:
                    self.loader = custom_loader.Loader(**kwargs)
                    content = self.loader.load()
                else:
                    content = requests.get(**kwargs).content
                self.results[url] = content
            except:
                logger.exception('Unable to browse \'{0}\''.format(url))
            self.queue.task_done()


class BatchDownloader(object):
    """Handle multi-threaded page downloading."""

    def __init__(self, urls, **kwargs):
        """Initialize the downloader.
        Args:
            urls: a list of urls that will be downloaded.
            **kwargs: optional params to be transferred to worker
        """
        self.urls = urls
        self.kwargs = kwargs
        self.concurrent = kwargs.get('concurrent') or CONCURRENT_DOWNLOADS
        self.queue = Queue()
        [self.queue.put(url) for url in self.urls]
        self.results = {}
        self.threads = []
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signal, *args, **kwargs):
        """Stop all of the threads by emptying the queue."""
        # Empty the queue
        if not self.queue.empty():
            self.queue.queue.clear()

    def download(self):
        """ Returns a dict of page content.
        Returns: {
                     'http://first/page': 'page content...',
                    'http://second/page': 'page content 2...'
                 }
        """
        for i in range(min(len(self.urls), CONCURRENT_DOWNLOADS)):
            thread = DownloadThread(self.queue, self.results, **self.kwargs)
            thread.setDaemon(True)
            thread.start()
            self.threads.append(thread)
        while self.queue.unfinished_tasks:
            sleep(QUEUE_WAIT_PERIOD)
        return self.results


def download_batch(urls, **kwargs):
    """Download the given urls and returns a dictionary of results."""
    downloader = BatchDownloader(urls, **kwargs)
    return downloader.download()
