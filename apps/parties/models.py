from decimal import Decimal
from django.db import models
from apps.core.models import TenantModel

class LedgerGroup(TenantModel):
    name = models.CharField(max_length=120)

    class Meta:
        verbose_name = 'Ledger Group'
        verbose_name_plural = 'Ledger Groups'
        unique_together = ('shop', 'name')

    def __str__(self):
        return self.name

class Area(TenantModel):
    name = models.CharField(max_length=120)

    class Meta:
        verbose_name = 'Area'
        verbose_name_plural = 'Areas'
        unique_together = ('shop', 'name')

    def __str__(self):
        return self.name

class Supplier(TenantModel):
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Inactive', 'Inactive'),
    ]

    code = models.CharField(max_length=60, db_index=True)
    name = models.CharField(max_length=200)
    ledger_group = models.ForeignKey(LedgerGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='suppliers')
    ledger_op_bal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    area = models.ForeignKey(Area, on_delete=models.SET_NULL, null=True, blank=True, related_name='suppliers')
    area_name = models.CharField(max_length=120, blank=True, default='')
    flower_name = models.CharField(max_length=120, blank=True, default='')
    adv_opening = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    advances_given = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    advances_recovered = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    commission_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('15.00'))
    luggage_default = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('150.00'))
    gate_charges = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    interest_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Supplier'
        verbose_name_plural = 'Suppliers'
        unique_together = ('shop', 'code')
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def outstanding_advance(self):
        """Current outstanding advance available to recover on bills."""
        return (self.adv_opening + self.advances_given - self.advances_recovered).quantize(Decimal('0.01'))
