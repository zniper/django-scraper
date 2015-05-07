from django.core.management.base import NoArgsCommand

from scraper.models import Spider


class Command(NoArgsCommand):
    """ Crawl all active resources """

    def handle_noargs(self, **options):
        spiders = Spider.objects.all()
        for spider in spiders:
            spider.crawl_content()
