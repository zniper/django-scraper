import requests
import os
import re
import json
import logging

from lxml import etree
from urlparse import urljoin
from shutil import rmtree
from hashlib import sha1


logger = logging.getLogger(__name__)

EXCLUDED_ATTRIBS = ('html')

INDEX_HTML = 'index.html'
INDEX_JSON = 'index.json'

refine_rules = [
    re.compile(r'\s+(class|id)=".*?"', re.IGNORECASE),
    re.compile(r'<script.*?</script>', re.IGNORECASE),
    re.compile(r'<a .*?>|</a>', re.IGNORECASE),
    re.compile(r'<h\d.*</h\d>', re.IGNORECASE),
    ]


class Extractor(object):
    url = ''
    hash_value = ''

    def __init__(self, url, base_dir='', proxies=None):
        self.url = url
        self.proxies = proxies
        self.base_dir = base_dir
        self.hash_value, self.root = self.parse_content(url)
        self.set_location(self.hash_value)

    def parse_content(self, url=''):
        """ Return hashed value and etree object of target page """
        response = requests.get(url)
        hash_value = sha1(url).hexdigest()
        return hash_value, etree.HTML(response.content)

    def set_location(self, location=''):
        self.download_to = os.path.join(self.base_dir, location)

    def extract_links(self, xpath, expand_rules=None, depth=1):
        all_links = []

        # First, crawl all links in the current page
        elements = self.root.xpath(xpath)
        for el in elements:
            all_links.append({
                'url': self.complete_url(el.get('href')),
                'text': el.text,
                })

        # Check if going to next page
        if depth > 1:
            for rule in expand_rules:
                for path in self.root.xpath(rule):
                    url = self.complete_url(path)
                    sub_extractor = Extractor(url)
                    sub_links = sub_extractor.extract_links(
                        xpath, expand_rules, depth-1)
                    all_links.extend(sub_links)

        return all_links

    def complete_url(self, path):
        if path.strip().lower()[:7] != 'http://':
            path = urljoin(self.url, path)
        return path

    def extract_content(self, xpath, with_image=True, metapath=None,
                        extrapath=None, custom_rules=None, blacklist=None,
                        metadata=None):
        """ Download the whole content and images and save to local
            * metapath = {
                'key': xpath_value,
                ...
                }
        """
        # Extract metadata
        base_meta = {
            'hash': self.hash_value,
            'url': self.url,
            }
        metadata = metadata or {}
        metadata.update(base_meta)

        for key in metapath:
            metadata[key] = self.root.xpath(metapath[key]) or ''

        # Create dir and download HTML content
        self.prepare_directory()
        content = etree.tostring(self.root.xpath(xpath)[0], pretty_print=True)
        content = self.refine_content(content, custom_rules=custom_rules)
        node = etree.HTML(content)

        # Check if this content will be fully downloaded or not
        stop_flag = False
        norm_content = content.lower()
        for word in blacklist:
            if norm_content.find(word) != -1:
                logger.info('Bad word found (%s). Downloading stopped.' % word)
                stop_flag = True
                break

        # Download images if required
        images_meta = []
        if with_image and not stop_flag:
            images = node.xpath('//img')
            logger.info('Download %d found image(s)' % len(images))
            for el in images:
                ipath = el.xpath('@src')[0]
                file_name = self.download_file(ipath)
                content = content.replace(ipath, file_name)
                meta = {'caption': ''.join(el.xpath('@alt'))}
                images_meta.append((file_name, meta))
        metadata['images'] = images_meta

        # Download extra content
        extra_files = []
        for single_path in extrapath:
            for url in self.root.xpath(single_path):
                extra_files.append(self.download_file(url))
        metadata['extras'] = extra_files

        # Write to HTML file
        postfix = '.denied' if stop_flag else ''
        with open(self.get_path(INDEX_HTML+postfix), 'wb') as hfile:
            hfile.write(content)

        # Write manifest
        with open(self.get_path(INDEX_JSON+postfix), 'wb') as mfile:
            mfile.write(json.dumps(metadata))

        return self.download_to

    def get_path(self, file_name):
        """ Return full path of file (include containing directory) """
        return os.path.join(self.download_to,
                            os.path.basename(file_name))

    def prepare_directory(self):
        """ Create local directories if not existing """
        try:
            rmtree(self.download_to)
        except OSError:
            pass
        finally:
            os.makedirs(self.download_to)

    def download_file(self, url):
        """ Download image from given url and save to common location """
        file_url = url.strip()
        file_name = url.split('/')[-1].split('?')[0]
        if file_url.lower().find('http://') == -1:
            file_url = urljoin(self.url, file_url)
        lives = 3
        while lives:
            try:
                lives -= 1
                response = requests.get(file_url, proxies=self.proxies)
            except requests.ConnectionError:
                logger.error('Retry downloading file %s' % file_url)
        file_path = self.get_path(file_name)
        with open(file_path, 'wb') as bfile:
            bfile.write(response.content)
        return file_name

    def refine_content(self, content, custom_rules=None):
        """ rules should adapt formats:
                [(action, target, value),...]j
            actions:
                'replace'
        """
        content = content.replace('\n', '').strip()

        # Run custom rules first
        for rule in custom_rules:
            rg = re.compile(rule, re.IGNORECASE)
            content = rg.sub('', content)

        # then common rules...
        for rg in refine_rules:
            content = rg.sub('', content)

        return content
