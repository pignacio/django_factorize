#!/usr/bin/env python
# encoding: utf-8
from __future__ import (absolute_import, unicode_literals, division,
                        print_function)

import collections
import logging
import os
import textwrap
from StringIO import StringIO

from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import models

try:
    import django.apps
    get_django_models = django.apps.apps.get_models  # pylint: disable=invalid-name
except (ImportError, AttributeError):
    from django.db.models import get_models as get_django_models  # pylint: disable=no-name-in-module

from django_factorize.contrib import color
from django_factorize.contrib.nt_with_defaults import namedtuple_with_defaults
from django_factorize.debug import pprint

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

_NOTHING = object()

_ModelInfo = collections.namedtuple('ModelInfo', ['module', 'name', 'app'])


class ModelInfo(_ModelInfo):
    __slots__ = ()

    @classmethod
    def from_model(cls, model):
        module = model.__module__
        return cls(module=module,
                   name=model.__name__,
                   app=_get_app_for_module(module), )


_ModelData = collections.namedtuple('ModelData', ['info', 'fields'])


class ModelData(_ModelData):
    __slots__ = ()

    @classmethod
    def from_model(cls, model):
        field_datas = collections.OrderedDict()  # Keep fields order
        for field in model._meta.get_fields():  # pylint: disable=protected-access
            if not _should_skip_field(model, field.name, field):
                field_datas[field.name] = FieldData.from_field(field)
        return cls(info=ModelInfo.from_model(model), fields=field_datas)

_FieldData = namedtuple_with_defaults(
    'FieldData',
    ['model', 'name', 'field_type', 'default', 'is_relation',
     'is_reverse_relation', 'related_model', 'related_name'],
    defaults={
        'default': _NOTHING,
        'is_relation': False,
        'is_reverse_relation': False,
        'related_model': None,
        'related_name': None}
)  # yapf: disable


# pylint: disable=slots-on-old-class,too-few-public-methods
class FieldData(_FieldData):
    __slots__ = ()

    @classmethod
    def from_field(cls, field):
        data = cls(model=ModelInfo.from_model(field.model),
                   name=field.name,
                   field_type=field.__class__.__name__)
        try:
            default = field.default
        except AttributeError:
            pass
        else:
            if default != models.NOT_PROVIDED:
                data = data._replace(default=default)

        if isinstance(field, (models.ForeignKey, models.OneToOneField)):
            data = data._replace(
                is_relation=True,
                is_reverse_relation=False,
                related_model=ModelInfo.from_model(field.related_model),
                related_name=field.related.name, )
        elif isinstance(field, models.OneToOneRel):
            related_model = ModelInfo.from_model(field.related_model)
            data = data._replace(is_relation=True,
                                 is_reverse_relation=True,
                                 related_model=related_model, )
        return data


def _get_local_apps():
    return [app for app in settings.INSTALLED_APPS if _is_local_module(app)]


def _get_app_for_module(module):
    for app in sorted(settings.INSTALLED_APPS, reverse=True):
        if module.startswith(app):
            return app
    return None


def _is_local_module(app_dotted_path):
    app_path = app_dotted_path.replace('.', '/')
    return os.path.isfile(os.path.join(
        app_path, '__init__.py')) or os.path.isfile(app_path + '.py')


def _get_field_data(field):
    try:
        default = field.default
    except AttributeError:
        default = _NOTHING
    else:
        if default == models.NOT_PROVIDED:
            default = _NOTHING

    data = {'field': field.__class__.__name__,
            'relation': False,
            'default': default}
    if isinstance(field, models.ForeignKey):
        data.update({'relation': True,
                     'relation_reversed': False,
                     'related_to': (field.related_model.__module__,
                                    field.related_model.__name__)})
    elif isinstance(field, models.ManyToOneRel):
        data.update({'relation': True,
                     'relation_reversed': True,
                     'related_to': (field.related_model.__module__,
                                    field.related_model.__name__)})

    return data


def _skip_reason(name, field):
    if field.name != name:
        return 'Field names do not match: "{}" != "{}"'.format(field.name,
                                                               name)

    if isinstance(field, models.DateTimeField) and (field.auto_now_add or
                                                    field.auto_now):
        return 'DateTimeField with auto_now or auto_now_add'

    if isinstance(field, models.AutoField):
        return 'AutoField'

    # OneToOneRel is subclass of ManyToOneRel
    if field.__class__ == models.ManyToOneRel:
        return 'ManyToOneRel'

    return None


def _should_skip_field(model, name, field):
    reason = _skip_reason(name, field)
    if reason is not None:
        logger.debug('%s.%s: %s. Skipping', model.__name__, name, reason)
    return reason is not None


def _get_model_data(model):
    meta = model._meta  # pylint: disable=protected-access
    field_names = meta.get_all_field_names()
    fields = {name: meta.get_field_by_name(name)[0]
              for name in meta.get_all_field_names()}
    field_datas = {name: FieldData.from_field(meta.get_field_by_name(name)[0])
                   for name, field in fields.items()
                   if not _should_skip_field(model, name, field)}
    return {'data': ModelData.from_model(model),
            'fields': field_datas,
            'field_names': field_names}


def _get_field_status_color(field_data, value):
    if value != _NOTHING:
        return color.bright_green
    if field_data.default != _NOTHING:
        return color.bright_yellow
    return color.bright_red


def _get_value(models_by_app, model, field, field_data, value):
    if value != _NOTHING:
        return value
    if field_data.default != _NOTHING:
        return _NOTHING
    if field_data.is_relation:
        if field_data.is_reverse_relation:
            return ''
    return _NOTHING


def _generate_factory(name,
                      model,
                      fields,
                      comments=None,
                      comment_missing_fields=True):
    comments = comments or {}
    code = StringIO()
    code.write(textwrap.dedent('''
        class {name}(factory.DjangoModelFactory):
            class Meta(object):
                model = {model}

        ''').format(name=name,
                    model=model))
    for field, value in fields.items():
        comment = comments.get(field)
        if value != _NOTHING:
            code.write('    {} = {}'.format(field, value))
            if comment:
                code.write('  # ' + comment)
            code.write('\n')
        elif comment_missing_fields:
            code.write('    # ' + field)
            if comment:
                code.write('  # ' + comment)
            code.write('\n')
    return code.getvalue()


def _get_field_name_in_related_model(field, related_model):
    for related_field, field_data in related_model.fields.items():
        if (field_data.related_model == field.model and
                field_data.related_name == field.name):
            return field_data.name
    return None


def _get_suggested_field_values(model_data, models_by_app):
    suggested = collections.defaultdict(lambda: _NOTHING)
    for name, field in model_data.fields.items():
        value = _NOTHING
        if field.is_relation:
            if field.is_reverse_relation:
                # TODO(irossi): get reverse foreign key field
                related_model = models_by_app[field.related_model.app][
                    field.related_model.name]
                related_field = _get_field_name_in_related_model(
                    field, related_model)
                if related_field:
                    value = 'factory.RelatedFactory("{}.{}", "{}")'.format(
                        field.related_model.app, field.related_model.name,
                        related_field)
            else:
                value = 'factory.SubFactory("{}.{}")'.format(
                    field.related_model.app, field.related_model.name)
            suggested[name] = value
    return suggested


class Command(BaseCommand):
    help = "Factorize your app models."

    def handle(self, *args, **options):
        local_apps = sorted(_get_local_apps(), reverse=True)
        models_by_app = collections.defaultdict(dict)
        values = collections.defaultdict(dict)
        for model in get_django_models():
            app = _get_app_for_module(model.__module__)
            if app in local_apps:
                models_by_app[app][model.__name__] = ModelData.from_model(
                    model)
                values[app][model.__name__] = {}

        pprint(dict(models_by_app))

        for app, app_models in models_by_app.items():
            print(color.blue(app))
            for model, model_data in app_models.items():
                print(color.magenta(" " + model))
                for field, field_data in model_data.fields.items():
                    value = values[app][model].get(field, _NOTHING)
                    (models_by_app, model, field, field_data, _NOTHING)
                    status_color = _get_field_status_color(field_data, value)
                    print(status_color('  - {} = {}'.format(field, _get_value(
                        models_by_app, model, field, field_data, value))))

        code = StringIO()
        for app, app_models in models_by_app.items():
            app_path = os.path.join(*app.split("."))
            factories_path = os.path.join(app_path, 'test_factories.py')
            print(color.green('#  {factories_path}\n'.format(factories_path=
                                                             factories_path)),
                  file=code)
            for model, model_data in app_models.items():
                suggested = _get_suggested_field_values(model_data,
                                                        models_by_app)
                values = collections.OrderedDict()
                comments = {}
                for field, field_data in model_data.fields.items():
                    if field in suggested:
                        value = suggested[field]
                    else:
                        value = _NOTHING

                    values[field] = value

                    if field_data.default != _NOTHING:
                        comments[field] = 'Has default: {}'.format(
                            field_data.default)

                print(_generate_factory(model + "Factory", model, values,
                                        comments),
                      file=code)
            print(file=code)

        print(code.getvalue())
