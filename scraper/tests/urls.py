import re

from django.conf import settings
from django.conf.urls import include, url
from django.conf.urls.static import static
from django.views.static import serve

urlpatterns = [
    url("", include("scraper.urls"))
]

urlpatterns += [
    url(r'^%s(?P<path>.*)$' % re.escape(settings.TEST_DATA_URL.lstrip('/')), serve,
        kwargs={"document_root": settings.TEST_DATA_DIR}),
]
