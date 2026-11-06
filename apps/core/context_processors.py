from django.conf import settings
from apps.core.decorators import get_user_shop

def shop_context(request):
    """Provides current shop, user profile, and administrative parameters to templates."""
    shop = None
    profile = None
    if hasattr(request, 'user') and request.user.is_authenticated:
        try:
            profile = request.user.shopprofile
        except Exception:
            profile = None
        shop = getattr(request, 'shop', None) or get_user_shop(request.user)
    return {
        'current_shop': shop,
        'current_profile': profile,
        'admin_phone': settings.ADMIN_CONTACT_NUMBER,
    }
