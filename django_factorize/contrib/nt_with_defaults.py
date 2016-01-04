#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2015 Ignacio Rossi
#
# This library is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation; either version 2.1 of the License, or
# (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this library; if not, see <http://www.gnu.org/licenses/>.
from __future__ import absolute_import, unicode_literals

import collections
import logging
import sys

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def namedtuple_with_defaults(tuple_name, fields, defaults=None):
    '''
    Create a :py:class:`collections.namedtuple` subclass with the given
    ``name`` and ``fields`` which has default values for some fields.

    Args:
        tuple_name (str): namedtuple's name.
        fields (str,list): namedtuple's field.
        defaults (dict): the namedtuple's defaults.

    Returns:
        type: the new namedtuple class


    >>> MyTuple = namedtuple_with_defaults('MyTuple', ['a', 'b'], {'b': 5})
    >>> MyTuple(a=3)
    MyTuple(a=3, b=5)
    >>> MyTuple(a=1, b=2)
    MyTuple(a=1, b=2)
    '''
    defaults = defaults or {}
    tuple_class = collections.namedtuple(tuple_name, fields)

    # pylint: disable=no-init,too-few-public-methods
    class NamedTuple(tuple_class):
        __slots__ = ()

        # Magic: this also works as expected with dicts
        __defaults = staticmethod(defaults)

        def __new__(cls, *args, **kwargs):
            if len(args) > len(tuple_class._fields):
                raise ValueError('Too many arguments for namedtuple: got {} '
                                 'instead of {}'
                                 .format(len(args), len(tuple_class._fields)))
            defaults = cls.__get_defaults()
            fields_in_args = set(tuple_class._fields[:len(args)])
            kwvalues = {
                f: cls.__extract_value(f, kwargs, defaults)
                for f in tuple_class._fields if f not in fields_in_args
            }
            if kwargs:
                raise ValueError('Unexpected argument for namedtuple: {}'
                                 .format(kwargs.popitem()[0]))
            return tuple_class.__new__(cls, *args, **kwvalues)

        @staticmethod
        def __extract_value(key, kwargs, defaults):
            try:
                return kwargs.pop(key)
            except KeyError:
                try:
                    return defaults[key]
                except KeyError:
                    raise ValueError("Missing argument for namedtuple: '{}'"
                                     .format(key))

        @classmethod
        def __get_defaults(cls):
            try:
                return cls.__defaults()
            except Exception:  # pylint: disable=broad-except
                return cls.__defaults

    NamedTuple.__name__ = str(tuple_name)  # Prevent unicode in Python 2.x

    # Stolen from: collections.namedtuple
    # For pickling to work, the __module__ variable needs to be set to the
    # frame where the named tuple is created.  Bypass this step in environments
    # where sys._getframe is not defined (Jython for example) or sys._getframe
    # is not defined for arguments greater than 0 (IronPython).
    try:
        # pylint: disable=protected-access
        NamedTuple.__module__ = sys._getframe(1).f_globals.get('__name__',
                                                               '__main__')
    except (AttributeError, ValueError):
        pass
    # /Stolen
    return NamedTuple
