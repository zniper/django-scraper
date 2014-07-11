# -*- coding: utf-8 -*-
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'Source'
        db.create_table(u'scraper_source', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('url', self.gf('django.db.models.fields.CharField')(max_length=256)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=256, null=True, blank=True)),
            ('link_xpath', self.gf('django.db.models.fields.CharField')(max_length=255)),
            ('expand_rules', self.gf('django.db.models.fields.TextField')(null=True, blank=True)),
            ('crawl_depth', self.gf('django.db.models.fields.PositiveIntegerField')(default=1)),
            ('content_xpath', self.gf('django.db.models.fields.CharField')(max_length=255)),
            ('content_type', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['scraper.ContentType'], null=True, blank=True)),
            ('meta_xpath', self.gf('django.db.models.fields.TextField')(default='', blank=True)),
            ('extra_xpath', self.gf('django.db.models.fields.TextField')(default='', blank=True)),
            ('refine_rules', self.gf('django.db.models.fields.TextField')(default='', blank=True)),
            ('black_words', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['scraper.WordSet'], null=True, blank=True)),
            ('active', self.gf('django.db.models.fields.BooleanField')(default=True)),
            ('download_image', self.gf('django.db.models.fields.BooleanField')(default=True)),
        ))
        db.send_create_signal(u'scraper', ['Source'])

        # Adding model 'LocalContent'
        db.create_table(u'scraper_localcontent', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('url', self.gf('django.db.models.fields.CharField')(max_length=256)),
            ('source', self.gf('django.db.models.fields.related.ForeignKey')(blank=True, related_name='content', null=True, to=orm['scraper.Source'])),
            ('local_path', self.gf('django.db.models.fields.CharField')(max_length=256)),
            ('created_time', self.gf('django.db.models.fields.DateTimeField')(default=datetime.datetime.now, null=True, blank=True)),
        ))
        db.send_create_signal(u'scraper', ['LocalContent'])

        # Adding model 'WordSet'
        db.create_table(u'scraper_wordset', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=64)),
            ('words', self.gf('django.db.models.fields.TextField')()),
        ))
        db.send_create_signal(u'scraper', ['WordSet'])

        # Adding model 'ContentType'
        db.create_table(u'scraper_contenttype', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=64)),
            ('description', self.gf('django.db.models.fields.TextField')(null=True, blank=True)),
        ))
        db.send_create_signal(u'scraper', ['ContentType'])


    def backwards(self, orm):
        # Deleting model 'Source'
        db.delete_table(u'scraper_source')

        # Deleting model 'LocalContent'
        db.delete_table(u'scraper_localcontent')

        # Deleting model 'WordSet'
        db.delete_table(u'scraper_wordset')

        # Deleting model 'ContentType'
        db.delete_table(u'scraper_contenttype')


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
            'refine_rules': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'url': ('django.db.models.fields.CharField', [], {'max_length': '256'})
        },
        u'scraper.wordset': {
            'Meta': {'object_name': 'WordSet'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '64'}),
            'words': ('django.db.models.fields.TextField', [], {})
        }
    }

    complete_apps = ['scraper']