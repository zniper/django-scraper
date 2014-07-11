from django.contrib import admin

import models

admin.site.register(models.Source)
admin.site.register(models.ContentType)
admin.site.register(models.LocalContent)
admin.site.register(models.WordSet)
admin.site.register(models.UserAgent)
admin.site.register(models.ProxyServer)
