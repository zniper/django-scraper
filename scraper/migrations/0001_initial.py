# -*- coding: utf-8 -*-
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'BaseCrawl'
        db.create_table(u'scraper_basecrawl', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('proxy', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['scraper.ProxyServer'], null=True, on_delete=models.PROTECT, blank=True)),
            ('user_agent', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['scraper.UserAgent'], null=True, on_delete=models.PROTECT, blank=True)),
        ))
        db.send_create_signal(u'scraper', ['BaseCrawl'])

        # Adding model 'Collector'
        db.create_table(u'scraper_collector', (
            (u'basecrawl_ptr', self.gf('django.db.models.fields.related.OneToOneField')(to=orm['scraper.BaseCrawl'], unique=True, primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=256)),
            ('get_image', self.gf('django.db.models.fields.BooleanField')(default=True)),
            ('replace_rules', self.gf('jsonfield.fields.JSONField')(default={})),
            ('black_words', self.gf('django.db.models.fields.CharField')(max_length=256, null=True, blank=True)),
        ))
        db.send_create_signal(u'scraper', ['Collector'])

        # Adding M2M table for field selectors on 'Collector'
        m2m_table_name = db.shorten_name(u'scraper_collector_selectors')
        db.create_table(m2m_table_name, (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('collector', models.ForeignKey(orm[u'scraper.collector'], null=False)),
            ('selector', models.ForeignKey(orm[u'scraper.selector'], null=False))
        ))
        db.create_unique(m2m_table_name, ['collector_id', 'selector_id'])

        # Adding model 'Spider'
        db.create_table(u'scraper_spider', (
            (u'basecrawl_ptr', self.gf('django.db.models.fields.related.OneToOneField')(to=orm['scraper.BaseCrawl'], unique=True, primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=256, null=True, blank=True)),
            ('url', self.gf('django.db.models.fields.URLField')(max_length=256)),
            ('target_links', self.gf('jsonfield.fields.JSONField')(default={})),
            ('expand_links', self.gf('jsonfield.fields.JSONField')(default={})),
            ('crawl_depth', self.gf('django.db.models.fields.PositiveIntegerField')(default=1)),
        ))
        db.send_create_signal(u'scraper', ['Spider'])

        # Adding M2M table for field collectors on 'Spider'
        m2m_table_name = db.shorten_name(u'scraper_spider_collectors')
        db.create_table(m2m_table_name, (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('spider', models.ForeignKey(orm[u'scraper.spider'], null=False)),
            ('collector', models.ForeignKey(orm[u'scraper.collector'], null=False))
        ))
        db.create_unique(m2m_table_name, ['spider_id', 'collector_id'])

        # Adding model 'Selector'
        db.create_table(u'scraper_selector', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('key', self.gf('django.db.models.fields.SlugField')(max_length=50)),
            ('xpath', self.gf('django.db.models.fields.CharField')(max_length=512)),
            ('data_type', self.gf('django.db.models.fields.CharField')(max_length=64)),
        ))
        db.send_create_signal(u'scraper', ['Selector'])

        # Adding model 'Result'
        db.create_table(u'scraper_result', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('task_id', self.gf('django.db.models.fields.CharField')(max_length=64, null=True, blank=True)),
            ('data', self.gf('jsonfield.fields.JSONField')(default={})),
            ('other', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['scraper.LocalContent'], null=True, on_delete=models.SET_NULL, blank=True)),
        ))
        db.send_create_signal(u'scraper', ['Result'])

        # Adding model 'LocalContent'
        db.create_table(u'scraper_localcontent', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('url', self.gf('django.db.models.fields.CharField')(max_length=256)),
            ('collector', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['scraper.Collector'])),
            ('local_path', self.gf('django.db.models.fields.CharField')(max_length=256)),
            ('created_time', self.gf('django.db.models.fields.DateTimeField')(default=datetime.datetime.now, null=True, blank=True)),
            ('state', self.gf('django.db.models.fields.IntegerField')(default=0)),
        ))
        db.send_create_signal(u'scraper', ['LocalContent'])

        # Adding model 'UserAgent'
        db.create_table(u'scraper_useragent', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=64)),
            ('value', self.gf('django.db.models.fields.CharField')(max_length=256)),
        ))
        db.send_create_signal(u'scraper', ['UserAgent'])

        # Adding model 'ProxyServer'
        db.create_table(u'scraper_proxyserver', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=64)),
            ('address', self.gf('django.db.models.fields.CharField')(max_length=128)),
            ('port', self.gf('django.db.models.fields.IntegerField')()),
            ('protocol', self.gf('django.db.models.fields.CharField')(max_length=16)),
        ))
        db.send_create_signal(u'scraper', ['ProxyServer'])


    def backwards(self, orm):
        # Deleting model 'BaseCrawl'
        db.delete_table(u'scraper_basecrawl')

        # Deleting model 'Collector'
        db.delete_table(u'scraper_collector')

        # Removing M2M table for field selectors on 'Collector'
        db.delete_table(db.shorten_name(u'scraper_collector_selectors'))

        # Deleting model 'Spider'
        db.delete_table(u'scraper_spider')

        # Removing M2M table for field collectors on 'Spider'
        db.delete_table(db.shorten_name(u'scraper_spider_collectors'))

        # Deleting model 'Selector'
        db.delete_table(u'scraper_selector')

        # Deleting model 'Result'
        db.delete_table(u'scraper_result')

        # Deleting model 'LocalContent'
        db.delete_table(u'scraper_localcontent')

        # Deleting model 'UserAgent'
        db.delete_table(u'scraper_useragent')

        # Deleting model 'ProxyServer'
        db.delete_table(u'scraper_proxyserver')


    models = {
        u'scraper.basecrawl': {
            'Meta': {'object_name': 'BaseCrawl'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'proxy': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['scraper.ProxyServer']", 'null': 'True', 'on_delete': 'models.PROTECT', 'blank': 'True'}),
            'user_agent': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['scraper.UserAgent']", 'null': 'True', 'on_delete': 'models.PROTECT', 'blank': 'True'})
        },
        u'scraper.collector': {
            'Meta': {'object_name': 'Collector', '_ormbases': [u'scraper.BaseCrawl']},
            u'basecrawl_ptr': ('django.db.models.fields.related.OneToOneField', [], {'to': u"orm['scraper.BaseCrawl']", 'unique': 'True', 'primary_key': 'True'}),
            'black_words': ('django.db.models.fields.CharField', [], {'max_length': '256', 'null': 'True', 'blank': 'True'}),
            'get_image': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '256'}),
            'replace_rules': ('jsonfield.fields.JSONField', [], {'default': '{}'}),
            'selectors': ('django.db.models.fields.related.ManyToManyField', [], {'to': u"orm['scraper.Selector']", 'symmetrical': 'False', 'blank': 'True'})
        },
        u'scraper.localcontent': {
            'Meta': {'object_name': 'LocalContent'},
            'collector': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['scraper.Collector']"}),
            'created_time': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now', 'null': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'local_path': ('django.db.models.fields.CharField', [], {'max_length': '256'}),
            'state': ('django.db.models.fields.IntegerField', [], {'default': '0'}),
            'url': ('django.db.models.fields.CharField', [], {'max_length': '256'})
        },
        u'scraper.proxyserver': {
            'Meta': {'object_name': 'ProxyServer'},
            'address': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '64'}),
            'port': ('django.db.models.fields.IntegerField', [], {}),
            'protocol': ('django.db.models.fields.CharField', [], {'max_length': '16'})
        },
        u'scraper.result': {
            'Meta': {'object_name': 'Result'},
            'data': ('jsonfield.fields.JSONField', [], {'default': '{}'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'other': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['scraper.LocalContent']", 'null': 'True', 'on_delete': 'models.SET_NULL', 'blank': 'True'}),
            'task_id': ('django.db.models.fields.CharField', [], {'max_length': '64', 'null': 'True', 'blank': 'True'})
        },
        u'scraper.selector': {
            'Meta': {'object_name': 'Selector'},
            'data_type': ('django.db.models.fields.CharField', [], {'max_length': '64'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'key': ('django.db.models.fields.SlugField', [], {'max_length': '50'}),
            'xpath': ('django.db.models.fields.CharField', [], {'max_length': '512'})
        },
        u'scraper.spider': {
            'Meta': {'object_name': 'Spider', '_ormbases': [u'scraper.BaseCrawl']},
            u'basecrawl_ptr': ('django.db.models.fields.related.OneToOneField', [], {'to': u"orm['scraper.BaseCrawl']", 'unique': 'True', 'primary_key': 'True'}),
            'collectors': ('django.db.models.fields.related.ManyToManyField', [], {'to': u"orm['scraper.Collector']", 'symmetrical': 'False', 'blank': 'True'}),
            'crawl_depth': ('django.db.models.fields.PositiveIntegerField', [], {'default': '1'}),
            'expand_links': ('jsonfield.fields.JSONField', [], {'default': '{}'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '256', 'null': 'True', 'blank': 'True'}),
            'target_links': ('jsonfield.fields.JSONField', [], {'default': '{}'}),
            'url': ('django.db.models.fields.URLField', [], {'max_length': '256'})
        },
        u'scraper.useragent': {
            'Meta': {'object_name': 'UserAgent'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '64'}),
            'value': ('django.db.models.fields.CharField', [], {'max_length': '256'})
        }
    }

    complete_apps = ['scraper']