from django.contrib import admin

import models


class CrawlUrlInline(admin.TabularInline):
    model = models.CrawlUrl
    min_num = 0
    extra = 0


class DataItemInline(admin.TabularInline):
    model = models.DataItem
    min_num = 0
    extra = 0


class CollectorInline(admin.TabularInline):
    model = models.Collector
    min_num = 0
    extra = 0


class SelectorInline(admin.TabularInline):
    model = models.Selector
    min_num = 0
    extra = 0


class SpiderAdmin(admin.ModelAdmin):
    """Spider model admin."""
    inlines = [CrawlUrlInline, DataItemInline]


class DataItemAdmin(admin.ModelAdmin):
    """DataItem model admin."""
    inlines = [CollectorInline]


class CollectorAdmin(admin.ModelAdmin):
    """Collector model admin."""
    inlines = [SelectorInline]


admin.site.register(models.Spider, SpiderAdmin)
admin.site.register(models.CrawlUrl)
admin.site.register(models.DataItem, DataItemAdmin)
admin.site.register(models.Collector, CollectorAdmin)
admin.site.register(models.Selector)

admin.site.register(models.Result)
admin.site.register(models.LocalContent)
admin.site.register(models.UserAgent)
admin.site.register(models.ProxyServer)
