from __future__ import unicode_literals

import json
import os
from collections import OrderedDict
from copy import deepcopy
from os.path import join
from shutil import rmtree
from zipfile import ZipFile

from django import VERSION
from django.conf import settings
from django.core.files.storage import default_storage as storage
from django.test import TestCase, LiveServerTestCase
from django.utils import timezone
from django.utils.encoding import force_text
from django.utils.translation import ugettext_lazy as _

from lxml import etree

from scraper.runner import Page, ListingPage, DetailedPage, SpiderRunner
from scraper import utils, models, config
from scraper.config import INVALID_DATA, INDEX_JSON, TEMP_DIR, CRAWL_ROOT
from scraper.extractor import Extractor

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                        'data')

PRIOR_18 = VERSION < (1, 8)


def get_path(file_name):
    return os.path.join(DATA_DIR, file_name)


def exists(path):
    if storage.exists(path):
        return True
    else:
        parent, name = path.rstrip('/').rsplit('/', 1)
        res = storage.listdir(parent)
        return name in res[0] or name in res[1]


class BaseTestCase(TestCase):
    """A base test case that solves fixtures setup issue on django prior to 1.8.
    """

    @classmethod
    def setUpClass(cls):
        super(BaseTestCase, cls).setUpClass()
        if not PRIOR_18:
            # Data should be setup once on class level to improve performance.
            cls.setupData(cls)

    def setUp(self):
        super(BaseTestCase, self).setUp()
        if PRIOR_18:
            self.setupData(self)

    @staticmethod
    def setupData(self):
        """Setup data for tests."""
        pass


class ProxyServerTests(TestCase):
    def test_create(self):
        proxy = models.ProxyServer(
            name='Test Proxy',
            address='Proxy address',
            port=8080,
            protocol='http'
        )
        proxy.save()
        self.assertNotEqual(proxy.pk, None)


def get_extractor(file_name, url=''):
    html = open(get_path(file_name), 'r').read()
    url = url.strip() or 'http://127.0.0.1/'
    return Extractor(url, html=html)


class ExtractorLocalTests(TestCase):
    yc_0_html = os.path.join('yc', 'yc.0.html')
    yc_0_html_path = get_path(yc_0_html)
    yc_a0_html_path = get_path(os.path.join('yc', 'yc.a0.html'))

    @classmethod
    def setUpClass(self):
        self.extractor = get_extractor(self.yc_0_html)

    @classmethod
    def tearDownClass(self):
        if os.path.exists(self.extractor.location):
            rmtree(self.extractor.location)

    def test_parse_content(self):
        self.assertNotEqual(self.extractor._uuid, '')
        self.assertNotEqual(self.extractor.root, None)

    def test_parse_invalid_content(self):
        for val in ['', None, 'Anything', '<html>']:
            res = self.extractor.parse_content(val)
            self.assertNotEqual(res, None)

    def test_unique_location(self):
        new_extractor = Extractor('http://127.0.0.1/', html='<html></html>')
        self.assertNotEqual(self.extractor.location, new_extractor.location)

    def test_complete_url_no_http(self):
        tmp = self.extractor._url
        self.extractor._url = 'http://google.com'
        url = self.extractor.complete_url('search/me')
        self.assertEqual(url, 'http://google.com/search/me')
        self.extractor._url = tmp

    def test_complete_url_good(self):
        url = self.extractor.complete_url('http://google.com')
        self.assertEqual(url, 'http://google.com')

    def test_complete_url_https(self):
        url = self.extractor.complete_url('https://google.com')
        self.assertEqual(url, 'https://google.com')

    def test_extract_links_unique(self):
        links = self.extractor.extract_links()
        self.assertEqual(len(links), 74)
        link = {'url': 'https://posthaven.com/', 'text': ''}
        self.assertEqual(link in links, True)

    def test_extract_article(self):
        html = open(self.yc_a0_html_path, 'r').read()
        extr = Extractor('http://127.0.0.1/', html=html)
        data = extr.extract_article()
        self.assertNotEqual(data['title'], '')
        self.assertEqual(data['content'][:6], '<html>')

    def test_get_path(self):
        file_path = self.extractor.get_path(__file__)
        self.assertGreater(len(file_path), 0)

    def test_invalid_xpath(self):
        res = self.extractor.xpath('~something-wrong')
        self.assertEqual(res, [])
        res = self.extractor.xpath('')
        self.assertEqual(res, [])

    def test_refine_content(self):
        with open(self.yc_0_html_path, 'r') as index:
            content = index.read().decode("utf-8")
            self.assertNotEqual(content.find("<section id='bio'>"), -1)
            self.assertNotEqual(content.find("<section id='contributors'>"),
                                -1)
            self.assertNotEqual(content.find("<div class='archive-link'>"), -1)
            rules = ['<section .*?>', "<div class='archive-link'>"]
            refined = self.extractor.refine_content(content, rules)
        self.assertEqual(refined.find("<section id='bio'>"), -1)
        self.assertEqual(refined.find("<section id='contributors'>"), -1)
        self.assertEqual(refined.find("<div class='archive-link'>"), -1)

    def test_refine_content_no_rule(self):
        with open(self.yc_0_html_path, 'r') as index:
            content = index.read()
            rules = []
            refined = self.extractor.refine_content(content, rules)
        self.assertEqual(content, refined)


class ExtractorOnlineTests(LiveServerTestCase):
    def get_url(self, path):
        """Returns complete URL of live server to path."""
        return self.live_server_url + os.path.join(
            settings.TEST_DATA_URL, path)

    @classmethod
    def tearDownClass(self):
        super(ExtractorOnlineTests, self).tearDownClass()

    def tearDown(self):
        location = self.extractor.location
        if os.path.exists(location):
            if os.path.isdir(location):
                rmtree(location)
            else:
                os.remove(location)

    def setUp(self):
        self.yc_0_html_path = "{0}{1}yc/yc.0.html".format(
            self.live_server_url, settings.TEST_DATA_URL)
        self.extractor = Extractor(self.yc_0_html_path)
        self.selectors = {
            'post': {
                "xpath": "//div[@id='main']/article[@class='post']",
                "data_type": "text"
            },
        }

    def test_download_file(self):
        FILE_URL = self.get_url('yc/simple_page.txt')
        file_name = self.extractor.download_file(FILE_URL)
        self.assertTrue(file_name.endswith(".txt"))

    def test_download_file_failed(self):
        FILE_URL = self.get_url('yc/not_exist.txt')
        file_name = self.extractor.download_file(FILE_URL)
        self.assertEqual(file_name, None)

    def test_extract_content_basic(self):
        data, path = self.extractor.extract_content(self.selectors)
        self.assertNotEqual(path, '')
        self.assertEqual(os.path.exists(path), False)
        self.assertGreater(len(data['content']['post']), 0)

    def test_extract_content_tbody(self):
        selectors = {
            'post': {
                "xpath": "//div[@id='main']/tbody/article[@class='post']",
                "data_type": "text"
            }
        }
        data, path = self.extractor.extract_content(selectors)
        self.assertNotEqual(path, '')
        self.assertGreater(len(data['content']['post']), 0)

    def test_extract_content_with_ua(self):
        UA = 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36'
        self.extractor = Extractor(self.yc_0_html_path, user_agent=UA)
        data, path = self.extractor.extract_content(self.selectors)
        self.assertGreater(len(data['content']['post']), 0)
        self.assertNotEqual(path, '')

    def test_extract_content_blackword(self):
        bw = ['panicked', 'phone']
        selectors = deepcopy(self.selectors)
        selectors["post"]["black_words"] = bw
        data, path = self.extractor.extract_content(selectors)
        self.assertEqual(data, INVALID_DATA)

    def test_extract_content_with_image(self):
        custom_selector = {
            'post': {
                "xpath": "//div[@id='main']/article[@class='post']",
                "data_type": "html"
            },
        }
        data, path = self.extractor.extract_content(custom_selector)
        self.assertEqual(path, self.extractor.location)
        self.assertEqual(len(os.listdir(path)), 2)

    def test_extract_content_meta(self):
        custom_selectors = self.selectors.copy()
        custom_selectors['title'] = {
            "xpath": "(//h2/a)[1]",
            "data_type": "text"
        }
        data, path = self.extractor.extract_content(custom_selectors)
        self.assertNotEqual(path, '')
        # Verify the meta file
        self.assertEquals(
            data['content']['title'],
            ["Shift Messenger (YC W15) Makes It Easy For Workers To Swap Hours"]
        )

    def test_extract_content_media(self):
        custom_selectors = self.selectors.copy()
        custom_selectors['extra'] = {
            "xpath": "(//img)[1]/@src",
            "data_type": "binary"
        }
        data, path = self.extractor.extract_content(custom_selectors)

        self.assertEqual(path, self.extractor.location)
        self.assertEqual(len(os.listdir(path)), 1)

    def test_download_error(self):
        res = self.extractor.download_file(
            'http://github.com/not.exist-for-sure-acb2afq1/')
        self.assertIn(res, (None, ''))


class SpiderMock(object):
    def __init__(self, target=['//a'], expand=[]):
        self.target_links = target
        self.expand_links = expand


class CrawlUrlTests(BaseTestCase):
    """Tests for CrawlUrl model."""

    fixtures = ["spider.json", "crawl_url.json"]

    @staticmethod
    def setupData(self):
        super(CrawlUrlTests, self).setupData(self)
        self.spider = models.Spider.objects.get(pk=2)

    def test_create(self):
        """Test create a new CrawlUrl object."""
        craw_url = models.CrawlUrl.objects.create(
            spider=self.spider,
            base="https://blog.ycombinator.com/?page={0}",
            number_pattern='[1, 5, 1]',
            text_pattern=''
        )
        self.assertEqual(force_text(craw_url),
                         "https://blog.ycombinator.com/?page={0}")

    def test_generate_urls(self):
        url = models.CrawlUrl.objects.get(pk=2)
        self.assertEqual(list(url.generate_urls()),
                         ['https://blog.ycombinator.com/?page=1',
                          'https://blog.ycombinator.com/?page=2',
                          'https://blog.ycombinator.com/?page=3',
                          'https://blog.ycombinator.com/?page=4'])


class DataItemTests(BaseTestCase):
    fixtures = ["spider.json"]

    @staticmethod
    def setupData(self):
        super(DataItemTests, self).setupData(self)
        self.spider = models.Spider.objects.get(pk=1)

    def test_create(self):
        data_item = models.DataItem.objects.create(
            name="BlogPost",
            base="//*[@id=\"main\"]/article",
            spider=self.spider
        )
        self.assertEqual(force_text(data_item),
                         "{0} - {1}".format(self.spider.name, data_item.name))


class CollectorTests(BaseTestCase):
    fixtures = ["spider.json", "data_item.json", "collector.json",
                "selector.json"]

    @staticmethod
    def setupData(self):
        super(CollectorTests, self).setupData(self)
        self.spider = models.Spider.objects.get(pk=1)
        self.blog_item = models.DataItem.objects.get(pk=1)

    def test_create(self):
        collector = models.Collector.objects.create(
            link="",
            get_image=True,
            replace_rules=None,
            data_item=self.blog_item
        )
        self.assertEqual(force_text(collector), _("Collector: {0}-{1}").format(
            force_text(self.blog_item), ""
        ))

    def test_selector_dict(self):
        collector = models.Collector.objects.get(pk=3)
        data_xpaths = collector.selector_dict
        self.assertEqual(len(data_xpaths), 4)
        self.assertEqual(set(data_xpaths.keys()),
                         {'title', 'url', 'content', 'author'})


class SelectorTests(TestCase):
    fixtures = ["collector.json", "selector.json", "data_item.json",
                "spider.json"]

    def test_create(self):
        collector = models.Collector.objects.get(pk=1)
        selector = models.Selector.objects.create(
            key="title",
            xpath="./header/div/h2/a",
            attribute="",
            data_type="text",
            required_words=None,
            black_words=None,
            collector=collector
        )
        self.assertEqual(force_text(selector),
                         _('Selector: {0} - Collector: {1}').format(
                             selector.key,
                             force_text(collector)
                         ))

    def test_to_dict(self):
        selector = models.Selector.objects.get(pk=6)
        selector_dict = selector.to_dict()
        self.assertEqual(selector_dict, {"key": "url",
                                         "xpath": ".//header/div/h2/a",
                                         "attribute": "href",
                                         "data_type": "text",
                                         "required_words": None,
                                         "black_words": None
                                         })


class GeneralPageTests(BaseTestCase):
    """Tests for general page."""

    fixtures = ["spider.json"]

    @classmethod
    def setUpClass(cls):
        super(GeneralPageTests, cls).setUpClass()

    @staticmethod
    def setupData(self):
        super(GeneralPageTests, self).setupData(self)
        self.spider = models.Spider.objects.get(pk=2)
        self.runner = SpiderRunner(self.spider, task_id="task-id")
        self.page_source = open(
            get_path(os.path.join('yc', 'yc.0.html')), 'r').read()
        self.page = Page(self.runner, "http://test.url", 1, self.page_source)

    def test_init_general_page(self):
        self.assertEqual(self.page.spider, self.spider)
        self.assertIsInstance(self.page.extractor, Extractor)
        self.assertEqual(self.page.extractor.base_dir, self.runner.base_dir)

    def test_extract_data(self):
        with self.assertRaises(NotImplementedError):
            self.page.extract_data()

    def test_find_expand_links(self):
        expand_links = self.page.find_expand_links()
        self.assertEqual(expand_links, {'http://test.url/yc.1.html': 2})


class DetailedPageTests(LiveServerTestCase):
    """Tests for DetailedPage"""

    fixtures = ["spider.json", "crawl_url.json", "collector.json",
                "selector.json", "data_item.json"]

    def setUp(self):
        super(DetailedPageTests, self).setUp()
        self.yc_0_url = "{0}{1}yc/yc.0.html".format(
            self.live_server_url, settings.TEST_DATA_URL)
        self.yc_a0_url = "{0}{1}yc/yc.a0.html".format(
            self.live_server_url, settings.TEST_DATA_URL)
        self.spider = models.Spider.objects.get(pk=3)
        self.collector = models.Collector.objects.get(pk=2)
        self.runner = SpiderRunner(self.spider, task_id="task-id")
        yc_0_source = open(get_path(os.path.join('yc', 'yc.0.html')), 'r') \
            .read()
        self.yc_a0_source = open(
            get_path(os.path.join('yc', 'yc.a0.html')), 'r').read()
        self.listing_page = ListingPage(self.runner, self.yc_0_url, 1,
                                        yc_0_source)
        self.page = DetailedPage(self.runner, self.yc_a0_url, 2,
                                 self.yc_a0_source,
                                 parent=self.listing_page,
                                 collector=self.collector)

    def tearDown(self):
        # Remove extractor's location dir
        if os.path.exists(self.page.extractor.location):
            rmtree(self.page.extractor.location)

    def test_init_detailed_page(self):
        self.assertEqual(self.page.collector, self.collector)
        self.assertEqual(self.page.parent, self.listing_page)
        self.assertEqual(self.page.extractor._uuid,
                         self.listing_page.extractor._uuid)
        self.assertEqual(self.page.extractor._location,
                         self.listing_page.extractor._location)

    def test_extract_data(self):
        results = self.page.extract_data(deferred_download=False)
        self.assertEqual(len(results), 2)
        data, expand_links = results
        self.assertEqual(expand_links, {})
        self.assertEqual(set(data.keys()), {"content", "images", "media"})
        self.assertEqual(data["media"], [])
        self.assertEqual(len(data["images"]), 1)
        self.assertEqual(set(data["content"].keys()), {"content", "author"})
        self.assertEqual(data["content"]['author'], ['Y Combinator'])

    def test_extract_data_invalid(self):
        # Get a collector that its selector has black_words filter.
        collector = models.Collector.objects.get(pk=7)
        self.page = DetailedPage(self.runner, self.yc_a0_url, 2,
                                 self.yc_a0_source,
                                 parent=self.listing_page,
                                 collector=collector)
        results = self.page.extract_data(deferred_download=False)
        self.assertEqual(len(results), 2)
        data, expand_links = results
        self.assertEqual(data, INVALID_DATA)

    def test_extract_data_with_deferred_download(self):
        results = self.page.extract_data(deferred_download=True)
        self.assertEqual(len(results), 2)
        data, expand_links = results
        self.assertEqual(expand_links, {})
        self.assertEqual(set(data.keys()), {"content", "images", "media",
                                            "deferred_info"})
        self.assertEqual(data["media"], [])
        self.assertEqual(data["images"], [])
        self.assertEqual(set(data["deferred_info"].keys()), {"images", "media"})
        self.assertIn("content", data["deferred_info"]["images"])
        content_images = data["deferred_info"]["images"]["content"]
        self.assertIn("elements", content_images)
        self.assertEqual(set(content_images.keys()), {"elements", "data_type"})
        self.assertEqual(len(content_images["elements"]), 1)
        self.assertEqual(data["deferred_info"]["media"], {})
        self.assertEqual(set(data["content"].keys()), {"content", "author"})
        self.assertEqual(data["content"]['author'], ['Y Combinator'])


class ListingPageTests(LiveServerTestCase):
    """Tests for ListingPage"""
    fixtures = ["spider.json", "crawl_url.json", "collector.json",
                "selector.json", "data_item.json"]

    def setUp(self):
        super(ListingPageTests, self).setUp()
        self.yc_0_url = "{0}{1}yc/yc.0.html".format(
            self.live_server_url, settings.TEST_DATA_URL)
        self.yc_a0_url = "{0}{1}yc/yc.a0.html".format(
            self.live_server_url, settings.TEST_DATA_URL)
        self.spider = models.Spider.objects.get(pk=3)
        self.runner = SpiderRunner(self.spider, task_id="task-id")
        self.yc_0_source = open(
            get_path(os.path.join('yc', 'yc.0.html')), 'r').read()
        self.yc_a0_source = open(
            get_path(os.path.join('yc', 'yc.a0.html')), 'r').read()
        self.page = ListingPage(self.runner, self.yc_0_url, 1, self.yc_0_source)
        self.data_item = models.DataItem.objects.get(pk=3)
        self.base = self.page.extractor.xpath(self.data_item.base)[0]
        self.collector = models.Collector.objects.get(pk=5)
        self.page_sources = {
            self.yc_0_url: self.yc_0_source,
            self.yc_a0_url: self.yc_a0_source
        }

    def tearDown(self):
        # Remove extractor's location dir
        if os.path.exists(self.page.extractor.location):
            rmtree(self.page.extractor.location)

    def test_get_collector_data_with_valid_link(self):
        # Get collector with link
        collector = self.collector
        collector_data = self.page.get_collector_data(self.base, collector)
        self.assertEqual(set(collector_data.keys()),
                         {"collector", "links", "pages"})
        self.assertEqual(collector_data["collector"], collector)
        self.assertEqual(collector_data["pages"], [])
        self.assertEqual(collector_data["links"],
                         ['http://127.0.0.1:9999/data/yc/yc.a0.html'])

    def test_get_collector_data_with_invalid_link(self):
        # Get collector with link
        collector = self.collector
        collector.link = "//ns:a"
        collector_data = self.page.get_collector_data(self.base, collector)
        self.assertEqual(set(collector_data.keys()),
                         {"collector", "links", "pages"})
        self.assertEqual(collector_data["collector"], collector)
        self.assertEqual(collector_data["pages"], [])
        self.assertEqual(collector_data["links"], [])

    def test_get_collector_data_without_link(self):
        # Get collector without link
        collector = models.Collector.objects.get(pk=4)
        collector_data = self.page.get_collector_data(self.base, collector)
        self.assertEqual(set(collector_data.keys()),
                         {"collector", "links", "pages"})
        self.assertEqual(collector_data["collector"], collector)
        self.assertEqual(collector_data["links"], [])
        self.assertEqual(len(collector_data["pages"]), 1)
        page = collector_data["pages"][0]
        self.assertEqual(page.url, self.page.url)
        self.assertEqual(page.source, etree.tounicode(self.base))

    def test_find_items_with_base(self):
        items = self.page.find_items_for(self.data_item)
        self.assertEqual(len(items), 3)
        item = items[0]
        self.assertEqual(set(item.keys()), {"data", "collectors"})
        self.assertEqual(item["data"], {})
        collectors = item["collectors"]
        self.assertEqual(len(collectors), 2)

    def test_find_items_without_base(self):
        data_item = models.DataItem.objects.get(pk=5)
        items = self.page.find_items_for(data_item)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(set(item.keys()), {"data", "collectors"})
        self.assertEqual(len(item["collectors"]), 1)

    def test_extract_data(self):
        data, expand_links = self.page.extract_data()
        self.assertEqual(expand_links,
                         {'http://127.0.0.1:9999/data/yc/yc.1.html': 2})
        self.assertEqual(
            set(data.keys()),
            {'ContributorList', 'NON-YC-W15 BlogPost', 'YC-W15 BlogPost'})
        # Check ContributorList
        self.assertEqual(len(data["ContributorList"]), 1)
        self.assertEqual(data["ContributorList"][0]["media"], [])
        self.assertEqual(data["ContributorList"][0]["images"], [])
        self.assertEqual(set(data["ContributorList"][0]["content"].keys()),
                         {"content"})
        # Check NON-YC-W15 BlogPost
        self.assertEqual(len(data["NON-YC-W15 BlogPost"]), 1)
        self.assertEqual(data["NON-YC-W15 BlogPost"][0]["media"], [])
        self.assertEqual(data["NON-YC-W15 BlogPost"][0]["images"], [])
        self.assertEqual(data["NON-YC-W15 BlogPost"][0]["content"]["title"],
                         ['YC Digest - 2/20-2/26'])
        # Check YC-W15 BlogPost
        self.assertEqual(len(data["YC-W15 BlogPost"]), 2)
        self.assertEqual(len(data["YC-W15 BlogPost"][0]["media"]), 1)
        self.assertIn("2669c715ecb8fa24f957ce7e3605f125697d50d0.html",
                      data["YC-W15 BlogPost"][0]["media"][0])
        self.assertEqual(data["YC-W15 BlogPost"][0]["images"],
                         [('292ccf426955da481aecada2ea1022cca2c1438c.jpg',
                           {'caption': ''})])
        self.assertEqual(data["YC-W15 BlogPost"][0]["content"]['title'],
                         ['Shift Messenger (YC W15) Makes It Easy For Workers '
                          'To Swap Hours'])
        self.assertEqual(len(data["YC-W15 BlogPost"][1]["media"]), 1)
        self.assertIn("2c68001e37ac73a00cca98b8ecf28bdd246465f2.html",
                      data["YC-W15 BlogPost"][1]["media"][0])
        self.assertEqual(data["YC-W15 BlogPost"][1]["images"],
                         [('66b3db3eeb02a148a8618d65621683addc1812f8.png',
                           {'caption': ''})])
        self.assertEqual(data["YC-W15 BlogPost"][1]["content"]['title'],
                         [u'YesGraph (YC W15) Raises A Million To Build A '
                          u'Better Referral System For Mobile Apps'])
        # Check if index file path exists or not.
        self.assertTrue(os.path.isfile(join(self.page.extractor.location,
                                            INDEX_JSON)))

    def test_extract_valid_item_data(self):
        items = self.page.find_items_for(self.data_item)
        item = items[0]
        is_valid = self.page.extract_item_data(item, self.page_sources)
        data = item['data']
        self.assertTrue(is_valid)
        self.assertEqual(set(data.keys()),
                         {'content', 'images', 'deferred_info', 'media'})
        self.assertEqual(data['images'], [])
        self.assertEqual(data['media'], [])
        self.assertEqual(set(data['deferred_info'].keys()), {"images", "media"})
        content = data["content"]
        self.assertEqual(set(content.keys()),
                         {"url", "content", "author", "title"})
        self.assertEqual(content["url"], ['yc.a0.html'])
        self.assertEqual(content["author"], ['Y Combinator'])
        self.assertEqual(content["title"],
                         ['Shift Messenger (YC W15) Makes It Easy For Workers '
                          'To Swap Hours'])
        self.assertEqual(len(content["content"]), 1)
        self.assertIn('<div class="post-body" id="post_body_816534">',
                      content["content"][0])

    def test_extract_invalid_item_data(self):
        data_item = models.DataItem.objects.get(pk=4)
        item = self.page.find_items_for(data_item)[0]
        is_valid = self.page.extract_item_data(item, self.page_sources)
        self.assertFalse(is_valid)
        self.assertEqual(item["data"], {})

    def test_aggregate_links(self):
        self.page.expand_links = {"http://link1.com": 2, "http://link2.com": 2}
        new_links = {"http://link1.com": 3, "https://link3.com": 3}
        self.page.aggregate_links(new_links)
        self.assertEqual(self.page.expand_links,
                         {"http://link1.com": 2, "http://link2.com": 2,
                          "https://link3.com": 3})

    def test_get_link_from_element(self):
        element = self.base.xpath(self.collector.link)[0]
        link = self.page.get_link_from_element(element)
        self.assertEqual(link, "http://127.0.0.1:9999/data/yc/yc.a0.html")
        # Invalid element
        self.assertIsNone(self.page.get_link_from_element(None))
        # Not http/https link
        element = etree.fromstring('<a href="ftp://host.com/abc.txt">File</a>')
        self.assertIsNone(self.page.get_link_from_element(element))

    def test_merge_data(self):
        result = {"content": {"Item 1": [{"id": 1, "title": "Item 1.1"}],
                              "Item 2": [{"id": 1, "title": "Item 2.1"}]},
                  "media": ["/tmp/file1.txt"]}
        item = {"content": {"Item 1": [{"id": 2, "title": "Item 1.2"}],
                            "Item 3": [{"id": 1, "title": "Item 3.1"}]},
                "media": ["/tmp/file2.txt"],
                "images": ["/tmp/img1.jpg", "/tmp/img2.jpg"]}
        result = self.page.merge_data(result, item)
        self.assertEqual(
            result,
            {u'content': {u'Item 3': [{u'id': 1, u'title': u'Item 3.1'}],
                          u'Item 2': [{u'id': 1, u'title': u'Item 2.1'}],
                          u'Item 1': [{u'id': 1, u'title': u'Item 1.1'},
                                      {u'id': 2, u'title': u'Item 1.2'}]},
             'media': ['/tmp/file1.txt', '/tmp/file2.txt'],
             'images': ['/tmp/img1.jpg', '/tmp/img2.jpg']})

    def test_download_deferred_info(self):
        items = self.page.find_items_for(self.data_item)
        item = items[0]
        self.page.extract_item_data(item, self.page_sources)
        item = self.page.download_deferred_info(item)
        data = item["data"]
        self.assertEqual(set(data.keys()), {'content', 'images', 'media'})
        self.assertEqual(data["images"],
                         [('292ccf426955da481aecada2ea1022cca2c1438c.jpg',
                           {'caption': ''})])
        self.assertIn('292ccf426955da481aecada2ea1022cca2c1438c.jpg',
                      data["content"]["content"][0])

    def test_write_index(self):
        data = {"content": []}
        self.page.write_index(data)
        file_path = join(self.page.extractor.location, INDEX_JSON)
        self.assertTrue(os.path.isfile(file_path))
        with open(file_path) as inp:
            file_data = json.loads(inp.read())
            self.assertEqual(set(file_data.keys()), {"url", "time", "data"})
            self.assertEqual(file_data["data"], data)


class SpiderRunnerTests(LiveServerTestCase):
    """Tests for SpiderRunner"""

    fixtures = ["spider.json", "crawl_url.json", "collector.json",
                "selector.json", "data_item.json"]

    def setUp(self):
        super(SpiderRunnerTests, self).setUp()
        self.spider = models.Spider.objects.get(pk=3)
        self.runner = SpiderRunner(self.spider)

    def test_init_runner(self):
        self.assertEqual(self.runner.spider, self.spider)
        self.assertEqual(self.runner.pages, [])
        self.assertEqual(self.runner.crawled, set([]))
        self.assertEqual(self.runner.base_dir,
                         join(TEMP_DIR, self.spider.storage_location))
        self.assertIsNotNone(self.runner.task_id)

    def test_generate_task_id(self):
        task_id = self.runner.generate_task_id()
        self.assertIsNotNone(task_id)

    def test_init_urls(self):
        urls = self.runner.init_urls(["http://url1.com", "http2://url2.com"])
        self.assertEqual(urls, OrderedDict({
            "http://url1.com": 1,
            "http2://url2.com": 1
        }))

    def test_combine_data(self):
        data = {"Item 1": [{"id": 1}]}
        page_data = {"Item 1": [{"id": 2}], "Item 2": [{"id": 1}]}
        self.runner.combine_data(data, page_data)
        self.assertEqual(data, {'Item 2': [{'id': 1}],
                                'Item 1': [{'id': 1}, {'id': 2}]})

    def test_download_pages(self):
        pages = self.runner.download_pages(self.runner.urls)
        self.assertEqual(len(pages), 1)
        page = pages[0]
        self.assertIsInstance(page, ListingPage)
        self.assertEqual(page.depth, 1)

    def test_run(self):
        data = self.runner.run()
        self.assertIsInstance(data, utils.Datum)
        self.assertIn("path", data.extras)
        self.assertEqual(len(data.extras['path']), 3)
        self.assertEqual(
            set(data.content.keys()),
            {'ContributorList', 'NON-YC-W15 BlogPost', 'YC-W15 BlogPost'})


class SpiderTests(LiveServerTestCase):
    fixtures = ["spider.json", "crawl_url.json", "collector.json",
                "selector.json", "data_item.json"]

    def setUp(self):
        self.compress_option = models.COMPRESS_RESULT
        models.COMPRESS_RESULT = False
        self.spider = models.Spider.objects.get(pk=3)

    def tearDown(self):
        models.COMPRESS_RESULT = self.compress_option

    def test_storage_location(self):
        now = timezone.now()
        self.assertEqual(self.spider.storage_location,
                         os.path.join(CRAWL_ROOT, now.strftime('%Y/%m/%d')))

    def test_get_proxy(self):
        self.assertIsNone(self.spider.get_proxy())

    def get_path(self, location):
        if hasattr(storage, 'base_location'):
            return os.path.join(storage.base_location, location)
        else:
            return location

    def test_crawl(self):
        result = self.spider.start('anything')
        self.assertEqual(len(result.data['results']), 1)
        self.assertEqual(len(result.data['results'][0]['content']), 3)
        self.assertGreater(result.other.pk, 0)

        # Self cleanup
        path = result.other.local_path
        if hasattr(storage, 'base_location'):
            rmtree(self.get_path(path))
        else:
            if storage.exists(path):
                storage.delete(path)

    def test_crawl_zip(self):
        models.COMPRESS_RESULT = True
        result = self.spider.start('anything')
        self.assertEqual(len(result.data['results']), 1)
        self.assertEqual(len(result.data['results'][0]['content']), 3)
        self.assertGreater(result.other.pk, 0)

        path = result.other.local_path
        self.assertIn('.zip', path)
        self.assertEqual(storage.exists(path), True)
        zfile = ZipFile(join(storage.base_location, path))
        self.assertEquals(len(zfile.namelist()), 15)

        # Self cleanup
        if hasattr(storage, 'base_location'):
            os.remove(self.get_path(path))
        else:
            if storage.exists(path):
                storage.delete(path)

    def test_crawl_expand(self):
        self.spider.crawl_depth = 2
        result = self.spider.start('any-id')
        self.assertEqual(len(result.data['results']), 1)
        self.assertEqual(len(result.data['results'][0]['content']), 3)
        self.assertGreater(result.other.pk, 0)

        path = result.other.local_path
        if hasattr(storage, 'base_location'):
            rmtree(self.get_path(path))
        else:
            if storage.exists(path):
                storage.delete(path)


class LocalContentTests(TestCase):
    fixtures = ["spider.json", "result.json"]

    def test_create(self):
        result = models.Result.objects.get(pk=1)
        local_content = models.LocalContent.objects.create(
            local_path="2016/06/07/test.zip",
        )
        result.other = local_content
        result.save()
        self.assertEqual(force_text(local_content),
                         _('Content (at {0}) of: {1}').format(
                             local_content.created_time,
                             result)
                         )


class ResultTests(TestCase):
    fixtures = ["spider.json", "result.json"]

    def test_create(self):
        spider = models.Spider.objects.get(pk=1)
        result = models.Result.objects.create(
            task_id="c1e26d8e-2e75-4377-991e-c1df346e5b11",
            data='{}',
            spider=spider,
        )
        self.assertEqual(force_text(result),
                         _('Task Result <{0}>').format(result.task_id))

    def test_data(self):
        result = models.Result.objects.get(pk=1)
        data = result.get_data(clean=True)
        self.assertEqual(len(data), 1)
        self.assertIn("BlogPost", data)
        self.assertEqual(len(data["BlogPost"]), 1)
        self.assertEqual(set(data["BlogPost"][0]["content"].keys()),
                         {"url", "content", "author", "title"})


class SimpleArchiveTests(TestCase):
    base_dir = 'test-simplearchive-tmp'
    storage_dir = 'test-simplearchive-storage'

    @classmethod
    def setUpClass(self):
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir)
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir)

    @classmethod
    def tearDownClass(self):
        rmtree(self.base_dir)
        try:
            storage.delete(self.storage_dir)
        except:
            rmtree(os.path.join(storage.base_location, self.storage_dir))

    def test_create_archive(self):
        """ Test creating a normal and small archive """
        zip_name = self.id() + '.zip'
        zip_path = os.path.join(self.base_dir, zip_name)
        arch = utils.SimpleArchive(zip_path)
        sample_content = 'Hey there!'
        arch.write('01.py', sample_content)
        arch.write('02.py', sample_content)
        arch.finish()
        self.assertEqual(os.path.exists(zip_path), True)
        zfile = ZipFile(zip_path, 'r')
        files = zfile.namelist()
        self.assertIn('01.py', files)
        self.assertIn('02.py', files)

    def test_move_to_storage_keep(self):
        """ Moving to storage and still keeping the old file """
        zip_name = self.id() + '.zip'
        zip_path = os.path.join(self.base_dir, zip_name)
        arch = utils.SimpleArchive(zip_path)
        arch.write('index.json', '{}')
        new_path = arch.move_to_storage(storage, self.storage_dir, remove=False)
        expected_file = os.path.join(self.storage_dir, zip_name)
        self.assertEqual(expected_file, new_path)
        self.assertEqual(storage.exists(expected_file), True)
        self.assertEqual(os.path.exists(zip_path), True)

    def test_move_to_storage_remove(self):
        """ Moving to storage and still keeping the old file """
        zip_name = self.id() + '.zip'
        zip_path = os.path.join(self.base_dir, zip_name)
        arch = utils.SimpleArchive(zip_path)
        arch.write('index.json', '{}')
        new_path = arch.move_to_storage(
            storage, self.storage_dir, remove=True)
        expected_file = os.path.join(self.storage_dir, zip_name)
        self.assertEqual(expected_file, new_path)
        self.assertEqual(storage.exists(expected_file), True)
        self.assertEqual(os.path.exists(zip_path), False)


class MiscTests(TestCase):
    def tearDown(self):
        try:
            storage.delete('tests')
        except:
            rmtree(join(storage.base_location, 'tests'))

    def test_move_to_storage_file(self):
        file_path = join(config.TEMP_DIR, 'test_move.txt')
        with open(file_path, 'w') as wfile:
            wfile.write('dummy')
        new_path = utils.move_to_storage(storage, file_path, 'tests')
        self.assertEqual(new_path, join('tests', 'test_move.txt'))
        self.assertNotEqual(os.path.exists(file_path), True)
        self.assertEqual(storage.exists(new_path), True)

    def test_move_to_storage_dir(self):
        location = join(config.TEMP_DIR, 'test_misc')
        os.makedirs(location + '/empty_dir')
        os.makedirs(location + '/normal_dir')
        file_one = join(location, '01.txt')
        with open(file_one, 'w') as wfile:
            wfile.write('dummy')
        file_two = join(location, 'normal_dir/02.txt')
        with open(file_two, 'w') as wfile:
            wfile.write('dummy')
        new_path = utils.move_to_storage(storage, location, 'tests')
        self.assertEqual(new_path, join('tests', 'test_misc'))
        self.assertNotEqual(os.path.exists(location), True)
        self.assertEqual(storage.exists(new_path), True)
        self.assertEqual(storage.exists(join(new_path, 'empty_dir')), False)
        self.assertEqual(storage.exists(join(new_path, 'normal_dir')), True)
        self.assertEqual(
            storage.exists(join(new_path, 'normal_dir/02.txt')), True)
        self.assertEqual(storage.exists(join(new_path, '01.txt')), True)

    def test_remove_local_files(self):
        file_path = join(config.TEMP_DIR, 'test_remove_local.txt')
        with open(file_path, 'w') as wfile:
            wfile.write('dummy')
        new_path = utils.move_to_storage(storage, file_path, 'tests')
        local = models.LocalContent(
            local_path=new_path,
        )
        self.assertEquals(storage.exists(new_path), True)
        local.remove_files()
        self.assertEqual(local.local_path, '')
        self.assertEquals(storage.exists(new_path), False)
