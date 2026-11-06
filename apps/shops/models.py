import uuid
from django.db import models

class Shop(models.Model):
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    market_address = models.TextField(blank=True, default='')
    phone = models.CharField(max_length=30, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    devotional_motto = models.CharField(
        max_length=255,
        default='ARULMIGU VINAYAGA THUNAI   ARULMIGU VEERUCHINNAMMAL THUNAI'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Shop'
        verbose_name_plural = 'Shops'

    def __str__(self):
        return f"{self.name} ({self.code})"

    @classmethod
    def generate_code(cls, prefix="shop"):
        return f"{prefix}-{uuid.uuid4().hex[:8]}"
