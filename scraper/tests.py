from django.test import TestCase

import os

from scraper import utils


LOCAL_HOST = 'http://127.0.0.1:8000/'
DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                        'test_data')


#def start_local_site(path=''):
#    """ Just a simple local site for testing HTTP requests """
#    PORT = 8000
#    handler = SimpleHTTPServer.SimpleHTTPRequestHandler
#    httpd = SocketServer.TCPServer(('', PORT), handler)
#    print 'Local test server is up at', PORT
#    httpd.serve_forever()


def get_path(file_name):
    return os.path.join(DATA_DIR, file_name)


class ExtractorTests(TestCase):

    def setUp(self):
        target_file = get_path('simple_page.txt')
        self.extractor = utils.Extractor(target_file)

    def tearDown(self):
        pass

    def test_parse_content(self):
        self.assertNotEqual(self.extractor.hash_value, '')
        self.assertNotEqual(self.extractor.root, None)
