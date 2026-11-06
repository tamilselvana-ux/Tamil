from decimal import Decimal
from django.db import models
from apps.core.models import TenantModel

class Flower(TenantModel):
    code = models.CharField(max_length=50, db_index=True)
    name = models.CharField(max_length=150)
    default_rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    unit = models.CharField(max_length=20, default='kg')
    status = models.CharField(max_length=20, default='Active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Flower'
        verbose_name_plural = 'Flowers'
        unique_together = ('shop', 'code')
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"
