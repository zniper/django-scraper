# -*- coding: utf-8 -*-
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding field 'Spider.crawl_root'
        db.add_column(u'scraper_spider', 'crawl_root',
                      self.gf('django.db.models.fields.BooleanField')(default=False),
                      keep_default=False)


    def backwards(self, orm):
        # Deleting field 'Spider.crawl_root'
        db.delete_column(u'scraper_spider', 'crawl_root')


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
            'crawl_root': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
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