from django.core.management.base import NoArgsCommand

from scraper.models import Spider


class Command(NoArgsCommand):
    """ Crawl all active resources """

    def handle_noargs(self, **options):
        spiders = Spider.objects.all()
        operations = [
            {'action': 'crawl', 'target': 'content'}
        ]
        for spider in spiders:
            spider.operate(operations)
