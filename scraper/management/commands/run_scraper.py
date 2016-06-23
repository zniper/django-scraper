from django.core.management.base import NoArgsCommand

from scraper.models import Spider


class Command(NoArgsCommand):
    """ Crawl all active resources """

    def handle_noargs(self, **options):
        spiders = Spider.objects.order_by("-id")[:1]
        operations = {'action': 'crawl', 'target': 'content'}

        for spider in spiders:
            spider.start(operations)
            # runner = SpiderRunner(spider)
            # data = runner.start()
            # print json.dumps(data, indent=4)
