#!/usr/bin/env python
# encoding: utf-8
from __future__ import absolute_import, unicode_literals, division

import collections
import logging
import os
from pprint import pprint

from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import models

from django_factorize import color

try:
    import django.apps
    get_django_models = django.apps.apps.get_models
except (ImportError, AttributeError):
    from django.db.models import get_models as get_django_models

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name

NO_DEFAULT = models.NOT_PROVIDED


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


def _get_field_data(model, field):
    data = {'field': field.__class__.__name__, 'relation': False, }
    if isinstance(field, models.ForeignKey):
        data.update({'relation': True,
                     'relation_reversed': False,
                     'related_to': (field.related_model.__module__,
                                    field.related_model.__name__),
                     'default': field.default})
    elif isinstance(field, models.ManyToOneRel):
        data.update({'relation': True,
                     'relation_reversed': True,
                     'related_to': (field.related_model.__module__,
                                    field.related_model.__name__)})

    else:
        data.update({'default': field.default})
    return data


def _skip_reason(model, name, field):
    if field.name != name:
        return 'Field names do not match: "{}" != "{}"'.format(field.name,
                                                               name)

    if isinstance(field, models.DateTimeField) and (field.auto_now_add or
                                                    field.auto_now):
        return 'DateTimeField with auto_now or auto_now_add'

    if isinstance(field, models.AutoField):
        return 'AutoField'

    return None


def _should_skip_field(model, name, field):
    reason = _skip_reason(model, name, field)
    if reason is not None:
        logger.debug('%s.%s: %s', model.__name__, name, reason)
    return reason is not None


def _get_model_data(model):
    meta = model._meta
    fields = {name: meta.get_field_by_name(name)[0]
              for name in meta.get_all_field_names()}
    field_datas = {name: _get_field_data(model, field)
                   for name, field in fields.items()
                   if not _should_skip_field(model, name, field)}
    return {'fields': field_datas, }


def _get_field_status_color(field_data, value):
    if value != NO_DEFAULT:
        return color.bright_green
    if field_data.get('default', NO_DEFAULT) != NO_DEFAULT:
        return color.bright_yellow
    return color.bright_red


class Command(BaseCommand):
    help = "Factorize your app models."

    def handle(self, *args, **options):
        local_apps = sorted(_get_local_apps(), reverse=True)
        models_by_app = collections.defaultdict(dict)
        values = collections.defaultdict(dict)
        for model in get_django_models():
            app = _get_app_for_module(model.__module__)
            if app in local_apps:
                models_by_app[app][model.__name__] = _get_model_data(model)
                values[app][model.__name__] = {}

        for app, app_models in models_by_app.items():
            print color.blue(app)
            for model, model_data in app_models.items():
                print color.magenta(" " + model)
                for field, field_data in model_data['fields'].items():
                    print _get_field_status_color(
                        field_data, values[app][model].get(
                            field, NO_DEFAULT))('  - ' + field)

        return
        lines = []
        for app, app_models in models_by_app.items():
            lines.append('#  {app}/test_factories.py \n'.format(app=app))
            for model, model_data in app_models.items():
                lines.append(
                    'class {model}Factory(factory.DjangoModelFactory):\n'
                    '    class Meta(object):\n'
                    '       model = "{app}.{model}"\n'.format(app=app,
                                                              model=model))
                for field, field_data in model_data['fields'].items():
                    if field_data['relation']:
                        if field_data['relation_reversed']:
                            # TODO(irossi): get reverse foreign key field
                            value = 'factory.RelatedFactory("{}.{}", )'.format(
                                *field_data['related_to'])
                        else:
                            value = 'factory.SubFactory("{}.{}")'.format(
                                *field_data['related_to'])
                    elif field_data.get('default', NO_DEFAULT) != NO_DEFAULT:
                        value = repr(field_data['default'])
                    else:
                        value = repr("")

                    line = '    {field} = {value}'.format(field=field,
                                                          value=value)

                    if field_data.get('default', NO_DEFAULT) != NO_DEFAULT:
                        line = line + "  # has default"

                    lines.append(line)
                lines.append('')
            lines.append('')

        for line in lines:
            print line
