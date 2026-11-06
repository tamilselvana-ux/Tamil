from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User

class CaseInsensitiveEmailOrUsernameBackend(ModelBackend):
    """
    Authenticates against django.contrib.auth.models.User using either
    case-insensitive username or case-insensitive email address.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        username = username.strip()

        # Case-insensitive lookup on username first, then email
        user = User.objects.filter(username__iexact=username).first()
        if not user:
            user = User.objects.filter(email__iexact=username).first()

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
