import requests
import os
import re
import logging
import urlparse

from os.path import join
from requests.exceptions import InvalidSchema, MissingSchema
from lxml import etree

from .config import DEFAULT_REPLACE_RULES
from .utils import complete_url, get_uuid, get_link_info, get_content


logger = logging.getLogger('scraper')


class Extractor(object):
    _url = ''
    _uuid = ''
    _location = ''
    _html = ''
    _archive = None
    headers = {}

    def __init__(self, url, base_dir='.', proxies=None, user_agent=None):
        self._url = url
        self.proxies = proxies
        self.headers['User-Agent'] = user_agent if user_agent else ''
        self.base_dir = base_dir
        self.root = self.parse_content()
        self._location = self.location

    def xpath(self, value):
        """ Support calling xpath() from root element """
        try:
            elements = self.root.xpath(value)
            # Deal with the case of injected <tbody> by browser
            if len(elements) == 0 and '/tbody/' in value:
                elements = self.root.xpath(value.replace('tbody/', ''))
            return elements
        except etree.XPathEvalError:
            logger.exception('Cannot evaluate XPath value: {0}'.format(value))
        return []

    def parse_content(self):
        """ Returns etree._Element object of target page """
        content = ''
        try:
            response = requests.get(
                self._url, headers=self.headers, proxies=self.proxies)
            content = response.content
        except (InvalidSchema, MissingSchema):
            with open(self._url, 'r') as target:
                content = target.read()
        self._html = content
        return etree.HTML(content)

    @property
    def location(self):
        if not self._location:
            self._uuid = get_uuid(self._url, self.base_dir)
            self._location = os.path.join(self.base_dir, self._uuid)
        return self._location

    def complete_url(self, path):
        return complete_url(self._url, path)

    def extract_links(self, xpaths=['//a'], unique=True, make_root=False):
        """ Collect all links in current page following given XPath values
        Arguments:
            xpaths - List of XPath values of links
            unique - Accept URL duplication in result or nor
            make_root - Add / at beginning of URL
        """
        urls = []
        links = []
        for xpath in xpaths:
            for element in self.xpath(xpath):
                link = get_link_info(element, make_root)
                if not link:
                    continue
                if unique:
                    if link['url'] in urls:
                        continue
                    urls.append(link['url'])
                links.append(self.complete_url(link))
        return links

    def extract_content(self, selectors={}, get_image=True, replace_rules=[],
                        black_words=[]):
        """ Extract the content from current extractor page following rules in
        selectors.

        Arguments
            selectors - Dictionary of selectors, ex: {'key': 'xpath'}
            get_image - Download images if having HTML content
            replace_rules - List of rules for removing useless text data
            black_words - Process will stop if one of these words found

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
        for key in selectors:
            if isinstance(selectors[key], basestring):
                xpath = selectors[key]
                data_type = 'html'
            else:
                xpath, data_type = selectors[key]
            elements = self.xpath(xpath)

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
                        media.append((file_name, description))
            else:
                tmp_content = get_content(elements, data_type)

                # Stop operation if black word found
                for word in black_words:
                    norm_content = ' '.join(tmp_content).lower()
                    if norm_content.find(word) != -1:
                        logger.info('Bad word found (%s). Downloading stopped.'
                                    % word)
                        # A ROLLBACK CASE SHOULD BE IMPLEMENTED
                        return (None, '')

                # Perfrom replacing in the content
                if replace_rules:
                    tmp_content = self.refine_content(
                        tmp_content, replace_rules=replace_rules)
                content[key] = tmp_content

                # In case of getting image, put the HTML nodes into a list
                if get_image and data_type == 'html':
                    for element in elements:
                        images.extend(self.extract_images(element))

        # Preparing output
        return ({
            'content': content,
            'images': images,
            'media': media,
            'uuid': self._uuid,
        }, self.location)

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
        """ Write file to temporary directory """
        file_path = os.path.join(self.location, file_name)
        try:
            if not os.path.exists(self.location):
                os.makedirs(self.location)
            with open(file_path, 'w') as mfile:
                mfile.write(content)
            return file_path
        except OSError:
            logger.exception('Cannot create file: {0}'.format(file_path))

    def get_path(self, file_name):
        """ Return full path of file (include containing directory) """
        return join(self._location, os.path.basename(file_name))

    def download_file(self, url):
        """ Download file from given url and save to common location """
        file_url = url.strip()
        file_name = url.split('/')[-1].split('?')[0]
        if file_url.lower().find('http://') == -1:
            file_url = urlparse.urljoin(self._url, file_url)
        lives = 3
        while lives:
            try:
                response = requests.get(file_url, headers=self.headers,
                                        proxies=self.proxies)
                if response.status_code == 200:
                    self.write_file(file_name, response.content)
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
