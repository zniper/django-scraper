from __future__ import unicode_literals

from django.utils.deconstruct import deconstructible
from lxml import etree
from six import text_type

from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _


@deconstructible
class ListValidator(object):
    """A validator that validates if a value is a list of given type or not."""

    def __init__(self, item_types, message=""):
        if not isinstance(item_types, list):
            item_types = [item_types]
        self.item_types = item_types
        self.message = message

    def __call__(self, value):
        if not isinstance(value, list) and not isinstance(value, tuple):
            raise ValidationError(self.get_message(), code="invalid_list")
        for item in value:
            is_valid = False
            for item_type in self.item_types:
                if isinstance(item, item_type):
                    is_valid = True
                    break
            if not is_valid:
                raise ValidationError(self.get_message(), code="invalid_list")

    def get_message(self, *args, **kwargs):
        if not self.message:
            self.message = _("Please enter a list of {0} items").format(
                self.item_type)
        return self.message


@deconstructible
class DictValidator(object):
    """A validator that validates if a value is a dictionary or not."""

    def __init__(self):
        super(DictValidator, self).__init__()

    def __call__(self, value):
        if not isinstance(value, dict):
            raise ValidationError(_("Please enter a valid dictionary."),
                                  "invalid_dict")


@deconstructible
class XPathValidator(object):
    """A validator that validates if a value is a valid XPath or not."""

    def __call__(self, value):
        tree = etree.HTML("<html></html>")
        try:
            tree.xpath(value)
        except (ValueError, etree.XPathEvalError):
            raise ValidationError(_("Invalid XPath."), "invalid_xpath")


@deconstructible
class XPathListValidator(ListValidator):
    """A validator that validates if a value is a list of valid XPaths or not.
    """

    def __init__(self, message=""):
        super(XPathListValidator, self).__init__(text_type, message)

    def __call__(self, value):
        super(XPathListValidator, self).__call__(value)
        # Validate XPaths
        for item in value:
            try:
                XPathValidator()(item)
            except ValidationError:
                raise ValidationError(
                    "{0} {1}".format(
                        self.get_message(item),
                        _(" Invalid XPath: {0}.").format(item)
                    ), "invalid_xpath_list")


@deconstructible
class NumberPatternValidator(ListValidator):
    def __init__(self, message=""):
        super(NumberPatternValidator, self).__init__(int, message)

    def __call__(self, value):
        super(NumberPatternValidator, self).__call__(value)
        if len(value) != 3:
            raise ValidationError(self.get_message(), "invalid_number_pattern")
        for item in value:
            if item < 0:
                raise ValidationError(
                    "{0} {1}".format(
                        self.get_message(),
                        _(" {0} is not a positive integer.").format(item)),
                    "invalid_number_pattern")


@deconstructible
class RequiredWordsValidator(ListValidator):
    def __init__(self, message=""):
        super(RequiredWordsValidator, self).__init__([text_type, list], message)

    def __call__(self, value):
        super(RequiredWordsValidator, self).__call__(value)
        for item in value:
            if isinstance(item, list):
                for element in item:
                    if not isinstance(element, text_type):
                        raise ValidationError(self.get_message(),
                                              "invalid_required_words")
