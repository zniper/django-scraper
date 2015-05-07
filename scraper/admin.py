from django.contrib import admin

import models

admin.site.register(models.Spider)
admin.site.register(models.Collector)
admin.site.register(models.Selector)

admin.site.register(models.Result)
admin.site.register(models.LocalContent)
admin.site.register(models.UserAgent)
admin.site.register(models.ProxyServer)
