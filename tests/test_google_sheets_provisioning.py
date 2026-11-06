import json
from unittest.mock import patch, MagicMock
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from apps.shops.models import Shop
from apps.accounts.models import ShopProfile, GoogleAdminCredential, GoogleProvisioningAuditLog
from apps.core.google_sheets_provisioner import (
    approve_shop_and_provision_sheet,
    sanitize_sheet_value,
    get_or_create_drive_folder,
    create_merchant_spreadsheet
)


class GoogleSheetsProvisioningTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username='prov_admin',
            email='admin@floweragency.com',
            password='AdminPassword123!'
        )
        self.regular_user = User.objects.create_user(
            username='prov_clerk',
            email='clerk@floweragency.com',
            password='ClerkPassword123!'
        )

        # Create active Google OAuth credentials in DB
        self.cred = GoogleAdminCredential.objects.create(
            id=1,
            admin_user=self.superuser,
            admin_email='admin@floweragency.com',
            access_token='mock_access_token_123',
            is_valid=True
        )
        self.cred.set_refresh_token('mock_refresh_token_abc')
        self.cred.save()

        # Pending Merchant Shop
        self.shop = Shop.objects.create(
            code='shop-prov-001',
            name='Kavitha Rose Agency',
            market_address='Koyambedu Gate 4',
            phone='9876543210',
            email='kavitha@agency.com'
        )
        self.merchant_user = User.objects.create_user(
            username='kavitha_owner',
            email='kavitha@agency.com',
            password='KavithaPassword123!'
        )
        self.profile = ShopProfile.objects.create(
            user=self.merchant_user,
            shop=self.shop,
            status=ShopProfile.STATUS_PENDING,
            phone='9876543210'
        )

    # 1. Formula Injection Sanitizer Tests
    def test_formula_injection_defense(self):
        """Values starting with =, +, -, @, or whitespace control characters must be prefixed with single quote."""
        self.assertEqual(sanitize_sheet_value("=SUM(A1:A10)"), "'=SUM(A1:A10)")
        self.assertEqual(sanitize_sheet_value("+cmd|'/C calc'!A0"), "'+cmd|'/C calc'!A0")
        self.assertEqual(sanitize_sheet_value("-100"), "'-100")
        self.assertEqual(sanitize_sheet_value("@HYPERLINK('evil.com')"), "'@HYPERLINK('evil.com')")
        self.assertEqual(sanitize_sheet_value("Normal Agency Name"), "Normal Agency Name")
        self.assertEqual(sanitize_sheet_value(""), "")
        self.assertEqual(sanitize_sheet_value(None), "")

    # 2. Automated Provisioning Success & Idempotency
    @patch('apps.core.google_sheets_provisioner.build')
    @patch('apps.core.google_sheets_provisioner.get_admin_credentials')
    def test_approve_shop_provisions_google_sheet_successfully(self, mock_get_creds, mock_build):
        """Super Admin approves shop: creates Drive folder, creates sheet, moves it, and sets status APPROVED."""
        mock_creds = MagicMock()
        mock_get_creds.return_value = mock_creds

        mock_drive = MagicMock()
        mock_sheets = MagicMock()

        def build_side_effect(serviceName, version, credentials=None):
            if serviceName == 'drive':
                return mock_drive
            elif serviceName == 'sheets':
                return mock_sheets
            return MagicMock()

        mock_build.side_effect = build_side_effect

        # Mock Drive folder search: not found -> created
        mock_drive.files().list().execute.return_value = {'files': []}
        mock_drive.files().create().execute.return_value = {'id': 'folder_abc_123'}

        # Mock Sheet create
        mock_sheets.spreadsheets().create().execute.return_value = {
            'spreadsheetId': 'sheet_xyz_789',
            'spreadsheetUrl': 'https://docs.google.com/spreadsheets/d/sheet_xyz_789/edit'
        }

        # Mock Drive file parents & update
        mock_drive.files().get().execute.return_value = {'parents': ['root']}
        mock_drive.files().update().execute.return_value = {'id': 'sheet_xyz_789'}
        mock_sheets.spreadsheets().values().batchUpdate().execute.return_value = {}

        # Execute approval
        success, profile, msg = approve_shop_and_provision_sheet(self.profile.id, self.superuser)

        self.assertTrue(success)
        self.assertEqual(profile.status, ShopProfile.STATUS_APPROVED)
        self.assertEqual(profile.google_sheet_id, 'sheet_xyz_789')
        self.assertEqual(profile.google_sheet_url, 'https://docs.google.com/spreadsheets/d/sheet_xyz_789/edit')
        self.assertEqual(profile.google_folder_id, 'folder_abc_123')

        # Check Audit Log
        log = GoogleProvisioningAuditLog.objects.filter(shop=self.shop, action='SHEET_PROVISIONED').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'SUCCESS')
        self.assertEqual(log.sheet_id, 'sheet_xyz_789')

        # Idempotency check: Calling approve again must NOT call spreadsheets().create() again
        mock_sheets.spreadsheets().create.reset_mock()
        success2, profile2, msg2 = approve_shop_and_provision_sheet(self.profile.id, self.superuser)
        self.assertTrue(success2)
        mock_sheets.spreadsheets().create.assert_not_called()
        self.assertIn("already approved", msg2)

    # 3. Missing Google OAuth Fallback Test
    @patch('apps.core.google_sheets_provisioner.get_admin_credentials')
    def test_missing_google_oauth_sets_sheet_pending_without_crashing(self, mock_get_creds):
        """When admin OAuth is not connected, shop approval does not crash; status becomes APPROVED_SHEET_PENDING."""
        mock_get_creds.return_value = None  # No valid credentials

        success, profile, msg = approve_shop_and_provision_sheet(self.profile.id, self.superuser)

        self.assertFalse(success)
        self.assertEqual(profile.status, ShopProfile.STATUS_APPROVED_SHEET_PENDING)
        self.assertIn("OAuth connection is not active", profile.sheet_provision_error)

        log = GoogleProvisioningAuditLog.objects.filter(shop=self.shop, action='PROVISION_FAILED_AUTH').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'PENDING_RETRY')

    # 4. Google API Error Fallback & Retry via AJAX
    @patch('apps.core.google_sheets_provisioner.build')
    @patch('apps.core.google_sheets_provisioner.get_admin_credentials')
    def test_google_api_failure_and_retry_workflow(self, mock_get_creds, mock_build):
        """Google API error gracefully sets APPROVED_SHEET_PENDING, allowing retry via update_shop_status_api."""
        mock_creds = MagicMock()
        mock_get_creds.return_value = mock_creds

        # First attempt: Drive throws 503 Service Unavailable
        mock_drive = MagicMock()
        mock_drive.files().list().execute.side_effect = Exception("503 Service Unavailable from Google Drive")

        def build_fail(serviceName, version, credentials=None):
            return mock_drive
        mock_build.side_effect = build_fail

        success, profile, msg = approve_shop_and_provision_sheet(self.profile.id, self.superuser)
        self.assertFalse(success)
        self.assertEqual(profile.status, ShopProfile.STATUS_APPROVED_SHEET_PENDING)
        self.assertIn("503 Service Unavailable", profile.sheet_provision_error)

        # Second attempt: Admin triggers retry via AJAX API
        mock_sheets = MagicMock()
        mock_drive.files().list().execute.side_effect = None
        mock_drive.files().list().execute.return_value = {'files': [{'id': 'folder_recovered_456'}]}
        mock_sheets.spreadsheets().create().execute.return_value = {
            'spreadsheetId': 'sheet_recovered_123',
            'spreadsheetUrl': 'https://docs.google.com/spreadsheets/d/sheet_recovered_123/edit'
        }
        mock_drive.files().get().execute.return_value = {'parents': ['root']}
        mock_drive.files().update().execute.return_value = {'id': 'sheet_recovered_123'}

        def build_success(serviceName, version, credentials=None):
            if serviceName == 'drive':
                return mock_drive
            return mock_sheets
        mock_build.side_effect = build_success

        self.client.login(username='prov_admin', password='AdminPassword123!')
        res_retry = self.client.post(
            '/api/super-admin/update-status/',
            data=json.dumps({'profile_id': self.profile.id, 'status': 'RETRY_PROVISION'}),
            content_type='application/json'
        )
        self.assertEqual(res_retry.status_code, 200)
        data = res_retry.json()
        self.assertTrue(data.get('provision_success'))
        self.assertEqual(data.get('new_status'), ShopProfile.STATUS_APPROVED)
        self.assertEqual(data.get('sheet_id'), 'sheet_recovered_123')

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.status, ShopProfile.STATUS_APPROVED)
        self.assertEqual(self.profile.google_sheet_id, 'sheet_recovered_123')
        self.assertEqual(self.profile.sheet_provision_error, '')

    # 5. Non-Superuser Access Blocked
    def test_non_superuser_cannot_approve_or_provision(self):
        """Non-superusers cannot trigger sheet provisioning."""
        success, profile, msg = approve_shop_and_provision_sheet(self.profile.id, self.regular_user)
        self.assertFalse(success)
        self.assertIn("Permission denied", msg)
