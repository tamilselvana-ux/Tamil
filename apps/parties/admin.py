from django.contrib import admin
from .models import Supplier, Area, LedgerGroup

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'shop', 'area_name', 'commission_pct', 'adv_opening', 'status')
    list_filter = ('shop', 'status')
    search_fields = ('code', 'name')

@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ('name', 'shop')
    list_filter = ('shop',)

@admin.register(LedgerGroup)
class LedgerGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'shop')
    list_filter = ('shop',)
