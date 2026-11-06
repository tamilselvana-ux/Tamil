from functools import wraps
from django.shortcuts import redirect
from django.urls import reverse
from django.http import JsonResponse
from apps.shops.models import Shop
from apps.accounts.models import ShopProfile


def get_user_shop(user):
    """
    Safely retrieves the Shop instance associated with the user.
    - If user has a ShopProfile: returns profile.shop.
    - If user is a superuser (without a dedicated ShopProfile):
      falls back to the primary shop (Shop.objects.first()) so admins can
      test and inspect terminal, parties, flowers, and bills seamlessly.
    - Otherwise returns None.
    """
    if not user or not user.is_authenticated:
        return None
    try:
        if hasattr(user, 'shopprofile') and user.shopprofile.shop:
            return user.shopprofile.shop
    except Exception:
        pass

    if getattr(user, 'is_superuser', False):
        return Shop.objects.first()
    return None


def shop_required(view_func):
    """
    Requires the user to be authenticated and linked to an APPROVED ShopProfile
    (or be a superuser). Attaches `request.shop` for seamless downstream usage.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/api/'):
                return JsonResponse({'status': 'error', 'message': 'Authentication required.'}, status=401)
            login_url = reverse('login')
            return redirect(f"{login_url}?next={request.get_full_path()}")

        shop = get_user_shop(request.user)

        # Superuser access
        if request.user.is_superuser:
            if not shop:
                return redirect('super_admin')
            request.shop = shop
            return view_func(request, *args, **kwargs)

        profile = None
        try:
            profile = request.user.shopprofile
        except Exception:
            profile = None

        if not profile or not shop:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/api/'):
                return JsonResponse({'status': 'error', 'message': 'No shop profile associated with this account.'}, status=403)
            login_url = reverse('login')
            return redirect(f"{login_url}?next={request.get_full_path()}")

        if profile.status == ShopProfile.STATUS_PENDING:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/api/'):
                return JsonResponse({'status': 'error', 'message': 'Shop registration is pending approval.'}, status=403)
            return redirect('pending')

        if profile.status != ShopProfile.STATUS_APPROVED:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/api/'):
                return JsonResponse({'status': 'error', 'message': f'Shop account is {profile.status}.'}, status=403)
            login_url = reverse('login')
            return redirect(f"{login_url}?next={request.get_full_path()}")

        request.shop = shop
        return view_func(request, *args, **kwargs)
    return _wrapped_view
