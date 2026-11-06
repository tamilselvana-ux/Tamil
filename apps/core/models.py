from django.db import models

class TenantQuerySet(models.QuerySet):
    def for_shop(self, shop):
        if shop is None:
            return self.none()
        return self.filter(shop=shop)

class TenantManager(models.Manager):
    def get_queryset(self):
        return TenantQuerySet(self.model, using=self._db)

    def for_shop(self, shop):
        return self.get_queryset().for_shop(shop)

class TenantModel(models.Model):
    shop = models.ForeignKey('shops.Shop', on_delete=models.CASCADE, related_name='%(class)ss')

    objects = TenantManager()

    class Meta:
        abstract = True
