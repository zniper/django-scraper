import os
import logging
import urlparse
import simplejson as json

from os.path import join
from uuid import uuid4
from zipfile import ZipFile
from datetime import datetime
from lxml import etree
from shutil import rmtree

from django.utils.functional import cached_property

from .config import DATETIME_FORMAT


logger = logging.getLogger(__name__)


class JSONResult(object):
    """ Provide better way to produce JSON result, which will be put into
    index.json and stored along with result objects """

    def __init__(self, action, *args, **kwargs):
        self.action = action
        self.uuid = kwargs.get('uuid') or kwargs.get('id')
        self.task = kwargs.get('task_id')
        self.url = kwargs.get('url')
        self.start = kwargs.get('start') or datetime.now()
        self.end = kwargs.get('end') or None
        self.content = kwargs.get('content')
        self.media = kwargs.get('media') or []
        self.images = kwargs.get('images') or []

    @property
    def dict(self):
        if self.end is None:
            self.end = datetime.now()
        result = {
            'id': self.uuid,
            'task': self.task,
            'url': self.url,
            'action': self.action,
            'start': print_time(self.start),
            'end': print_time(self.end),
            'content': self.content,
            'images': self.images,
            'media': self.media,
        }
        return result

    def update(self, **kwargs):
        """ Update this object data with provided dictionary """
        for key in kwargs:
            self.__setattr__(key, kwargs[key])

    @cached_property
    def json(self):
        """ Return as pretty JSON """
        return json.dumps(self.dict, indent=2)


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
        href = link.get('href') if not make_root else '/'+link.get('href')
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
    if hasattr(elements, '__iter__'):
        return [get_single_content(el, data_type) for el in elements]
    else:
        return get_single_content(elements, data_type)


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
