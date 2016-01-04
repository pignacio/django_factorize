#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division

import collections
import logging
from pprint import PrettyPrinter  # pylint: disable=unused-import

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class MyPrettyPrinter(PrettyPrinter):
    def _format(self, thing, *args, **kwargs):
        try:
            as_dict = thing._asdict
        except AttributeError:
            if isinstance(thing, collections.OrderedDict):
                thing = dict(thing)
        else:
            thing = dict(as_dict())
        return PrettyPrinter._format(self, thing, *args, **kwargs)


pprint = MyPrettyPrinter().pprint  # pylint: disable=invalid-name
