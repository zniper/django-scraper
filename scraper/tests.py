from django.test import TestCase
from django.conf import settings
from django.core.files.storage import default_storage as storage

from shutil import rmtree

import os
import simplejson as json

from scraper import utils, models


LOCAL_HOST = 'http://127.0.0.1:8000/'
DATA_URL = """https://raw.githubusercontent.com/zniper/django-scraper/master/scraper/test_data/"""
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                        'test_data')

# For future use, with real web server
# def start_local_site(path=''):
#     """ Just a simple local site for testing HTTP requests """
#     PORT = 8000
#     handler = SimpleHTTPServer.SimpleHTTPRequestHandler
#     httpd = SocketServer.TCPServer(('', PORT), handler)
#     print 'Local test server is up at', PORT
#     httpd.serve_forever()


def get_path(file_name):
    return os.path.join(DATA_DIR, file_name)

def exists(path):
    if storage.exists(path):
        return True
    else:
        parent, name = path.rstrip('/').rsplit('/', 1)
        res = storage.listdir(parent)
        return name in res[0] or name in res[1]

class UserAgentTests(TestCase):

    def test_create(self):
        ua = models.UserAgent(name='Test UA', value='UA string')
        ua.save()
        self.assertNotEqual(ua.pk, None)


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


class ExtractorLocalTests(TestCase):

    @classmethod
    def setUpClass(self):
        target_file = get_path('yc.0.html')
        self.extractor = utils.Extractor(target_file)

    @classmethod
    def tearDownClass(self):
        if os.path.exists(self.extractor.location):
            rmtree(self.extractor.location)

    def tearDown(self):
        self.extractor.set_location(self.current_location)

    def setUp(self):
        self.current_location = self.extractor.location

    def test_parse_content(self):
        self.assertNotEqual(self.extractor._uuid, '')
        self.assertNotEqual(self.extractor.root, None)

    def test_unchanged_location(self):
        """Location will not be generated if existing"""
        old_location = self.extractor.location
        self.extractor.set_location()
        self.assertGreater(len(self.extractor.location), 0)
        self.assertEqual(self.extractor.location, old_location)

    def test_reset_location(self):
        """Location will not be generated if existing"""
        old_location = self.extractor.location
        self.extractor.set_location(reset=True)
        self.assertGreater(len(self.extractor.location), 0)
        self.assertNotEqual(self.extractor.location, old_location)

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

    def test_extract_links_no_expand(self):
        links = self.extractor.extract_links()
        self.assertEqual(len(links), 81)
        self.assertEqual(links[0]['url'],
                         'https://posthaven.com/')
        self.assertEqual(links[19]['url'],
                         'http://www.fastcompany.com/3042861/the-y-combinator-chronicles/the-secret-million-that-y-combinator-invests-in-all-its-startups')
        self.assertEqual(links[19]['text'],
                         u'Transcriptic\xc2\xa0(YC W15) and the array of free services for new YC startups')

    def test_get_path(self):
        file_path = self.extractor.get_path(__file__)
        self.assertGreater(len(file_path), 0)

    def test_refine_content(self):
        with open(get_path('yc.0.html'), 'r') as index:
            content = index.read()
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
        with open(get_path('yc.0.html'), 'r') as index:
            content = index.read()
            rules = []
            refined = self.extractor.refine_content(content, rules)
        self.assertEqual(content, refined)

    def test_download_file(self):
        FILE_URL = DATA_URL + 'simple_page.txt'
        file_name = self.extractor.download_file(FILE_URL)
        self.assertEqual(file_name, 'simple_page.txt')

    def test_download_file_failed(self):
        FILE_URL = DATA_URL + 'not_exist.txt'
        file_name = self.extractor.download_file(FILE_URL)
        self.assertEqual(file_name, None)


class ExtractorOnlineTests(TestCase):

    @classmethod
    def setUpClass(self):
        self.extractor = utils.Extractor(DATA_URL+'yc.0.html')
        self.selectors = {
            'post': ("//div[@id='main']/article[@class='post']", 'text'),
        }

    @classmethod
    def tearDownClass(self):
        pass

    def tearDown(self):
        if hasattr(storage, 'base_location'):
            result_path = os.path.join(
                storage.base_location,
                self.extractor.location)
            if os.path.exists(result_path):
                rmtree(result_path)
        else:
            if storage.exists(self.extractor.location):
                storage.delete(self.extractor.location)

    def setUp(self):
        self.extractor.set_location(reset=True)
        settings.SCRAPER_COMPRESS_RESULT = False

    def get_path(self, location):
        if hasattr(storage, 'base_location'):
            return os.path.join(storage.base_location, self.extractor.location)
        else:
            return location

    def test_extract_content_basic(self):
        result = self.extractor.extract_content(self.selectors)
        self.assertEqual(result[0], self.extractor.location)
        data = json.loads(result[1])
        self.assertGreater(len(data['content']['post']), 0)
        result_path = self.get_path(result[0])
        self.assertEqual(exists(result_path), True)

    def test_extract_content_as_zip(self):
        settings.SCRAPER_COMPRESS_RESULT = True
        result = self.extractor.extract_content(self.selectors)
        self.assertEqual(result[0], self.extractor.location)
        data = json.loads(result[1])
        self.assertGreater(len(data['content']['post']), 0)
        result_path = self.get_path(result[0]) + '.zip'
        self.assertEqual(exists(result_path), True)
        settings.SCRAPER_COMPRESS_RESULT = False
        try:
            os.remove(result_path)
        except OSError:
            pass

    def test_extract_content_with_ua(self):
        UA = 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36' 
        self.extractor = utils.Extractor(DATA_URL+'yc.0.html', user_agent=UA)
        result = self.extractor.extract_content(self.selectors)
        self.assertEqual(result[0], self.extractor.location)
        self.assertEqual(exists(result[0]), True)

    def test_extract_content_blackword(self):
        bw = ['panicked', 'phone']
        result = self.extractor.extract_content(self.selectors, black_words=bw)
        self.assertEqual(result, None)

    def test_extract_content_with_image(self):
        custom_selector = {
            'post': ("//div[@id='main']/article[@class='post']", 'html'),
        }
        result = self.extractor.extract_content(custom_selector)
        self.assertEqual(result[0], self.extractor.location)
        self.assertEqual(len(storage.listdir(result[0])[1]), 3)

    def test_extract_content_meta(self):
        custom_selectors = self.selectors.copy()
        custom_selectors['title'] = ("(//h2/a)[1]", 'text')
        result = self.extractor.extract_content(custom_selectors)

        self.assertEqual(result[0], self.extractor.location)
        # Verify the meta file
        with storage.open(os.path.join(result[0], 'index.json'), 'r') as vfile:
            values = json.load(vfile)
            self.assertEquals(
                values['content']['title'],
                ["Shift Messenger (YC W15) Makes It Easy For Workers To Swap Hours\n"]
            )

    def test_extract_content_extra(self):
        custom_selectors = self.selectors.copy()
        custom_selectors['extra'] = ('(//img)[1]/@src', 'binary')
        result = self.extractor.extract_content(custom_selectors)

        self.assertEqual(result[0], self.extractor.location)
        self.assertEqual(len(storage.listdir(result[0])), 2)

    def test_extract_links_expand(self):
        links = self.extractor.extract_links(
            ["//h2/a"],
            expand_xpaths=["//a[@rel='next']"],
            depth=2
        )
        self.assertEqual(len(links), 23)
        self.assertEqual(links[0]['url'],
                         'https://raw.githubusercontent.com/zniper/django-scraper/master/scraper/test_data/yc.a0.html')
        self.assertEqual(links[0]['text'],
                         'Shift Messenger (YC W15) Makes It Easy For Workers To Swap Hours')
        self.assertEqual(links[22]['url'],
                         'http://blog.ycombinator.com/cloudmedx-yc-w15-helps-doctors-spot-patients-who-will-need-expensive-treatment')
        self.assertEqual(links[22]['text'],
                         'CloudMedx (YC W15) Helps Doctors Spot Patients Who Will Need Expensive Treatment')


class ModelSourceTests(TestCase):

    def setUp(self):
        pass

    def get_path(self, location):
        if hasattr(storage, 'base_location'):
            return os.path.join(storage.base_location, location)
        else:
            return location

    def test_crawl_basic(self):
        # Create collector, selectors then spider
        selector = models.Selector(
            key='content',
            xpath="//div[@class='post-body']",
            data_type='html'
        )
        selector.save()
        collector = models.Collector(name='news-content')
        collector.save()
        collector.selectors.add(selector)
        spider = models.Spider(
            url=DATA_URL+'yc.0.html',
            name='Test Source',
            target_links=["//div[@class='post-title']/h2/a"],
            crawl_depth=1
        )
        spider.save()
        spider.collectors.add(collector)
        self.assertGreater(spider.pk, 0)
        results = spider.crawl_content()
        self.assertEqual(len(results), 3)

        for result in results:
            result_path = result.other.local_path
            self.assertEqual(exists(result_path), True)
            if hasattr(storage, 'base_location'):
                rmtree(self.get_path(result_path))
            else:
                if storage.exists(result_path):
                    storage.delete(result_path)
