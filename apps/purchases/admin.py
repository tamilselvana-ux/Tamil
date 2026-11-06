from django.contrib import admin
from .models import PurchaseLot, Posting

@admin.register(Posting)
class PostingAdmin(admin.ModelAdmin):
    list_display = ('posting_no', 'shop', 'supplier_name', 'from_date', 'to_date', 'gross_total', 'net_balance')
    list_filter = ('shop',)
    search_fields = ('posting_no', 'supplier_name')

@admin.register(PurchaseLot)
class PurchaseLotAdmin(admin.ModelAdmin):
    list_display = ('lot_id', 'shop', 'purchase_date', 'party_code', 'flower_code', 'weight', 'rate', 'gross_value', 'posting_no')
    list_filter = ('shop', 'purchase_date')
    search_fields = ('party_code', 'flower_code', 'posting_no')
