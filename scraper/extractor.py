import hashlib
import mimetypes
from copy import deepcopy

import chardet
import requests
import os
import re
import logging
import urlparse

from os.path import join
from lxml import etree
from readability.readability import Document

from .config import DEFAULT_REPLACE_RULES, custom_loader, INVALID_DATA
from .utils import (
    complete_url, get_uuid, get_link_info, get_content, DATA_TEXT)

logger = logging.getLogger(__name__)


class Extractor(object):
    _url = ''
    _uuid = ''
    _location = ''
    _html = ''
    _archive = None
    headers = {}

    def __init__(self, url, base_dir='.', html='', proxies=None,
                 user_agent=None):
        self.proxies = proxies
        self.headers['User-Agent'] = user_agent if user_agent else ''
        self.base_dir = base_dir
        self.load_source(url, html)
        self._location = self.location

    def xpath(self, value):
        """Supports calling xpath() from root element"""
        try:
            elements = self.root.xpath(value)
            # Deal with the case of injected <tbody> by browser
            if len(elements) == 0 and '/tbody/' in value:
                elements = self.root.xpath(value.replace('tbody/', ''))
            return elements
        except etree.XPathEvalError:
            logger.exception('Invalue XPath value \'{0}\''.format(value))
        return []

    def load_source(self, url, html=''):
        """Loads HTML source from given URL or direct HTML content.
        Args:
            url - (required) URL of a page
            html - HTML source, this prevents loading page at URL
        Returns: Etree element
        """
        if not html:
            html = self.get_source(url)
        self.root = self.parse_content(html)
        self._url = url

    def get_source(self, url):
        """Loads page content from given URL
        Returns: HTML content (source)
        """
        try:
            arguments = {
                'url': url,
                'headers': self.headers,
                'proxies': self.proxies
            }
            if custom_loader:
                content = custom_loader.get_source(**arguments)
            else:
                content = requests.get(**arguments).content
            return content
        except:
            logger.exception('Unable to browse \'{0}\''.format(url))

    def parse_content(self, html=''):
        """ Returns etree._Element object of target page
            html - If provided, this will be used over content at given url
        """
        # Check if html is unicode string or not
        if isinstance(html, bytes):
            # Detect the encoding of html
            try:
                encoding = chardet.detect(html).get("encoding", None)
            except:
                encoding = None
            # Decode html to unicode before passing it to etree
            if encoding:
                html = html.decode(encoding)
            else:
                html = html.decode("utf-8", "ignore")
        if isinstance(html, basestring) and html:
            # Remove encoding inside HTML, let ElementTree deal with it
            self._html = re.sub(
                r'\sencoding=".*?"(?=.*\?\>)', '', html.strip())
        else:
            self._html = '<html></html>'
        parser = etree.HTML(self._html)
        return parser

    @property
    def location(self):
        if not self._location:
            self._uuid = get_uuid(self._url, self.base_dir)
            self._location = os.path.join(self.base_dir, self._uuid)
        return self._location

    def complete_url(self, path):
        return complete_url(self._url, path)

    def extract_links(self, xpaths=None, make_root=False):
        """ Collect all links in current page following given XPath values
        Arguments:
            make_root - Add / at beginning of URL
        """
        links = {}
        xpaths = xpaths or ['//a']
        for xpath in xpaths:
            for element in self.xpath(xpath):
                link = get_link_info(element, make_root)
                if link is None:
                    continue
                url = link['url'].strip().rstrip('/').split('#', 1)[0]
                scheme = urlparse.urlparse(url).scheme.lower()
                if scheme not in ('', 'http', 'https'):
                    continue
                if url in links:
                    if link['text'] and not links[url]['text']:
                        del links[url]
                    else:
                        continue
                links[url] = self.complete_url(link)
        found_links = links.values()
        found_links.sort()
        return found_links

    def extract_content(self, selectors={}, get_image=True, replace_rules=[],
                        deferred_download=False):
        """ Extract the content from current extractor page following rules in
        selectors.

        Arguments
            selectors - Dictionary of selectors, ex: {'key': {'xpath':'',..}}
            get_image - Download images if having HTML content
            replace_rules - List of rules for removing useless text data

        Returns - List of content dict and path to temp directory if existing
            (
                {
                    'content': {},
                    'media': [],
                    'images': []
                },
                'PATH_TO_TEMP_DIR',
            )
        """
        content = {}
        media = []
        images = []
        deferred_info = {"media": {}, "images": {}}
        for key in selectors:
            if isinstance(selectors[key], basestring):
                xpath = selectors[key]
                data_type = 'html'
                attribute = ""
            elif isinstance(selectors[key], dict):
                xpath = selectors[key].get("xpath", "")
                data_type = selectors[key].get("data_type", "") or "html"
                attribute = selectors[key].get("attribute", "")
            else:
                xpath, data_type = selectors[key]
                attribute = ""
            elements = self.xpath(xpath)

            extracted_contents = elements
            if attribute:
                attrs = [element.get(attribute, "") for element in elements
                         if element.get(attribute, "")]
                extracted_contents = attrs
            elif data_type in DATA_TEXT:
                extracted_contents = get_content(elements, data_type)

            # Different handlers for each data_type value
            if data_type == 'binary':
                for url in extracted_contents:
                    # The element must be string to downloadable target
                    if not (isinstance(url, basestring) and url.strip()):
                        continue
                    if not deferred_download:
                        logger.info('Download media object: {0}'.format(url))
                        description = ''
                        file_name = self.download_file(url)
                        if file_name:
                            media.append((file_name, description))
                    else:
                        # If deferred_download, add file's url to
                        # deferred_download's media list.
                        if key not in deferred_info["media"]:
                            deferred_info["media"][key] = []
                        deferred_info["media"][key].append(url)
            else:
                black_words = selectors[key].get("black_words", []) or []
                required_words = selectors[key].get("required_words", []) or []
                # Stop extraction if black word found
                norm_content = ' '.join(extracted_contents).lower()
                for word in black_words:
                    if norm_content.find(word.lower()) != -1:
                        logger.info('Bad word found (%s) in selector (%s). '
                                    'Extraction stopped.' % (word, key))
                        # A ROLLBACK CASE SHOULD BE IMPLEMENTED
                        return (INVALID_DATA, '')

                # Stop extraction if required words not found
                if required_words:
                    has_required_words = False
                    for word_set in required_words:
                        if not hasattr(word_set, '__iter__'):
                            word_set = [word_set]
                        has_word_set = True
                        for word in word_set:
                            if norm_content.find(word.lower()) == -1:
                                has_word_set = False
                                break
                        if has_word_set:
                            has_required_words = True
                            break
                    if not has_required_words:
                        logger.info('Required words not found in selector '
                                    '(%s). Extraction stopped.' % (key))
                        return (INVALID_DATA, '')

                # In case of getting image, put the HTML nodes into a list
                if get_image and data_type == 'html':
                    if not deferred_download:
                        for element in elements:
                            images.extend(self.extract_images(element))
                        # Image's src has been modified, so we need to get
                        # content again.
                        extracted_contents = get_content(elements, data_type)
                    else:
                        # If deferred_download, add file's url to
                        # deferred_download's media list.
                        deferred_info["images"][key] = {
                            "elements": deepcopy(elements),
                            "data_type": data_type
                        }

                # Perfrom replacing in the content
                if replace_rules:
                    extracted_contents = self.refine_content(
                        extracted_contents, replace_rules=replace_rules)
                content[key] = extracted_contents

        # Preparing output
        result = {'content': content,
                  'images': images,
                  'media': media}
        if deferred_download:
            result["deferred_info"] = deferred_info
        return (result, self.location)

    def extract_article(self):
        """Returns only readable content
        Returns:
            data - {
                'title': 'Title of the article',
                'content': 'HTML body of the article'
            }
        """
        doc = Document(self._html)
        return {'title': doc.title(), 'content': doc.summary()}

    def extract_images(self, element, *args, **kwargs):
        """Find all images inside given element and return those URLs"""
        # Download images if required
        imeta = []
        images = element.findall('.//img')
        logger.info('Download %d found image(s)' % len(images))
        for img in images:
            ipath = img.get('src')
            file_name = self.download_file(ipath)
            if file_name:
                caption = img.get('alt', "") or img.get("title", "") or ""
                meta = {'caption': caption}
                new_ipath = os.path.join(self._uuid, file_name)
                img.set('src', new_ipath)
                imeta.append((file_name, meta))
        return imeta

    def write_file(self, file_name, content):
        """ Write file to temporary directory """
        file_path = os.path.join(self.location, file_name)
        try:
            if not os.path.exists(self.location):
                os.makedirs(self.location)
            with open(file_path, 'w') as mfile:
                mfile.write(content)
            return file_path
        except (OSError, IOError):
            logger.exception('Cannot create file: {0}'.format(file_path))

    def get_path(self, file_name):
        """ Return full path of file (include containing directory) """
        return join(self._location, os.path.basename(file_name))

    def get_file_name(self, url, response):
        """
        Get file's name from given url and http response.
        Args:
            url: file's url
            response: http response after getting the file.

        Returns: an unique file's name that will be used to download file.
        """
        last_url_part = url.split('/')[-1].split('?')[0]
        url_extension = ""
        if "." in last_url_part:
            url_extension = "." + last_url_part.split(".")[-1]

        content_type = response.headers.get("Content-Type", "").split(";")[0]
        # Guess file extension from response's content type
        extensions = mimetypes.guess_all_extensions(content_type)
        if extensions:
            if url_extension in extensions:
                file_extension = url_extension
            else:
                file_extension = mimetypes.guess_extension(content_type)
        else:
            # If no extensions match with content_type, use url_extension
            file_extension = url_extension
        # Generate file_name by hashing source url
        file_name = hashlib.sha1(url).hexdigest() + file_extension
        return file_name

    def download_file(self, url):
        """ Download file from given url and save to common location """
        file_url = url.strip()

        if file_url.lower().find('http://') == -1:
            file_url = urlparse.urljoin(self._url, file_url)
        lives = 3
        while lives:
            try:
                response = requests.get(file_url, headers=self.headers,
                                        proxies=self.proxies)
                if response.status_code == 200:
                    file_name = self.get_file_name(url, response)
                    file_path = self.write_file(file_name, response.content)
                    if file_path:
                        return file_name
                else:
                    logger.error('Cannot downloading file %s' % url)
            except requests.ConnectionError:
                logger.info('Retry downloading file: %s' % file_url)
            lives -= 1
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
