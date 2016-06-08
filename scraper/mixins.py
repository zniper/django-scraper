import logging

from .exceptions import ExtractorNotSet

logger = logging.getLogger(__name__)


class ExtractorMixin(object):
    """Provides extractor property to models"""
    _extractor = None

    @property
    def extractor(self):
        if self._extractor is None:
            raise ExtractorNotSet
        return self._extractor

    @extractor.setter
    def extractor(self, obj):
        self._extractor = obj
