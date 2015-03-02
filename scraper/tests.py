from django.test import TestCase
from shutil import rmtree

import os

from scraper import utils, models


LOCAL_HOST = 'http://127.0.0.1:8000/'
GITHUB_URL = 'https://raw.githubusercontent.com/zniper/django-scraper/master/scraper/test_data/'
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


class ExtractorTests(TestCase):

    @classmethod
    def setUpClass(self):
        target_file = get_path('yc.0.html')
        self.extractor = utils.Extractor(target_file)

    @classmethod
    def tearDownClass(self):
        rmtree(self.extractor.get_location())

    def tearDown(self):
        self.extractor.set_location(self.current_location)

    def setUp(self):
        self.current_location = self.extractor.get_location()

    def test_parse_content(self):
        self.assertNotEqual(self.extractor.hash_value, '')
        self.assertNotEqual(self.extractor.root, None)

    def test_set_location(self):
        self.extractor.set_location('/new/location')
        self.assertEquals(self.extractor.get_location(), '/new/location')

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

    def test_prepare_directory(self):
        self.extractor.prepare_directory()
        self.assertEqual(os.path.exists(self.extractor.get_location()), True)

    def test_prepare_directory_existing(self):
        test_file = os.path.join(self.current_location, 'new_file')
        self.extractor.prepare_directory()
        f0 = open(test_file, 'w')
        f0.close()
        # recall the prepare directory
        self.extractor.prepare_directory()
        self.assertEqual(os.path.exists(self.current_location), True)
        self.assertEqual(os.path.exists(test_file), False)

    def test_download_file(self):
        self.extractor.prepare_directory()
        FILE_URL = 'https://raw.githubusercontent.com/zniper/django-scraper/master/scraper/test_data/simple_page.txt'
        file_name = self.extractor.download_file(FILE_URL)
        self.assertEqual(file_name, 'simple_page.txt')
