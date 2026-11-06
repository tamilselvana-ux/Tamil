import json
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse, HttpResponseForbidden
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from django.db.models import Sum
from apps.shops.models import Shop
from apps.accounts.models import ShopProfile, GoogleAdminCredential, GoogleProvisioningAuditLog
from apps.parties.models import Supplier
from apps.flowers.models import Flower
from apps.purchases.models import PurchaseLot, Posting
from apps.core.security import is_login_rate_limited, increment_login_attempts, reset_login_attempts
from apps.core.google_auth import get_authorization_url, exchange_code_for_tokens
from apps.core.google_sheets_provisioner import approve_shop_and_provision_sheet

def login_view(request):
    """
    Real authentication with Django credentials, session management,
    status gating (PENDING/APPROVED), brute-force rate limiting (15-min lockout),
    and safe ?next= redirection.
    """
    next_url = request.POST.get('next') or request.GET.get('next', '')

    def get_safe_redirect(default_target):
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            return redirect(next_url)
        return redirect(default_target)

    if request.user.is_authenticated:
        profile = None
        try:
            profile = request.user.shopprofile
        except Exception:
            profile = None
        if profile and profile.status == ShopProfile.STATUS_APPROVED:
            return get_safe_redirect('terminal')
        elif profile and profile.status == ShopProfile.STATUS_PENDING:
            return redirect('pending')
        elif request.user.is_superuser:
            return get_safe_redirect('super_admin')

    if request.method == 'POST':
        username_or_email = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        if is_login_rate_limited(request):
            return render(request, 'accounts/login.html', {
                'error': 'Too many failed login attempts. Please wait 15 minutes before trying again.',
                'entered_username': username_or_email,
                'next': next_url
            }, status=429)

        # Authenticate via custom backend (case-insensitive username or email)
        user = authenticate(request, username=username_or_email, password=password)

        if not user:
            increment_login_attempts(request)
            return render(request, 'accounts/login.html', {
                'error': 'Invalid username or password.',
                'entered_username': username_or_email,
                'next': next_url
            }, status=401)

        reset_login_attempts(request)

        # Superuser bypass
        if user.is_superuser:
            login(request, user)
            return get_safe_redirect('super_admin')

        # Check shop profile status
        profile = None
        try:
            profile = user.shopprofile
        except Exception:
            profile = None

        if not profile:
            return render(request, 'accounts/login.html', {
                'error': 'No shop account found for this user.',
                'entered_username': username_or_email,
                'next': next_url
            }, status=403)

        if profile.status == ShopProfile.STATUS_PENDING:
            return redirect('pending')
        elif profile.status == ShopProfile.STATUS_APPROVED:
            login(request, user)
            return get_safe_redirect('terminal')
        else:
            return render(request, 'accounts/login.html', {
                'error': f'Your shop account is {profile.status}. Please contact the administrator.',
                'entered_username': username_or_email,
                'next': next_url
            }, status=403)

    return render(request, 'accounts/login.html', {'next': next_url})

def logout_view(request):
    logout(request)
    return redirect('login')

def register_view(request):
    """
    Shop registration: creates a Shop and User with hashed password,
    linking a ShopProfile in PENDING status.
    """
    if request.method == 'POST':
        shop_name = request.POST.get('shop_name', '').strip()
        market_address = request.POST.get('market_address', '').strip()
        username = request.POST.get('owner_username', '').strip()
        email = request.POST.get('gmail_id', '').strip()
        phone = request.POST.get('phone', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')

        errors = []
        if not (shop_name and username and email and phone and password):
            errors.append('All required fields must be completed.')

        if password != confirm_password:
            errors.append('Passwords do not match.')

        if User.objects.filter(username__iexact=username).exists():
            errors.append('Username is already taken. Please choose another.')

        if User.objects.filter(email__iexact=email).exists():
            errors.append('Email is already registered. Please sign in or use another email.')

        try:
            validate_password(password)
        except ValidationError as e:
            errors.extend(e.messages)

        if errors:
            return render(request, 'accounts/register.html', {
                'error': ' '.join(errors),
                'admin_phone': settings.ADMIN_CONTACT_NUMBER,
                'form_data': request.POST
            }, status=400)

        with transaction.atomic():
            shop = Shop.objects.create(
                code=Shop.generate_code(),
                name=shop_name,
                market_address=market_address,
                phone=phone,
                email=email
            )
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password
            )
            ShopProfile.objects.create(
                user=user,
                shop=shop,
                status=ShopProfile.STATUS_PENDING,
                phone=phone
            )

        return redirect('pending')

    return render(request, 'accounts/register.html', {
        'admin_phone': settings.ADMIN_CONTACT_NUMBER
    })

def pending_view(request):
    return render(request, 'accounts/pending.html', {
        'admin_phone': settings.ADMIN_CONTACT_NUMBER
    })

@login_required
def super_admin_view(request):
    """
    Super Admin Command Center:
    - Oversees platform-wide trading turnover, lots, postings, and suppliers
    - Comprehensive shop registration approval workflow
    - Cross-shop activity monitor and audit feed
    """
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access restricted to platform Super Administrators.")

    profiles = ShopProfile.objects.select_related('shop', 'user', 'approved_by').order_by('-created_at')

    # Platform Counters
    total_shops = profiles.count()
    pending_count = profiles.filter(status=ShopProfile.STATUS_PENDING).count()
    active_count = profiles.filter(status=ShopProfile.STATUS_APPROVED).count()
    rejected_count = profiles.filter(status=ShopProfile.STATUS_REJECTED).count()
    deactivated_count = profiles.filter(status=ShopProfile.STATUS_DEACTIVATED).count()

    total_lots = PurchaseLot.objects.count()
    total_postings = Posting.objects.count()
    total_suppliers = Supplier.objects.count()
    total_flowers = Flower.objects.count()

    turnover_agg = PurchaseLot.objects.aggregate(total=Sum('gross_value'))
    total_turnover = turnover_agg['total'] or 0

    settled_agg = Posting.objects.aggregate(total=Sum('net_balance'))
    total_settled = settled_agg['total'] or 0

    # Per-Shop Detailed Matrix
    shops_data = []
    for p in profiles:
        s = p.shop
        sup_cnt = Supplier.objects.filter(shop=s).count()
        lots_cnt = PurchaseLot.objects.filter(shop=s).count()
        open_lots_cnt = PurchaseLot.objects.filter(shop=s, posting__isnull=True).count()
        postings_cnt = Posting.objects.filter(shop=s).count()
        shop_turnover = PurchaseLot.objects.filter(shop=s).aggregate(t=Sum('gross_value'))['t'] or 0

        shops_data.append({
            'profile_id': p.id,
            'shop_id': s.code,
            'name': s.name,
            'market_address': s.market_address or 'Market Stall',
            'owner_username': p.user.username,
            'gmail_id': p.user.email,
            'phone': p.phone or s.phone,
            'created_at': p.created_at.strftime('%Y-%m-%d %H:%M'),
            'status': p.status,
            'approved_by': p.approved_by.username if p.approved_by else None,
            'approved_at': p.approved_at.strftime('%Y-%m-%d %H:%M') if p.approved_at else None,
            'suppliers_count': sup_cnt,
            'lots_count': lots_cnt,
            'open_lots_count': open_lots_cnt,
            'postings_count': postings_cnt,
            'turnover': f"{shop_turnover:.2f}",
            'google_sheet_id': p.google_sheet_id,
            'google_sheet_url': p.google_sheet_url,
            'sheet_provision_error': p.sheet_provision_error,
        })

    # Recent Platform Activity Stream
    recent_lots = PurchaseLot.objects.select_related('shop', 'supplier').order_by('-created_at')[:8]
    recent_postings = Posting.objects.select_related('shop', 'supplier').order_by('-created_at')[:6]

    # Google Drive & Sheets OAuth Integration Status
    google_credential = GoogleAdminCredential.objects.filter(id=1).first()

    context = {
        'profiles': profiles,
        'shops': shops_data,
        'total_shops': total_shops,
        'pending_count': pending_count,
        'active_count': active_count,
        'rejected_count': rejected_count,
        'deactivated_count': deactivated_count,
        'total_lots': total_lots,
        'total_postings': total_postings,
        'total_suppliers': total_suppliers,
        'total_flowers': total_flowers,
        'total_turnover': f"{total_turnover:,.2f}",
        'total_settled': f"{total_settled:,.2f}",
        'recent_lots': recent_lots,
        'recent_postings': recent_postings,
        'google_credential': google_credential,
        'google_connected': request.GET.get('google_connected') == '1',
        'google_disconnected': request.GET.get('google_disconnected') == '1',
        'google_error': request.GET.get('google_error', ''),
    }
    return render(request, 'accounts/super_admin.html', context)

def update_shop_status_api(request):
    """Super Admin action API with CSRF protection and is_superuser check."""
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'Authentication required.'}, status=401)
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Forbidden'}, status=403)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            profile_id = data.get('profile_id')
            shop_id = data.get('shop_id')
            new_status = data.get('status')

            valid_statuses = [
                ShopProfile.STATUS_APPROVED,
                ShopProfile.STATUS_REJECTED,
                ShopProfile.STATUS_DEACTIVATED,
                ShopProfile.STATUS_PENDING,
                ShopProfile.STATUS_APPROVED_SHEET_PENDING,
                'RETRY_PROVISION'
            ]
            if new_status not in valid_statuses:
                return JsonResponse({'status': 'error', 'message': 'Invalid status.'}, status=400)

            if profile_id:
                profile = get_object_or_404(ShopProfile, pk=profile_id)
            elif shop_id:
                profile = get_object_or_404(ShopProfile, shop__code=shop_id)
            else:
                return JsonResponse({'status': 'error', 'message': 'Missing shop or profile identifier.'}, status=400)

            # Automated Google Sheets Provisioning upon Approval or Retry
            if new_status in [ShopProfile.STATUS_APPROVED, 'RETRY_PROVISION']:
                success, profile, msg = approve_shop_and_provision_sheet(profile.id, request.user)
                return JsonResponse({
                    'status': 'success',
                    'profile_id': profile.id,
                    'shop_code': profile.shop.code,
                    'new_status': profile.status,
                    'sheet_id': profile.google_sheet_id,
                    'sheet_url': profile.google_sheet_url,
                    'provision_success': success,
                    'message': msg
                })

            profile.status = new_status
            profile.save(update_fields=['status'])

            return JsonResponse({
                'status': 'success',
                'profile_id': profile.id,
                'shop_code': profile.shop.code,
                'new_status': profile.status
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    return JsonResponse({'status': 'invalid_method'}, status=405)


def admin_google_connect_view(request):
    """
    Super Admin only: Starts the Google OAuth 2.0 authorization flow.
    Enforces access_type=offline and prompt=consent to ensure a refresh token is returned.
    """
    if not request.user.is_authenticated:
        login_url = reverse('login')
        return redirect(f"{login_url}?next={request.path}")
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access restricted to platform super administrators.")

    auth_url, state = get_authorization_url(request)
    if not auth_url:
        return redirect('/super-admin/?google_error=Client+ID+or+Secret+missing+in+settings')

    request.session['google_oauth_state'] = state
    return redirect(auth_url)


def admin_google_callback_view(request):
    """
    Super Admin only: OAuth 2.0 callback endpoint.
    Exchanges authorization code for credentials and saves the encrypted refresh token.
    """
    if not request.user.is_authenticated:
        login_url = reverse('login')
        return redirect(f"{login_url}?next={request.path}")
    if not request.user.is_superuser:
        return HttpResponseForbidden("Access restricted to platform super administrators.")

    error = request.GET.get('error')
    if error:
        return redirect(f'/super-admin/?google_error={error}')

    code = request.GET.get('code')
    state = request.GET.get('state')
    saved_state = request.session.get('google_oauth_state')

    if not code:
        return redirect('/super-admin/?google_error=Authorization+code+not+provided')

    if saved_state and state != saved_state:
        return redirect('/super-admin/?google_error=Invalid+OAuth+state+parameter')

    try:
        exchange_code_for_tokens(request, code, admin_user=request.user)
        return redirect('/super-admin/?google_connected=1')
    except Exception as e:
        return redirect(f'/super-admin/?google_error={str(e)}')


def admin_google_disconnect_view(request):
    """
    Super Admin only: Disconnects the Google Drive & Sheets OAuth connection.
    """
    if not request.user.is_authenticated or not request.user.is_superuser:
        return HttpResponseForbidden("Access restricted to platform super administrators.")

    if request.method == 'POST':
        GoogleAdminCredential.objects.all().delete()
        GoogleProvisioningAuditLog.objects.create(
            admin_user=request.user,
            action="OAUTH_DISCONNECTED",
            status="SUCCESS",
            details="Admin disconnected Google OAuth credentials."
        )
        return redirect('/super-admin/?google_disconnected=1')

    return redirect('super_admin')

