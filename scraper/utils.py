import requests
import os
import re
import json
import logging
import urlparse

from datetime import datetime
from requests.exceptions import InvalidSchema, MissingSchema
from lxml import etree
from shutil import rmtree
from hashlib import sha1

from django.core.files.storage import default_storage as storage


logger = logging.getLogger(__name__)

EXCLUDED_ATTRIBS = ('html')

INDEX_JSON = 'index.json'

DATETIME_FORMAT = '%Y/%m/%d %H:%I:%S'

refine_rules = [
    re.compile(r'\s+(class|id)=".*?"', re.IGNORECASE),
    re.compile(r'<script.*?</script>', re.IGNORECASE),
    re.compile(r'<a .*?>|</a>', re.IGNORECASE),
    re.compile(r'<h\d.*</h\d>', re.IGNORECASE),
]


class Extractor(object):
    _url = ''
    _hash_value = ''
    _download_to = ''
    _html = ''
    headers = {}

    def __init__(self, url, base_dir='', proxies=None, user_agent=None):
        self._url = url
        self.proxies = proxies
        if user_agent:
            self.headers['User-Agent'] = user_agent
        self.base_dir = base_dir
        self.hash_value, self.root = self.parse_content()
        self.set_location(self.hash_value)

    def parse_content(self):
        """ Return hashed value and etree object of target page """
        content = ''
        try:
            response = requests.get(self._url,
                                    headers=self.headers,
                                    proxies=self.proxies)
            content = response.content
        except (InvalidSchema, MissingSchema):
            with open(self._url, 'r') as target:
                content = target.read()
        hash_value = sha1(self._url).hexdigest()
        self._html = content

        return hash_value, etree.HTML(content)

    def set_location(self, location=''):
        self._download_to = os.path.join(self.base_dir, location)

    def get_location(self):
        return self._download_to

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

    def extract_content(self, selectors={}, get_image=True,
                        media_xpaths=[], replace_rules=[], black_words=[],
                        data=None):
        """ Download the whole content and images and save to local
            * data_xpaths = {
                'key': (xpath_value, data_type),
                ...
                }
        """
        # Extract metadata
        base_meta = {
            'hash': self.hash_value,
            'url': self._url,
            'time': print_time(),
            'content': {},
            'images': [],
            'media': [],
            }
        data = data or {}
        data.update(base_meta)

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
                    logger.info('Download media object: {}'.format(url))
                    description = ''
                    file_name = self.download_file(url)
                    if file_name:
                        data['media'].append((file_name, description))
            else:
                tmp_content = get_content(elements, data_type)
                # Stop operation if black word found
                for word in black_words:
                    norm_content = tmp_content.lower()
                    if norm_content.find(word) != -1:
                        logger.info('Bad word found (%s). Downloading stopped.'
                                    % word)
                        # A ROLL BACK CASE SHOULD BE IMPLEMENTED!
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

        data['content'].update(content)

        # Save extracting result
        self.write_file(INDEX_JSON, json.dumps(data))

        return self._download_to

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
        mfile = None
        try:
            mfile = storage.open(self.get_path(file_name), 'w')
            mfile.write(content)
            mfile.close()
        except IOError:
            # When directories are not auto being created, exception raised.
            # Then try to rewrite using the FileSystemStorage
            os.makedirs(os.path.join(storage.base_location, self._download_to))
            mfile = storage.open(self.get_path(file_name), 'w')
            mfile.write(content)
            mfile.close()
        return mfile

    def get_path(self, file_name):
        """ Return full path of file (include containing directory) """
        return os.path.join(self._download_to,
                            os.path.basename(file_name))

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
        for rg in refine_rules:
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
        #return element.text or ''
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
