import requests
import os
import re
import json
import logging
import urlparse

from uuid import uuid4
from zipfile import ZipFile
from datetime import datetime
from requests.exceptions import InvalidSchema, MissingSchema
from lxml import etree

from django.core.files.storage import default_storage as storage
from django.conf import settings

from .config import INDEX_JSON, DEFAULT_REPLACE_RULES, DATETIME_FORMAT


logger = logging.getLogger(__name__)


class Extractor(object):
    _url = ''
    _uuid = ''
    _location = ''
    _html = ''
    _archive = None
    headers = {}

    def __init__(self, url, base_dir='', proxies=None, user_agent=None):
        self._url = url
        self.proxies = proxies
        if user_agent:
            self.headers['User-Agent'] = user_agent
        self.base_dir = os.path.join(
            getattr(settings, 'SCRAPER_CRAWL_ROOT', ''), base_dir)
        self.root = self.parse_content()
        self.set_location()

    def parse_content(self):
        """Returns etree._Element object of target page"""
        content = ''
        try:
            response = requests.get(self._url,
                                    headers=self.headers,
                                    proxies=self.proxies)
            content = response.content
        except (InvalidSchema, MissingSchema):
            with open(self._url, 'r') as target:
                content = target.read()
        self._html = content
        return etree.HTML(content)

    def set_location(self, reset=False):
        """Determine the path where downloaded files will be stored"""
        if reset or not self._location:
            self._uuid = get_uuid(self._url, self.base_dir)
            self._location = os.path.join(self.base_dir, self._uuid)
        return self._location

    @property
    def location(self):
        return self._location

    def complete_url(self, path):
        return complete_url(self._url, path)

    def extract_links(self, link_xpaths=['//a'], expand_xpaths=[], depth=1,
                      make_root=False):
        """Extracts all links within current page, following given rules"""
        all_links = []

        # First, crawl all target links
        elements = []
        for xpath in link_xpaths:
            elements.extend(self.root.xpath(xpath))

        for el in elements:
            link = get_link_info(el, make_root)
            if link:
                link = self.complete_url(link)
                all_links.append(link)

        # Then, check if going to next page
        if depth > 1:
            for rule in expand_xpaths:
                for path in self.root.xpath(rule):
                    link = get_link_info(path)
                    if link:
                        url = self.complete_url(link['url'])
                        sub_extractor = Extractor(url)
                        sub_links = sub_extractor.extract_links(
                            link_xpaths, expand_xpaths, depth-1, make_root)
                        all_links.extend(sub_links)

        return all_links

    def extract_content(self, selectors={}, get_image=True, replace_rules=[],
                        black_words=[], data=None, archive=None):
        """ Download the whole content and images and save to default storage.
            Return:
                (result_dir_path, {'content': <JSON_DATA>})
        """
        # Extract metadata
        base_meta = {
            'uuid': self._uuid,
            'url': self._url,
            'time': print_time(),
            'content': {},
            'images': [],
            'media': [],
            }
        data = data or {}
        data.update(base_meta)

        # If file compress is present, all content will be putting there
        # otherwise a new one will be created
        if settings.SCRAPER_COMPRESS_RESULT:
            self._archive = archive if archive else \
                SimpleArchive(self._uuid+'.zip')
        elif self._archive:
            self._archive = False

        content = {}
        for key in selectors:
            if isinstance(selectors[key], basestring):
                xpath = selectors[key]
                data_type = 'html'
            else:
                xpath, data_type = selectors[key]
            elements = self.root.xpath(xpath)
            # Different handlers for each data_type value
            if data_type == 'binary':
                for url in elements:
                    # The element must be string to downloadable target
                    if not (isinstance(url, basestring) and url.strip()):
                        continue
                    logger.info('Download media object: {0}'.format(url))
                    description = ''
                    file_name = self.download_file(url)
                    if file_name:
                        data['media'].append((file_name, description))
            else:
                tmp_content = get_content(elements, data_type)
                # Stop operation if black word found
                for word in black_words:
                    norm_content = ' '.join(tmp_content).lower()
                    if norm_content.find(word) != -1:
                        logger.info('Bad word found (%s). Downloading stopped.'
                                    % word)
                        # A ROLLBACK CASE SHOULD BE IMPLEMENTED
                        return None
                # Perfrom replacing in the content
                if replace_rules:
                    tmp_content = self.refine_content(
                        tmp_content, replace_rules=replace_rules)
                content[key] = tmp_content
                # In case of getting image, put the HTML nodes into a list
                if get_image and data_type == 'html':
                    for element in elements:
                        data['images'].extend(self.extract_images(element))

        # Save extracting result
        data['content'].update(content)
        json_data = json.dumps(data)
        self.write_file(INDEX_JSON, json_data)

        # Only move to storage if archive was created by Collector
        if settings.SCRAPER_COMPRESS_RESULT:
            if archive is None and self._archive:
                self._archive.move_to_storage(
                    storage, os.path.dirname(self._location))

        return (self._location, json_data)

    def extract_images(self, element, *args, **kwargs):
        """Find all images inside given element and return those URLs"""
        # Download images if required
        imeta = []
        images = element.findall('.//img')
        logger.info('Download %d found image(s)' % len(images))
        for img in images:
            ipath = img.xpath('@src')[0]
            file_name = self.download_file(ipath)
            meta = {'caption': ''.join(element.xpath('@alt'))}
            imeta.append((file_name, meta))
        return imeta

    def write_file(self, file_name, content):
        """Write file to selected file storage with given path and content"""
        # Get file writing function
        if self._archive:
            self._archive.write(os.path.join(self._uuid, file_name), content)
        else:
            write_storage_file(storage, self.get_path(file_name), content)

    def get_path(self, file_name):
        """ Return full path of file (include containing directory) """
        return os.path.join(self._location, os.path.basename(file_name))

    def download_file(self, url):
        """ Download file from given url and save to common location """
        file_url = url.strip()
        file_name = url.split('/')[-1].split('?')[0]
        if file_url.lower().find('http://') == -1:
            file_url = urlparse.urljoin(self._url, file_url)
        lives = 3
        while lives:
            try:
                lives -= 1
                response = requests.get(file_url, headers=self.headers,
                                        proxies=self.proxies)
                if response.status_code == 200:
                    self.write_file(file_name, response.content)
                    return file_name
                else:
                    logger.error('Error [%d] downloading %s' % (
                        response.status_code, url))
            except requests.ConnectionError:
                logger.error('Retry downloading file %s' % file_url)
        return None

    def refine_content(self, content, custom_rules=None):
        """ rules should adapt formats:
                [(action, target, value),...]j
            actions:
                'replace'
        """
        if not custom_rules:
            return content

        content = content.replace('\n', '').strip()

        # Run custom rules first
        for rule in custom_rules:
            rg = re.compile(rule, re.IGNORECASE)
            content = rg.sub('', content)

        # then common rules...
        for rg in DEFAULT_REPLACE_RULES:
            content = rg.sub('', content)

        return content


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
            duplicated = os.path.exists(os.path.join(base_dir, uuid))
        else:
            duplicated = False
    return uuid


def write_storage_file(storage, file_path, content):
    """Write a file with path and content into given storage. This
    merely tries to support both FileSystem and S3 storage"""
    try:
        mfile = storage.open(file_path, 'w')
        mfile.write(content)
        mfile.close()
    except IOError:
        # When directories are not auto being created, exception raised.
        # Then try to rewrite using the FileSystemStorage
        location = os.path.dirname(file_path)
        os.makedirs(os.path.join(storage.base_location, location))
        mfile = storage.open(file_path, 'w')
        mfile.write(content)
        mfile.close()
    return file_path


class SimpleArchive(object):
    """This class provides functionalities to create and maintain archive
    file, which is normally used for storing results."""

    _file = None

    def __init__(self, file_path='', *args, **kwargs):
        # Generate new file in case of duplicate or missing
        if not file_path:
            file_path = get_uuid(base_dir=settings.SCRAPER_TEMP_DIR)
        full_path = os.path.join(settings.SCRAPER_TEMP_DIR, file_path)
        if os.path.exists(full_path):
            raise IOError('Duplicate file name: {0}'.format(full_path))
        self._file = ZipFile(full_path, 'w')

    def write(self, file_name, content):
        """Write file with content into current archive"""
        self._file.writestr(file_name, content)

    def finish(self):
        self._file.close()

    def move_to_storage(self, storage, location):
        """Move the current archive to given location (dir) in storage.
        Notice: current ._file will be deleted"""
        self.finish()
        content = open(self._file.filename, 'r').read()
        file_path = os.path.join(location,
                                 os.path.basename(self._file.filename))
        return write_storage_file(storage, file_path, content)
