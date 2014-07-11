# -*- coding: utf-8 -*-
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
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

        # Adding field 'Source.proxy'
        db.add_column(u'scraper_source', 'proxy',
                      self.gf('django.db.models.fields.related.ForeignKey')(to=orm['scraper.ProxyServer'], null=True, blank=True),
                      keep_default=False)

        # Adding field 'Source.user_agent'
        db.add_column(u'scraper_source', 'user_agent',
                      self.gf('django.db.models.fields.related.ForeignKey')(to=orm['scraper.UserAgent'], null=True, blank=True),
                      keep_default=False)


    def backwards(self, orm):
        # Deleting model 'UserAgent'
        db.delete_table(u'scraper_useragent')

        # Deleting model 'ProxyServer'
        db.delete_table(u'scraper_proxyserver')

        # Deleting field 'Source.proxy'
        db.delete_column(u'scraper_source', 'proxy_id')

        # Deleting field 'Source.user_agent'
        db.delete_column(u'scraper_source', 'user_agent_id')


    models = {
        u'scraper.contenttype': {
            'Meta': {'object_name': 'ContentType'},
            'description': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '64'})
        },
        u'scraper.localcontent': {
            'Meta': {'object_name': 'LocalContent'},
            'created_time': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now', 'null': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'local_path': ('django.db.models.fields.CharField', [], {'max_length': '256'}),
            'source': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'content'", 'null': 'True', 'to': u"orm['scraper.Source']"}),
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
        u'scraper.source': {
            'Meta': {'object_name': 'Source'},
            'active': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'black_words': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['scraper.WordSet']", 'null': 'True', 'blank': 'True'}),
            'content_type': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['scraper.ContentType']", 'null': 'True', 'blank': 'True'}),
            'content_xpath': ('django.db.models.fields.CharField', [], {'max_length': '255'}),
            'crawl_depth': ('django.db.models.fields.PositiveIntegerField', [], {'default': '1'}),
            'download_image': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'expand_rules': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'extra_xpath': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'link_xpath': ('django.db.models.fields.CharField', [], {'max_length': '255'}),
            'meta_xpath': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '256', 'null': 'True', 'blank': 'True'}),
            'proxy': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['scraper.ProxyServer']", 'null': 'True', 'blank': 'True'}),
            'refine_rules': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'url': ('django.db.models.fields.CharField', [], {'max_length': '256'}),
            'user_agent': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['scraper.UserAgent']", 'null': 'True', 'blank': 'True'})
        },
        u'scraper.useragent': {
            'Meta': {'object_name': 'UserAgent'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '64'}),
            'value': ('django.db.models.fields.CharField', [], {'max_length': '256'})
        },
        u'scraper.wordset': {
            'Meta': {'object_name': 'WordSet'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '64'}),
            'words': ('django.db.models.fields.TextField', [], {})
        }
    }

    complete_apps = ['scraper']