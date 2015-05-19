import requests
import os
import re
import json
import logging
import urlparse

from os.path import join
from requests.exceptions import InvalidSchema, MissingSchema
from lxml import etree

from django.core.files.storage import default_storage as storage
from django.conf import settings

from .config import INDEX_JSON, DEFAULT_REPLACE_RULES
from .utils import (
    SimpleArchive, complete_url, get_uuid, get_link_info, print_time,
    write_storage_file, get_content
    )


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
        crawl_root = settings.SCRAPER_CRAWL_ROOT
        if base_dir.strip().find(crawl_root) != 0:
            self.base_dir = os.path.join(crawl_root, base_dir)
        else:
            self.base_dir = base_dir
        self.root = self.parse_content()
        self.set_location()

    def xpath(self, value):
        """ Support calling xpath() from root element """
        elements = self.root.xpath(value)
        # Deal with the case of injected <tbody> by browser
        if len(elements) == 0 and '/tbody/' in value:
            elements = self.root.xpath(value.replace('tbody/', ''))
        return elements

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
            elements.extend(self.xpath(xpath))

        for el in elements:
            link = get_link_info(el, make_root)
            if link:
                link = self.complete_url(link)
                all_links.append(link)

        # Then, check if going to next page
        if depth > 1:
            for rule in expand_xpaths:
                for path in self.xpath(rule):
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
            self._archive = archive or SimpleArchive(
                self._uuid+'.zip',
                base_dir=settings.SCRAPER_TEMP_DIR
            )
        elif self._archive:
            self._archive = False

        content = {}
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
        if archive is None and self._archive:
            new_path = self._archive.move_to_storage(
                storage, os.path.dirname(self._location))
            self._location = new_path

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
            self._archive.write(join(self._uuid, file_name), content)
        else:
            write_storage_file(storage, self.get_path(file_name), content)

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
