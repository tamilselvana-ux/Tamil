from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views
from apps.purchases import views as purchase_views
from apps.parties import views as party_views
from apps.accounts import views as account_views
from apps.flowers import views as flower_views
from apps.core import views as core_views

urlpatterns = [
    # Health Check & Diagnostics
    path('health/', core_views.health_check_view, name='health_check'),

    # Terminal & Purchases
    path('', purchase_views.terminal_view, name='home'),
    path('terminal/', purchase_views.terminal_view, name='terminal'),
    path('api/purchases/save/', purchase_views.save_purchase_lot_api, name='api_purchase_save'),
    path('api/purchases/batch-save/', purchase_views.save_purchase_lots_batch_api, name='api_purchase_batch_save'),
    path('api/postings/create/', purchase_views.create_posting_api, name='api_posting_create'),
    path('api/purchases/list/', purchase_views.purchase_list_api, name='api_purchase_list'),

    # Koyambedu Reports & PDF Generator
    path('invoice/', purchase_views.invoice_view, name='invoice'),
    path('invoice/download-pdf/', purchase_views.download_pdf_view, name='download_pdf'),

    # Supplier / Party Master & Autocomplete
    path('parties/', party_views.suppliers_view, name='suppliers'),
    path('api/parties/autocomplete/', party_views.supplier_autocomplete_api, name='api_supplier_autocomplete'),
    path('api/parties/save/', party_views.save_supplier_api, name='api_supplier_save'),
    path('api/parties/delete/<str:supplier_id>/', party_views.delete_supplier_api, name='api_supplier_delete'),
    path('api/parties/<str:code>/', party_views.supplier_detail_api, name='api_supplier_detail'),

    # Flower Catalog
    path('flowers/', flower_views.flowers_view, name='flowers'),
    path('api/flowers/list/', flower_views.flowers_list_api, name='api_flowers_list'),
    path('api/flowers/save/', flower_views.save_flower_api, name='api_flower_save'),

    # Shop Registration, Authentication & Password Reset
    path('register/', account_views.register_view, name='register'),
    path('pending/', account_views.pending_view, name='pending'),
    path('login/', account_views.login_view, name='login'),
    path('logout/', account_views.logout_view, name='logout'),
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='accounts/password_reset.html',
        email_template_name='accounts/password_reset_email.txt',
        subject_template_name='accounts/password_reset_subject.txt'
    ), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='accounts/password_reset_done.html'
    ), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='accounts/password_reset_confirm.html'
    ), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='accounts/password_reset_complete.html'
    ), name='password_reset_complete'),

    # Super Admin
    path('super-admin/', account_views.super_admin_view, name='super_admin'),
    path('api/super-admin/update-status/', account_views.update_shop_status_api, name='api_update_shop_status'),
    path('super-admin/google/connect/', account_views.admin_google_connect_view, name='admin_google_connect'),
    path('super-admin/google/callback/', account_views.admin_google_callback_view, name='admin_google_callback'),
    path('super-admin/google/disconnect/', account_views.admin_google_disconnect_view, name='admin_google_disconnect'),
    path('django-admin/', admin.site.urls),
]
