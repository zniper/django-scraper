import os
import logging
import urlparse

from os.path import join
from uuid import uuid4
from zipfile import ZipFile
from datetime import datetime
from lxml import etree

from .config import DATETIME_FORMAT


logger = logging.getLogger(__name__)


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
            return {'url': href, 'text': text}


def get_single_content(element, data_type):
    """Return the processed content of given element"""
    if isinstance(element, basestring) or \
       isinstance(element, etree._ElementStringResult) or \
       isinstance(element, etree._ElementUnicodeResult):
        return element
    if data_type == 'text':
        # Return element.text or ''
        return etree.tounicode(element, method='text')
    elif data_type == 'html':
        return etree.tounicode(element, pretty_print=True)


def get_content(elements, data_type='html'):
    """Receive XPath result and returns appropriate content"""
    if hasattr(elements, '__iter__'):
        return [get_single_content(el, data_type) for el in elements]
    else:
        return get_single_content(elements, data_type)


def print_time(atime=None, with_time=True):
    """Return string friendly value of given time"""
    atime = atime or datetime.now()
    try:
        return atime.strftime(DATETIME_FORMAT)
    except AttributeError:
        pass
    return ''


def get_uuid(url='', base_dir=''):
    """Return whole new and unique ID and make sure not being duplicated
    if base_dir is provided"""
    netloc = urlparse.urlsplit(url).netloc
    duplicated = True
    while duplicated:
        value = uuid4().get_hex()
        uuid = '{0}-{1}'.format(value, netloc) if netloc else value
        if base_dir:
            duplicated = os.path.exists(join(base_dir, uuid))
        else:
            duplicated = False
    return uuid


def write_storage_file(storage, file_path, content):
    """ Write a file with path and content into given storage. This
    merely tries to support both FileSystem and S3 storage """
    try:
        mfile = storage.open(file_path, 'w')
        mfile.write(content)
        mfile.close()
    except IOError:
        # When directories are not auto being created, exception raised.
        # Then try to rewrite using the FileSystemStorage
        location = os.path.dirname(file_path)
        os.makedirs(join(storage.base_location, location))
        mfile = storage.open(file_path, 'w')
        mfile.write(content)
        mfile.close()
    return file_path


class SimpleArchive(object):
    """ This class provides functionalities to create and maintain archive
    file, which is normally used for storing results. """

    _file = None

    def __init__(self, file_path='', base_dir='', *args, **kwargs):
        # Generate new file in case of duplicate or missing
        if not file_path:
            file_path = get_uuid(base_dir=base_dir)
        full_path = join(base_dir, file_path)
        if os.path.exists(full_path):
            os.remove(full_path)
        self._file = ZipFile(full_path, 'w')

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
                logger.error('Error when removing temporary file: {}'.format(
                    self._file.filename))
        return saved_path

    def __str__(self):
        dsc = self._file.filename if self._file else '_REMOVED_'
        return 'SimpleArchive ({})'.format(dsc)
