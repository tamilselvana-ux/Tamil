from django.contrib import admin
from .models import Shop

@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'phone', 'email', 'created_at')
    search_fields = ('code', 'name', 'phone')
