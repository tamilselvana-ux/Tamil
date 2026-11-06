from unittest.mock import patch, MagicMock
from datetime import timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from apps.accounts.models import GoogleAdminCredential, GoogleProvisioningAuditLog
from apps.core.encryption import encrypt_secret, decrypt_secret
from apps.core.google_auth import get_admin_credentials, exchange_code_for_tokens


class GoogleOAuthAndTokenTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username='oauth_admin',
            email='admin@floweragency.com',
            password='AdminPassword123!'
        )
        self.regular_user = User.objects.create_user(
            username='regular_clerk',
            email='clerk@floweragency.com',
            password='ClerkPassword123!'
        )

    # 1. Encryption & Decryption Tests
    def test_token_encryption_at_rest(self):
        """Plaintext token must be encrypted at rest and cleanly decrypted."""
        raw_refresh_token = "1//04_fake_refresh_token_abcdef123456789"
        encrypted = encrypt_secret(raw_refresh_token)

        self.assertNotEqual(raw_refresh_token, encrypted)
        self.assertTrue(len(encrypted) > 20)

        decrypted = decrypt_secret(encrypted)
        self.assertEqual(raw_refresh_token, decrypted)

    def test_credential_model_token_handling(self):
        """GoogleAdminCredential model properly encrypts and decrypts refresh tokens."""
        raw_token = "1//09_test_google_secret_token"
        cred = GoogleAdminCredential.objects.create(
            admin_user=self.superuser,
            admin_email='super@google.com',
            access_token='fake_access_123',
            token_expiry=timezone.now() + timedelta(hours=1)
        )
        cred.set_refresh_token(raw_token)
        cred.save()

        # Database raw field must NOT contain plain token
        cred_from_db = GoogleAdminCredential.objects.get(id=cred.id)
        self.assertNotEqual(cred_from_db.encrypted_refresh_token, raw_token)
        self.assertEqual(cred_from_db.get_refresh_token(), raw_token)
        self.assertFalse(cred_from_db.is_expired)

    # 2. Access Control Tests
    def test_anonymous_and_non_superuser_forbidden_from_oauth_routes(self):
        """Only superusers can access Google connect, callback, and disconnect endpoints."""
        endpoints = [
            '/super-admin/google/connect/',
            '/super-admin/google/callback/?code=test&state=xyz',
        ]
        # Anonymous -> Redirect to login
        for url in endpoints:
            res = self.client.get(url)
            self.assertEqual(res.status_code, 302)
            self.assertIn('/login/', res.url)

        # Regular user -> 403 Forbidden
        self.client.login(username='regular_clerk', password='ClerkPassword123!')
        for url in endpoints:
            res = self.client.get(url)
            self.assertEqual(res.status_code, 403)

        res_post = self.client.post('/super-admin/google/disconnect/')
        self.assertEqual(res_post.status_code, 403)

    # 3. Connect & Callback Flow Tests
    @patch('apps.core.google_auth.create_oauth_flow')
    def test_superuser_connect_initiates_oauth_flow(self, mock_create_flow):
        """Superuser gets redirected to Google authorization URL with state saved in session."""
        mock_flow = MagicMock()
        mock_flow.authorization_url.return_value = ('https://accounts.google.com/o/oauth2/auth?state=state123', 'state123')
        mock_create_flow.return_value = mock_flow

        self.client.login(username='oauth_admin', password='AdminPassword123!')
        response = self.client.get('/super-admin/google/connect/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('accounts.google.com', response.url)
        self.assertEqual(self.client.session.get('google_oauth_state'), 'state123')

    @patch('apps.core.google_auth.create_oauth_flow')
    def test_oauth_callback_exchanges_code_and_stores_encrypted_token(self, mock_create_flow):
        """OAuth callback successfully exchanges code, encrypts refresh token, and logs audit."""
        mock_flow = MagicMock()
        mock_creds = MagicMock()
        mock_creds.token = "new_access_token_xyz"
        mock_creds.refresh_token = "new_refresh_token_abc"
        mock_creds.expiry = timezone.now() + timedelta(hours=1)
        mock_creds.scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive.file']
        mock_flow.credentials = mock_creds
        mock_create_flow.return_value = mock_flow

        self.client.login(username='oauth_admin', password='AdminPassword123!')
        # Set matching state in session
        session = self.client.session
        session['google_oauth_state'] = 'valid_state_abc'
        session.save()

        with patch('googleapiclient.discovery.build') as mock_build:
            mock_userinfo = MagicMock()
            mock_userinfo.userinfo().get().execute.return_value = {'email': 'founder@floweragency.com'}
            mock_build.return_value = mock_userinfo

            response = self.client.get('/super-admin/google/callback/?code=auth_code_123&state=valid_state_abc')
            self.assertEqual(response.status_code, 302)
            self.assertIn('google_connected=1', response.url)

        # Verify database record
        cred = GoogleAdminCredential.objects.filter(id=1).first()
        self.assertIsNotNone(cred)
        self.assertEqual(cred.admin_email, 'founder@floweragency.com')
        self.assertEqual(cred.get_refresh_token(), 'new_refresh_token_abc')
        self.assertTrue(cred.is_valid)

        # Verify audit log created
        log = GoogleProvisioningAuditLog.objects.filter(action='OAUTH_CONNECTED').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'SUCCESS')

    def test_oauth_callback_state_mismatch_rejected(self):
        """CSRF/State parameter mismatch in OAuth callback redirects with error."""
        self.client.login(username='oauth_admin', password='AdminPassword123!')
        session = self.client.session
        session['google_oauth_state'] = 'correct_state'
        session.save()

        response = self.client.get('/super-admin/google/callback/?code=code_123&state=tampered_state')
        self.assertEqual(response.status_code, 302)
        self.assertIn('google_error=Invalid', response.url)

    # 4. Token Auto-Refresh & Revocation Handling Tests
    @patch('google.oauth2.credentials.Credentials.refresh')
    def test_get_admin_credentials_auto_refreshes_expired_token(self, mock_refresh):
        """Expired access token triggers auto-refresh using the stored encrypted refresh token."""
        # Create credential with expired token
        cred = GoogleAdminCredential.objects.create(
            id=1,
            admin_user=self.superuser,
            admin_email='admin@avt.com',
            access_token='old_expired_token',
            token_expiry=timezone.now() - timedelta(minutes=10),
            is_valid=True
        )
        cred.set_refresh_token('valid_refresh_token_123')
        cred.save()

        def side_effect(request):
            pass  # simulate successful refresh
        mock_refresh.side_effect = side_effect

        credentials = get_admin_credentials()
        self.assertIsNotNone(credentials)
        cred.refresh_from_db()
        self.assertTrue(cred.is_valid)

    @patch('google.oauth2.credentials.Credentials.refresh')
    def test_get_admin_credentials_handles_revocation(self, mock_refresh):
        """Revoked refresh token flags is_valid=False and records error for admin dashboard."""
        cred = GoogleAdminCredential.objects.create(
            id=1,
            admin_user=self.superuser,
            admin_email='admin@avt.com',
            access_token='expired_token',
            token_expiry=timezone.now() - timedelta(minutes=10),
            is_valid=True
        )
        cred.set_refresh_token('revoked_refresh_token')
        cred.save()

        mock_refresh.side_effect = Exception("invalid_grant: Token has been expired or revoked.")

        credentials = get_admin_credentials()
        self.assertIsNone(credentials)

        cred.refresh_from_db()
        self.assertFalse(cred.is_valid)
        self.assertIn("invalid_grant", cred.last_error)

        # Audit log entry for failure
        log = GoogleProvisioningAuditLog.objects.filter(action='OAUTH_REFRESH_FAILED').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'FAILURE')

    def test_superuser_disconnect_flow(self):
        """Superuser disconnects Google account via POST request."""
        GoogleAdminCredential.objects.create(
            id=1,
            admin_user=self.superuser,
            admin_email='admin@avt.com',
            access_token='token123'
        )
        self.client.login(username='oauth_admin', password='AdminPassword123!')
        res = self.client.post('/super-admin/google/disconnect/')
        self.assertEqual(res.status_code, 302)
        self.assertIn('google_disconnected=1', res.url)
        self.assertEqual(GoogleAdminCredential.objects.count(), 0)
