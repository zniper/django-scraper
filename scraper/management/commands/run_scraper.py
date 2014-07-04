from django.core.management.base import NoArgsCommand

from scraper.models import Source


class Command(NoArgsCommand):
    """ Crawl all active resources """

    def handle_noargs(self, **options):
        sources = Source.objects.filter(active=True)
        for source in sources:
            source.crawl()
