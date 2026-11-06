from django.contrib import admin
from .models import Flower

@admin.register(Flower)
class FlowerAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'shop', 'default_rate', 'unit', 'status')
    list_filter = ('shop', 'status')
    search_fields = ('code', 'name')
