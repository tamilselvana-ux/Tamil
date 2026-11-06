from django.contrib import admin
from .models import ShopProfile

@admin.register(ShopProfile)
class ShopProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'shop', 'status', 'phone', 'created_at', 'approved_by')
    list_filter = ('status',)
    search_fields = ('user__username', 'shop__name', 'shop__code')
