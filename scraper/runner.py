from __future__ import unicode_literals

import json
import logging
from collections import OrderedDict

import os
import urlparse
import uuid

from django.utils import timezone
from lxml import etree

from django.utils.encoding import force_text

from scraper.config import TEMP_DIR, INDEX_JSON, INVALID_DATA
from scraper.extractor import Extractor
from scraper.utils import download_batch, get_link_info, Datum, get_content

logger = logging.getLogger(__name__)


class Page(object):
    """Hold information and logics for a crawled page."""

    def __init__(self, runner, url, depth, source, tag_name='html', **kwargs):
        """Initialize a page object."""
        self.runner = runner
        self.spider = runner.spider
        self.url = url
        self.depth = depth
        self.source = source
        self.extractor = Extractor(url, html=source, tag_name=tag_name,
                                   base_dir=self.runner.base_dir)

    def extract_data(self):
        """Extract data from page's content."""
        raise NotImplementedError()

    def find_expand_links(self):
        """
        Find expand links from page.

        Returns: dictionary in format {'link': depth}

        """
        # Only find expand links if does not reach spider's max_depth yet
        if self.depth < self.spider.crawl_depth:
            return {link['url']: self.depth + 1 for link in
                    self.extractor.extract_links(
                        self.spider.expand_links)
                    }
        return {}


class ListingPage(Page):
    """A listing page where we look for ItemData."""

    def extract_data(self):
        """
        Extract page's data.

        Returns: data extracted from page and found expand_links:
            {
                'data_item_name': [
                    # List of found items
                ]
            },
            {
                'expand_link_1': depth2,
                'expand_link_2': depth3
            }
        """
        logger.info("Start extracting listing page %s..." % self.url)
        # Find expand links
        self.expand_links = self.find_expand_links()

        # Get list of DataItem that need to be crawled.
        data_items = self.spider.data_items.all()

        # Init list of results
        data = {}
        new_links = set()
        # Find collector information for each data item and detail links.
        for data_item in data_items:
            data[data_item.name] = self.find_items_for(data_item)
            for item in data[data_item.name]:
                for collector in item["collectors"]:
                    for link in collector["links"]:
                        new_links.add(link)
        logger.info("Found {0} detail links".format(len(new_links)))
        # Download new links
        logger.info("Start download detail links...")
        page_sources = download_batch(new_links)
        # Extract data for all found items of all data_items
        for data_item in data_items:
            for item in data[data_item.name]:
                valid = self.extract_item_data(item, page_sources)
                if valid and item["data"] and \
                        item["data"].get("deferred_info", None):
                    self.download_deferred_info(item)
        # Filter empty results
        for item_name in data:
            data[item_name] = [item["data"] for item in data[item_name]
                               if item["data"]]
        # Write index.json file
        self.write_index(data)
        # Returns crawled data and found expand_links
        return data, self.expand_links

    def extract_item_data(self, item, page_sources):
        """
        Extract item's data from item's collectors, downloaded page_sources and
        also update expand_links if found new ones.

        item's data will also be validated and updated while extracting.

        Args:
            item: item's curernt information. In format:
                {'data': {}, 'collectors': [list_of_collectors]}
            page_sources: downloaded page sources for all item's related links.
            current listing page, in format:
                {url: depth}

        Returns: True if item is valid, if not returns False.
        """
        is_invalid = False
        for collector in item["collectors"]:
            # Create detailed pages for collector links.
            for link in collector["links"]:
                if link in page_sources:
                    collector["pages"].append(
                        DetailedPage(
                            runner=self.runner,
                            url=link,
                            depth=self.depth + 1,
                            source=page_sources[link],
                            parent=self,
                            collector=collector["collector"]
                        )
                    )
            # Extract data from detailed pages.
            for page in collector["pages"]:
                page_data, page_expand_links = page.extract_data(
                    deferred_download=True
                )
                self.aggregate_links(page_expand_links)
                # Check if page contains invalid data or not.
                if page_data == INVALID_DATA:
                    # Cancel the collector because some fields has
                    # invalid information.
                    item["data"] = {}
                    is_invalid = True
                    break
                # Merge page's data to item's data
                item["data"] = self.merge_data(item["data"], page_data)
            if is_invalid:
                # Break the collector loop because one of collector has
                # invalid data
                break
        return not is_invalid

    def aggregate_links(self, new_links):
        """
        Aggregate current expand links with new ones.

        Args:
            new_links: a dictionary of links in format {link:depth}
            depth: current depth of the page where new_links come from.

        Returns:

        """
        for link in new_links:
            depth = min(self.expand_links.get(link, self.spider.crawl_depth),
                        new_links[link])
            self.expand_links[link] = depth

    def find_items_for(self, data_item):
        """
        Find and collect information of all matched data_item in page.

        Args:
            data_item: DataItem object

        Returns: list of found data_item in format:
            {
                "data": {},  # Store extracted data for the item
                "collectors": []  # Store collectors' information
            }
        """
        results = []
        if data_item.base:
            # Find all base elements for the data_item
            base_elements = self.extractor.xpath(data_item.base)
        else:
            base_elements = [self.extractor.root]
        # Init list of found items.
        for element in base_elements:
            item = {
                "data": {},  # Store extracted data for the item
                "collectors": []  # Store collector's links for the item
            }
            # With each base element, get all collectors to collect item's
            # information
            collectors = data_item.collectors.all()
            for collector in collectors:
                item["collectors"].append(
                    self.get_collector_data(element, collector)
                )
            results.append(item)
        return results

    def get_collector_data(self, base, collector):
        """
        Collect data from given collector object.

        Args:
            collector: Collector object.

        Returns: collector's data in format:
            {
                "links": [list of collector's links],
                "pages": [list of DetailedPage]
            }
        """
        collector_data = {
            "collector": collector,
            "links": [],
            "pages": []
        }
        if not collector.link:
            # Collector's data is extracted from base, so we created a detailed
            # page with html = base's html
            collector_data["pages"] = [
                DetailedPage(runner=self.runner,
                             url=self.url,
                             depth=self.depth,
                             source=etree.tounicode(base),
                             tag_name=base.tag,
                             parent=self,
                             collector=collector)]
        else:
            # Find all link elements from collector's link xpath (relative one)
            try:
                link_elements = base.xpath(collector.link)
            except etree.XPathEvalError:
                logger.exception(
                    'Invalue XPath value \'{0}\' for collector {1}'.format(
                        collector.link, collector.id))
                link_elements = []
            links = []
            for element in link_elements:
                link = self.get_link_from_element(element)
                if link:
                    links.append(link)
            collector_data["links"] = links
        return collector_data

    def get_link_from_element(self, element):
        """
        Returns link from element.

        Args:
            element: etree element

        Returns:
            None if link is invalid, if not returns link after refined.
        """
        link = get_link_info(element, make_root=False)
        if link is None:
            return
        url = link['url'].strip().rstrip('/').split('#', 1)[0]
        scheme = urlparse.urlparse(url).scheme.lower()
        if scheme not in ('', 'http', 'https'):
            return
        return self.extractor.complete_url(link['url'])

    def merge_data(self, result, item):
        """
        Merge item into result recursively.

        Args:
            result: dictionary that store result
            item: dictionary that need to be merged.

        Returns: merged result.
        """
        for key in item:
            if isinstance(item[key], dict):
                if key not in result:
                    result[key] = {}
                self.merge_data(result[key], item[key])
            elif isinstance(item[key], list):
                if key not in result:
                    result[key] = []
                result[key] += item[key]
            else:
                result[key] = item[key]
        return result

    def download_deferred_info(self, item):
        """
        Download item's images & binaries. Downloaded results will also be
        updated to item's data.

        Args:
            item: item's current information in format:
                {'data': {}, 'collectors': [list_of_collectors]}

        Returns: updated item.
        """
        logger.info("Start downloading deferred items...")
        deferred_info = item["data"]["deferred_info"]
        # Download binary files
        for field_name, urls in deferred_info["media"].items():
            paths = []
            for url in urls:
                file_name = self.extractor.download_file(url)
                paths.append(os.path.join(self.extractor._uuid, file_name))
            item["data"]["content"][field_name] = paths
            item["data"]["media"].extend(paths)
        # Download images
        for field_name, images_info in deferred_info["images"].items():
            elements = images_info["elements"]
            for element in elements:
                item["data"]["images"].extend(
                    self.extractor.extract_images(element)
                )
            # Get new content for item's field data after downloading.
            item["data"]["content"][field_name] = get_content(
                elements, images_info["data_type"]
            )
        # Removed deffered info from item
        item["data"].pop("deferred_info")
        return item

    def write_index(self, data):
        """Write index file with page's result."""
        result_path = self.extractor.location
        if not os.path.exists(result_path):
            os.makedirs(result_path)
        file_path = os.path.join(result_path, INDEX_JSON)
        with open(file_path, 'w') as index_file:
            index_file.write(json.dumps({
                "url": self.url,
                "time": timezone.now().strftime("%Y/%m/%d - %H:%M"),
                "data": data
            }))


class DetailedPage(Page):
    """A detailed page where ItemData's information resides in."""

    def __init__(self, runner, url, depth, source, tag_name='html', **kwargs):
        super(DetailedPage, self).__init__(
            runner, url, depth, source, tag_name, **kwargs)
        self.parent = kwargs.get("parent", None)
        self.collector = kwargs.get("collector", None)
        if self.parent:
            # Use same storage location with listing page.
            self.extractor._uuid = self.parent.extractor._uuid
            self.extractor._location = self.parent.extractor._location

    def extract_data(self, deferred_download=True):
        """
        Extract data from page.
        Args:
            deferred_download: if True, media and binaries will not be
            downloaded.

        Returns: extracted data, expand_links. E.g:
            {'content': {...},
             'images': images,
             'media': media,},
             ['expand_link1', 'expand_link2',...]
        """
        logger.info("Start extracting detailed page {0}".format(self.url))

        # Find expand links
        expand_links = self.find_expand_links()

        # Extract data from page with given set of selectors.
        selector_dict = self.collector.selector_dict
        data, result_path = self.extractor.extract_content(
            get_image=self.collector.get_image,
            selectors=selector_dict,
            replace_rules=self.collector.replace_rules,
            deferred_download=deferred_download
        )
        if data == INVALID_DATA:
            # The data item is invalid
            return data, expand_links
        return data, expand_links


class SpiderRunner(object):
    """A runner that do crawling, scraping,... job."""

    def __init__(self, spider, task_id=""):
        """Initialize a runner object."""
        self.spider = spider
        self.urls = self.init_urls(spider.get_root_urls())
        self.pages = []
        self.crawled = set()
        self.base_dir = os.path.join(TEMP_DIR, spider.storage_location)
        if not task_id:
            task_id = self.generate_task_id()
        self.task_id = task_id

    @staticmethod
    def generate_task_id():
        """Generate a new task id for the runner."""
        return str(uuid.uuid4())

    def init_urls(self, urls):
        """Initiate urls dict from list of root urls."""
        return OrderedDict([(url, 1) for url in urls])

    def run(self):
        """Start the spider."""
        logger.info('START CRAWLING SPIDER: {0}'.format(
            force_text(self.spider)))
        data = {}
        data_dirs = []
        while self.urls:
            self.pages = self.download_pages(self.urls)
            self.urls = OrderedDict()
            for page in self.pages:
                data_dirs.append(page.extractor.location)
                page_data, expand_links = page.extract_data()
                self.combine_data(data, page_data)
                # Add page's url to crawled list
                self.crawled.add(page.url)
                # Aggregate links
                for link in expand_links:
                    if link not in self.urls and link not in self.crawled:
                        self.urls[link] = expand_links[link]
        return Datum(content=data, path=data_dirs)

    def combine_data(self, data, page_data):
        """Combine current data with page's data."""
        for item_name in page_data:
            if item_name not in data:
                data[item_name] = []
            data[item_name] += page_data[item_name]

    def download_pages(self, urls):
        """
        Download all current urls and create page objects.

        Args:
            urls: urls dictionary in format {url:depth}

        Returns: list of page objects

        """
        logger.info("Start downloading root/expand urls")
        page_sources = download_batch(urls.keys())
        pages = []
        for url in urls:
            if url in page_sources:
                page = ListingPage(
                    runner=self,
                    url=url,
                    depth=self.urls[url],
                    source=page_sources[url]
                )
                pages.append(page)
        return pages
