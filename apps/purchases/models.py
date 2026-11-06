import uuid
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from apps.core.models import TenantModel
from apps.parties.models import Supplier
from apps.flowers.models import Flower

class Posting(TenantModel):
    posting_no = models.CharField(max_length=30, db_index=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='postings')
    supplier_name = models.CharField(max_length=200)
    from_date = models.DateField()
    to_date = models.DateField()
    gross_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    commission = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    total_luggage = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    total_coolie = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    total_expense = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    adv_deducted = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    total_less = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    net_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_postings')

    class Meta:
        verbose_name = 'Posting Cutoff'
        verbose_name_plural = 'Posting Cutoffs'
        unique_together = ('shop', 'posting_no')
        ordering = ['-created_at']

    def __str__(self):
        return f"Posting #{self.posting_no} - {self.supplier_name} ({self.from_date} to {self.to_date})"

class PurchaseLot(TenantModel):
    lot_id = models.CharField(max_length=60, unique=True, db_index=True, default=uuid.uuid4)
    purchase_date = models.DateField(db_index=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='lots', null=True, blank=True)
    party_code = models.CharField(max_length=60, db_index=True)
    party_name = models.CharField(max_length=200)
    flower = models.ForeignKey(Flower, on_delete=models.SET_NULL, null=True, blank=True, related_name='lots')
    flower_code = models.CharField(max_length=50)
    flower_name = models.CharField(max_length=150)
    weight = models.DecimalField(max_digits=10, decimal_places=3)
    rate = models.DecimalField(max_digits=10, decimal_places=2)
    gross_value = models.DecimalField(max_digits=14, decimal_places=2)
    boxes = models.IntegerField(default=0)
    lug_rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    luggage_amt = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    coolie_rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('15.00'))
    coolie_amt = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    net_lot_value = models.DecimalField(max_digits=14, decimal_places=2)
    posting = models.ForeignKey(Posting, on_delete=models.SET_NULL, null=True, blank=True, related_name='lots')
    posting_no = models.CharField(max_length=30, blank=True, null=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Purchase Lot'
        verbose_name_plural = 'Purchase Lots'
        ordering = ['-purchase_date', '-created_at']

    def __str__(self):
        return f"{self.party_code} - {self.flower_name} ({self.weight}kg @ ₹{self.rate})"

    @property
    def is_posted(self):
        return bool(self.posting or self.posting_no)
