# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import __builtin__
import jsonfield.fields
import datetime
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='BaseCrawl',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Collector',
            fields=[
                ('basecrawl_ptr', models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False, to='scraper.BaseCrawl')),
                ('name', models.CharField(max_length=256)),
                ('get_image', models.BooleanField(default=True, help_text=b'Download images found inside extracted content')),
                ('replace_rules', jsonfield.fields.JSONField(default={}, help_text=b'List of Regex rules will be applied to refine data')),
                ('black_words', models.CharField(max_length=256, null=True, blank=True)),
            ],
            options={
            },
            bases=('scraper.basecrawl',),
        ),
        migrations.CreateModel(
            name='LocalContent',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('url', models.CharField(max_length=256)),
                ('local_path', models.CharField(max_length=256)),
                ('created_time', models.DateTimeField(default=datetime.datetime.now, null=True, blank=True)),
                ('state', models.IntegerField(default=0)),
                ('collector', models.ForeignKey(to='scraper.Collector')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='ProxyServer',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=64, verbose_name='Proxy Server Name')),
                ('address', models.CharField(max_length=128, verbose_name='Address')),
                ('port', models.IntegerField(verbose_name='Port')),
                ('protocol', models.CharField(max_length=16, verbose_name='Protocol', choices=[(b'http', b'HTTP'), (b'https', b'HTTPS')])),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Result',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('task_id', models.CharField(max_length=64, null=True, blank=True)),
                ('data', jsonfield.fields.JSONField(default=__builtin__.dict)),
                ('other', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, blank=True, to='scraper.LocalContent', null=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Selector',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('key', models.SlugField()),
                ('xpath', models.CharField(max_length=512)),
                ('data_type', models.CharField(max_length=64, choices=[(b'text', b'Text content'), (b'html', b'HTML content'), (b'binary', b'Binary content')])),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Spider',
            fields=[
                ('basecrawl_ptr', models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False, to='scraper.BaseCrawl')),
                ('name', models.CharField(max_length=256, null=True, blank=True)),
                ('url', models.URLField(help_text=b'URL of         the starting page', max_length=256, verbose_name='Start URL')),
                ('target_links', jsonfield.fields.JSONField(default=__builtin__.dict, help_text=b'XPaths toward links to pages with content         to be extracted')),
                ('expand_links', jsonfield.fields.JSONField(default=__builtin__.dict, help_text=b'List of links (as XPaths) to other pages         holding target links (will not be extracted)')),
                ('crawl_depth', models.PositiveIntegerField(default=1, help_text=b'Set this > 1         in case of crawling from this page')),
                ('collectors', models.ManyToManyField(to='scraper.Collector', blank=True)),
            ],
            options={
            },
            bases=('scraper.basecrawl',),
        ),
        migrations.CreateModel(
            name='UserAgent',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=64, verbose_name='UA Name')),
                ('value', models.CharField(max_length=256, verbose_name='User Agent String')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.AddField(
            model_name='collector',
            name='selectors',
            field=models.ManyToManyField(to='scraper.Selector', blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='basecrawl',
            name='proxy',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, blank=True, to='scraper.ProxyServer', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='basecrawl',
            name='user_agent',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, blank=True, to='scraper.UserAgent', null=True),
            preserve_default=True,
        ),
    ]
