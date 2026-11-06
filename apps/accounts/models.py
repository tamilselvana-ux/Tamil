from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from apps.shops.models import Shop
from apps.core.encryption import encrypt_secret, decrypt_secret


class ShopProfile(models.Model):
    STATUS_PENDING = 'PENDING'
    STATUS_APPROVED = 'APPROVED'
    STATUS_APPROVED_SHEET_PENDING = 'APPROVED_SHEET_PENDING'
    STATUS_REJECTED = 'REJECTED'
    STATUS_DEACTIVATED = 'DEACTIVATED'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Approval'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_APPROVED_SHEET_PENDING, 'Approved (Sheet Pending)'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_DEACTIVATED, 'Deactivated'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='shopprofile')
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='profiles')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    phone = models.CharField(max_length=30, blank=True, default='')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_shops')
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # Dedicated Per-Merchant Google Drive & Sheets Metadata
    google_sheet_id = models.CharField(max_length=150, blank=True, default='', db_index=True)
    google_sheet_url = models.URLField(max_length=500, blank=True, default='')
    google_folder_id = models.CharField(max_length=150, blank=True, default='')
    sheet_provision_error = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Shop Profile'
        verbose_name_plural = 'Shop Profiles'

    def __str__(self):
        return f"{self.user.username} - {self.shop.name} [{self.status}]"

    @property
    def is_approved(self):
        return self.status in [self.STATUS_APPROVED, self.STATUS_APPROVED_SHEET_PENDING]

    @property
    def has_sheet(self):
        return bool(self.google_sheet_id and self.google_sheet_id.strip())


class GoogleAdminCredential(models.Model):
    """
    Stores the Super Admin's Google OAuth 2.0 credentials.
    The refresh token is encrypted at rest using AES/Fernet.
    """
    admin_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='google_credentials', null=True, blank=True)
    admin_email = models.EmailField(blank=True, default='')
    encrypted_refresh_token = models.TextField(blank=True, default='')
    access_token = models.TextField(blank=True, default='')
    token_expiry = models.DateTimeField(null=True, blank=True)
    scopes = models.TextField(blank=True, default='')
    is_valid = models.BooleanField(default=True)
    last_error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Google Admin Credential'
        verbose_name_plural = 'Google Admin Credentials'
        ordering = ['-updated_at']

    def __str__(self):
        status = "Active" if self.is_valid else "Needs Re-authorization"
        return f"Google Admin OAuth ({self.admin_email or 'System'}) - {status}"

    def set_refresh_token(self, plain_token: str):
        if plain_token:
            self.encrypted_refresh_token = encrypt_secret(plain_token)
        else:
            self.encrypted_refresh_token = ''

    def get_refresh_token(self) -> str:
        if not self.encrypted_refresh_token:
            return ''
        try:
            return decrypt_secret(self.encrypted_refresh_token)
        except Exception:
            return ''

    @property
    def is_expired(self) -> bool:
        if not self.token_expiry:
            return True
        return timezone.now() >= self.token_expiry


class GoogleProvisioningAuditLog(models.Model):
    """
    Audit log for Google Drive & Sheets provisioning events.
    Never logs credentials or refresh tokens.
    """
    admin_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, null=True, blank=True)
    action = models.CharField(max_length=100, db_index=True)
    sheet_id = models.CharField(max_length=150, blank=True, default='')
    folder_id = models.CharField(max_length=150, blank=True, default='')
    status = models.CharField(max_length=50, default='SUCCESS')
    details = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Google Provisioning Audit Log'
        verbose_name_plural = 'Google Provisioning Audit Logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.created_at.strftime('%Y-%m-%d %H:%M')}] {self.action} - {self.status}"
