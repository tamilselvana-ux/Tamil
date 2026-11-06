import os
import json
import logging
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow

from apps.accounts.models import GoogleAdminCredential, GoogleProvisioningAuditLog

logger = logging.getLogger('apps.google_auth')


def get_oauth_client_config():
    """Returns Google client configuration dictionary from Django settings."""
    client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '')
    client_secret = getattr(settings, 'GOOGLE_CLIENT_SECRET', '')
    if not client_id or not client_secret:
        return None
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs"
        }
    }


def get_redirect_uri(request=None):
    """Calculates redirect URI based on settings or incoming request host."""
    configured_uri = getattr(settings, 'GOOGLE_REDIRECT_URI', '')
    if configured_uri and configured_uri.strip():
        return configured_uri.strip()
    if request:
        return request.build_absolute_uri('/super-admin/google/callback/')
    return 'http://localhost:8000/super-admin/google/callback/'


def create_oauth_flow(request=None):
    """Creates a Google OAuth Flow object initialized with scopes and client config."""
    client_config = get_oauth_client_config()
    if not client_config:
        return None

    # Allow OAuth over HTTP for local testing/development
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

    flow = Flow.from_client_config(
        client_config=client_config,
        scopes=settings.GOOGLE_OAUTH_SCOPES,
        redirect_uri=get_redirect_uri(request)
    )
    return flow


def get_authorization_url(request):
    """
    Generates the Google OAuth authorization URL.
    Enforces access_type='offline' and prompt='consent' to guarantee a refresh token.
    """
    flow = create_oauth_flow(request)
    if not flow:
        return None, None

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        prompt='consent',
        include_granted_scopes='true'
    )
    return authorization_url, state


def exchange_code_for_tokens(request, code: str, admin_user=None):
    """
    Exchanges authorization code for credentials and saves them encrypted in the database.
    """
    flow = create_oauth_flow(request)
    if not flow:
        raise ValueError("Google OAuth client is not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.")

    flow.fetch_token(code=code)
    credentials = flow.credentials

    # Extract user email from token id_info if available
    admin_email = ''
    try:
        from googleapiclient.discovery import build
        userinfo_service = build('oauth2', 'v2', credentials=credentials)
        userinfo = userinfo_service.userinfo().get().execute()
        admin_email = userinfo.get('email', '')
    except Exception as e:
        logger.warning(f"Could not fetch Google user info email: {e}")

    refresh_token = credentials.refresh_token
    access_token = credentials.token
    expiry = credentials.expiry

    if expiry and timezone.is_naive(expiry):
        expiry = timezone.make_aware(expiry)

    # Store in database
    cred_obj, _ = GoogleAdminCredential.objects.get_or_create(id=1)
    if admin_user:
        cred_obj.admin_user = admin_user
    if admin_email:
        cred_obj.admin_email = admin_email
    if refresh_token:
        cred_obj.set_refresh_token(refresh_token)
    cred_obj.access_token = access_token
    cred_obj.token_expiry = expiry or (timezone.now() + timedelta(hours=1))
    cred_obj.scopes = " ".join(credentials.scopes or settings.GOOGLE_OAUTH_SCOPES)
    cred_obj.is_valid = True
    cred_obj.last_error = ''
    cred_obj.save()

    GoogleProvisioningAuditLog.objects.create(
        admin_user=admin_user,
        action="OAUTH_CONNECTED",
        status="SUCCESS",
        details=f"Admin connected Google Account ({admin_email or 'OAuth'}) with offline refresh token."
    )

    return cred_obj


def get_admin_credentials():
    """
    Retrieves Google OAuth credentials for the Admin.
    Automatically refreshes expired access tokens using the encrypted refresh token.
    Flags is_valid=False if the refresh token was revoked.
    """
    cred_obj = GoogleAdminCredential.objects.filter(id=1).first()
    if not cred_obj:
        return None

    refresh_token = cred_obj.get_refresh_token()
    if not refresh_token:
        cred_obj.is_valid = False
        cred_obj.last_error = "No refresh token stored. Re-authorization required."
        cred_obj.save(update_fields=['is_valid', 'last_error'])
        return None

    client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '')
    client_secret = getattr(settings, 'GOOGLE_CLIENT_SECRET', '')

    credentials = Credentials(
        token=cred_obj.access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=cred_obj.scopes.split() if cred_obj.scopes else settings.GOOGLE_OAUTH_SCOPES
    )

    # Auto-refresh if expired or about to expire
    try:
        now = timezone.now()
        needs_refresh = not cred_obj.token_expiry or (cred_obj.token_expiry <= now + timedelta(minutes=5))
        if needs_refresh:
            credentials.refresh(Request())
            cred_obj.access_token = credentials.token
            expiry = credentials.expiry
            if expiry and timezone.is_naive(expiry):
                expiry = timezone.make_aware(expiry)
            cred_obj.token_expiry = expiry or (timezone.now() + timedelta(hours=1))
            cred_obj.is_valid = True
            cred_obj.last_error = ''
            cred_obj.save(update_fields=['access_token', 'token_expiry', 'is_valid', 'last_error', 'updated_at'])
            logger.info("Successfully refreshed Google Admin access token.")
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to refresh Google OAuth token: {error_msg}")
        cred_obj.is_valid = False
        cred_obj.last_error = f"Token refresh failed: {error_msg}"
        cred_obj.save(update_fields=['is_valid', 'last_error', 'updated_at'])

        GoogleProvisioningAuditLog.objects.create(
            admin_user=cred_obj.admin_user,
            action="OAUTH_REFRESH_FAILED",
            status="FAILURE",
            details=error_msg
        )
        return None

    return credentials
