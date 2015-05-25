from django.test import TestCase
from django.conf import settings
from django.core.files.storage import default_storage as storage

import os
import simplejson as json

from zipfile import ZipFile
from os.path import join
from shutil import rmtree
from zipfile import ZipFile

from scraper import utils, models, config
from scraper.extractor import Extractor


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


def get_url(file_name):
    return os.path.join(DATA_URL, file_name)


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
        self.extractor = Extractor(target_file)

    @classmethod
    def tearDownClass(self):
        if os.path.exists(self.extractor.location):
            rmtree(self.extractor.location)

    def test_parse_content(self):
        self.assertNotEqual(self.extractor._uuid, '')
        self.assertNotEqual(self.extractor.root, None)

    def test_unique_location(self):
        new_extractor = Extractor(get_path('yc.0.html'))
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

    def test_extract_links_duplicate(self):
        links = self.extractor.extract_links(unique=False)
        self.assertEqual(len(links), 81)
        self.assertEqual(links[0]['url'],
                         'https://posthaven.com/')
        self.assertEqual(links[19]['url'],
                         'http://www.fastcompany.com/3042861/the-y-combinator-chronicles/the-secret-million-that-y-combinator-invests-in-all-its-startups')
        self.assertEqual(links[19]['text'],
                         u'Transcriptic\xc2\xa0(YC W15) and the array of free services for new YC startups')

    def test_extract_links_unique(self):
        links = self.extractor.extract_links(unique=True)
        self.assertEqual(len(links), 74)
        self.assertEqual(links[0]['url'],
                         'https://posthaven.com/')

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
        pass

    @classmethod
    def tearDownClass(self):
        pass

    def tearDown(self):
        location = self.extractor.location
        if os.path.exists(location):
            if os.path.isdir(location):
                rmtree(location)
            else:
                os.remove(location)

    def setUp(self):
        self.extractor = Extractor(DATA_URL+'yc.0.html')
        self.selectors = {
            'post': ("//div[@id='main']/article[@class='post']", 'text'),
        }

    def test_extract_content_basic(self):
        data, path = self.extractor.extract_content(self.selectors)
        self.assertNotEqual(path, '')
        self.assertEqual(os.path.exists(path), False)
        self.assertGreater(len(data['content']['post']), 0)

    def test_extract_content_tbody(self):
        selectors = {
            'post': ("//div[@id='main']/tbody/article[@class='post']", 'text')}
        data, path = self.extractor.extract_content(selectors)
        self.assertNotEqual(path, '')
        self.assertGreater(len(data['content']['post']), 0)

    def test_extract_content_with_ua(self):
        UA = 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36' 
        self.extractor = Extractor(DATA_URL+'yc.0.html', user_agent=UA)
        data, path = self.extractor.extract_content(self.selectors)
        self.assertGreater(len(data['content']['post']), 0)
        self.assertNotEqual(path, '')

    def test_extract_content_blackword(self):
        bw = ['panicked', 'phone']
        data, path = self.extractor.extract_content(self.selectors, black_words=bw)
        self.assertEqual(data, None)

    def test_extract_content_with_image(self):
        custom_selector = {
            'post': ("//div[@id='main']/article[@class='post']", 'html'),
        }
        data, path = self.extractor.extract_content(custom_selector)
        self.assertEqual(path, self.extractor.location)
        self.assertEqual(len(os.listdir(path)), 2)

    def test_extract_content_meta(self):
        custom_selectors = self.selectors.copy()
        custom_selectors['title'] = ("(//h2/a)[1]", 'text')
        data, path = self.extractor.extract_content(custom_selectors)
        self.assertNotEqual(path, '')
        # Verify the meta file
        self.assertEquals(
            data['content']['title'],
            ["Shift Messenger (YC W15) Makes It Easy For Workers To Swap Hours"]
        )

    def test_extract_content_media(self):
        custom_selectors = self.selectors.copy()
        custom_selectors['extra'] = ('(//img)[1]/@src', 'binary')
        data, path = self.extractor.extract_content(custom_selectors)

        self.assertEqual(path, self.extractor.location)
        self.assertEqual(len(os.listdir(path)), 1)


class SpiderMock(object):
    def __init__(self, target=['//a'], expand=[]):
        self.target_links = target
        self.expand_links = expand


class CollectorTests(TestCase):

    def setUp(self):
        self.compress_option = models.COMPRESS_RESULT

    def tearDown(self):
        models.COMPRESS_RESULT = self.compress_option

    def test_get_links(self):
        # Create collector, selectors then spider
        collector = models.Collector(name='news-content')
        collector.save()
        result = collector.get_links(get_url('yc.0.html'))
        self.assertNotEqual(result, None)
        self.assertEqual(len(result.data['content']), 81)

    def test_get_page(self):
        # Create collector, selectors then spider
        collector = models.Collector(name='news-content')
        collector.save()
        result = collector.get_links(get_url('yc.0.html'))
        self.assertNotEqual(result, None)
        self.assertGreater(len(result.data['content']), 10)

    def test_get_content(self):
        # Create collector, selectors then spider
        models.COMPRESS_RESULT = False
        collector = models.Collector(name='news-content')
        collector.save()
        selector = models.Selector(
            key='body',
            xpath="//div[@class='post-body']",
            data_type='html'
        )
        selector.save()
        collector.selectors.add(selector)
        res = collector.get_content(get_url('yc.0.html'))
        self.assertNotEqual(res['content']['body'], None)
        self.assertEqual(storage.exists(res['extras']['path']), True)

    def test_get_content_zip(self):
        models.COMPRESS_RESULT = True
        # Create collector, selectors then spider
        collector = models.Collector(name='news-content')
        collector.save()
        selector = models.Selector(
            key='body',
            xpath="//div[@class='post-body']",
            data_type='html'
        )
        selector.save()
        collector.selectors.add(selector)
        res = collector.get_content(get_url('yc.0.html'))
        self.assertNotEqual(res['content']['body'], None)
        self.assertEqual(storage.exists(res['extras']['path']), True)

    def test_get_content_with_spider(self):
        models.COMPRESS_RESULT = False
        collector = models.Collector(name='news-content')
        collector.save()
        selector = models.Selector(
            key='body',
            xpath="//div[@class='post-body']",
            data_type='html'
        )
        selector.save()
        collector.selectors.add(selector)
        spider = SpiderMock(
            ['//div[@class="post-title"]//a'],
            ['//header/a']
        )
        res = collector.get_content(get_url('yc.0.html'), spider=spider)
        self.assertNotEqual(res['content']['body'], None)
        self.assertEqual(len(res['extras']['target']), 3)
        self.assertEqual(len(res['extras']['expand']), 1)
        self.assertEqual(os.path.exists(res['extras']['path']), True)


class SpiderTests(TestCase):

    def setUp(self):
        self.compress_option = models.COMPRESS_RESULT

    def tearDown(self):
        models.COMPRESS_RESULT = self.compress_option

    def get_path(self, location):
        if hasattr(storage, 'base_location'):
            return os.path.join(storage.base_location, location)
        else:
            return location

    def test_crawl_basic(self):
        models.COMPRESS_RESULT = False
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
        result, path = spider.crawl_content()
        self.assertEqual(storage.exists(path), True)
        result_json = result.data
        self.assertEqual(len(result_json['content']), 3)
        self.assertGreater(result.other.pk, 0)

        if hasattr(storage, 'base_location'):
            rmtree(self.get_path(path))
        else:
            if storage.exists(path):
                storage.delete(path)

    def test_crawl_zip(self):
        models.COMPRESS_RESULT = True
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
        result, path = spider.crawl_content()
        self.assertIn('.zip', path)
        self.assertEqual(storage.exists(path), True)
        result_json = result.data
        self.assertEqual(len(result_json['content']), 3)
        self.assertGreater(result.other.pk, 0)
        zfile = ZipFile(join(storage.base_location, path))
        self.assertEquals(len(zfile.namelist()), 6)
        storage.delete(path)

    def test_crawl_expand(self):
        models.COMPRESS_RESULT = False
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
            expand_links=['//a[@rel="next"]'],
            crawl_depth=2
        )
        spider.save()
        spider.collectors.add(collector)
        self.assertGreater(spider.pk, 0)
        result, path = spider.crawl_content()
        self.assertEqual(storage.exists(path), True)
        result_json = result.data
        self.assertEqual(len(result_json['content']), 5)
        self.assertGreater(result.other.pk, 0)

        if hasattr(storage, 'base_location'):
            rmtree(self.get_path(path))
        else:
            if storage.exists(path):
                storage.delete(path)


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
        os.makedirs(location+'/empty_dir')
        os.makedirs(location+'/normal_dir')
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
