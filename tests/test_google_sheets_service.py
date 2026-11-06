from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth.models import User
from googleapiclient.errors import HttpError
from httplib2 import Response

from apps.shops.models import Shop
from apps.accounts.models import ShopProfile, GoogleAdminCredential, GoogleProvisioningAuditLog
from apps.core.google_sheets_service import (
    UserSheetService,
    SheetNotProvisionedError,
    GoogleSheetsAPIError,
    execute_with_retry
)


class UserSheetServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='merchant_serv',
            email='merchant_serv@avtflowers.com',
            password='Password@123'
        )
        self.shop = Shop.objects.create(
            name='Service Test Shop',
            code='STS-01',
            phone='9876543210'
        )
        self.profile = ShopProfile.objects.create(
            user=self.user,
            shop=self.shop,
            status=ShopProfile.STATUS_APPROVED,
            google_sheet_id='sheet_isolated_12345',
            google_sheet_url='https://docs.google.com/spreadsheets/d/sheet_isolated_12345/edit'
        )

    def test_initialization_with_valid_sheet_id(self):
        service = UserSheetService(self.shop)
        self.assertEqual(service.sheet_id, 'sheet_isolated_12345')
        self.assertEqual(service.shop, self.shop)

        # Also works when initialized with ShopProfile
        service_from_profile = UserSheetService(self.profile)
        self.assertEqual(service_from_profile.sheet_id, 'sheet_isolated_12345')

        # Also works via for_user factory
        service_from_user = UserSheetService.for_user(self.user)
        self.assertEqual(service_from_user.sheet_id, 'sheet_isolated_12345')

    def test_initialization_raises_error_if_sheet_not_provisioned(self):
        unprovisioned_shop = Shop.objects.create(
            name='Unprovisioned Shop',
            code='UNP-01',
            phone='9876543211'
        )
        ShopProfile.objects.create(
            user=User.objects.create_user('unp_user', 'unp@test.com', 'Pass@123'),
            shop=unprovisioned_shop,
            status=ShopProfile.STATUS_PENDING,
            google_sheet_id=''
        )

        with self.assertRaises(SheetNotProvisionedError):
            UserSheetService(unprovisioned_shop)

    def test_sanitize_rows_formula_injection(self):
        malicious_rows = [
            ['Normal Name', '=cmd|"/c calc"!A0', '+100', '-50.25'],
            ['@attacker.com', '\tmalicious_tab', 'Safe 123', '=SUM(A1:B10)']
        ]

        sanitized = UserSheetService.sanitize_rows(malicious_rows)

        self.assertEqual(sanitized[0][0], 'Normal Name')
        self.assertEqual(sanitized[0][1], '\'=cmd|"/c calc"!A0')
        self.assertEqual(sanitized[0][2], '\'+100')
        self.assertEqual(sanitized[0][3], '\'-50.25')

        self.assertEqual(sanitized[1][0], '\'@attacker.com')
        self.assertEqual(sanitized[1][1], '\'\tmalicious_tab')
        self.assertEqual(sanitized[1][2], 'Safe 123')
        self.assertEqual(sanitized[1][3], '\'=SUM(A1:B10)')

    @patch('apps.core.google_sheets_service.get_admin_credentials')
    @patch('apps.core.google_sheets_service.build')
    def test_read_rows(self, mock_build, mock_get_creds):
        mock_get_creds.return_value = MagicMock()
        mock_sheets_service = MagicMock()
        mock_build.return_value = mock_sheets_service

        mock_values_resource = mock_sheets_service.spreadsheets().values()
        mock_get = mock_values_resource.get.return_value
        mock_get.execute.return_value = {
            'values': [
                ['Supplier Code', 'Name', 'Phone'],
                ['SUP-01', 'Madurai Maligai', '9841011223']
            ]
        }

        service = UserSheetService(self.shop)
        rows = service.read_rows('Suppliers', 'A1:C2')

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], 'Supplier Code')
        mock_values_resource.get.assert_called_with(
            spreadsheetId='sheet_isolated_12345',
            range="'Suppliers'!A1:C2"
        )

    @patch('apps.core.google_sheets_service.get_admin_credentials')
    @patch('apps.core.google_sheets_service.build')
    def test_append_rows_sanitizes_data(self, mock_build, mock_get_creds):
        mock_get_creds.return_value = MagicMock()
        mock_sheets_service = MagicMock()
        mock_build.return_value = mock_sheets_service

        mock_append = mock_sheets_service.spreadsheets().values().append.return_value
        mock_append.execute.return_value = {'updates': {'updatedRows': 1}}

        service = UserSheetService(self.shop)
        raw_rows = [['SUP-02', '=HYPERLINK("http://evil.com")', '+999']]
        result = service.append_rows('Suppliers', raw_rows)

        self.assertEqual(result.get('updates', {}).get('updatedRows'), 1)
        mock_sheets_service.spreadsheets().values().append.assert_called_with(
            spreadsheetId='sheet_isolated_12345',
            range="'Suppliers'!A1",
            valueInputOption='USER_ENTERED',
            insertDataOption='INSERT_ROWS',
            body={'values': [['SUP-02', '\'=HYPERLINK("http://evil.com")', '\'+999']]}
        )

    @patch('apps.core.google_sheets_service.get_admin_credentials')
    @patch('apps.core.google_sheets_service.build')
    def test_batch_update_rows(self, mock_build, mock_get_creds):
        mock_get_creds.return_value = MagicMock()
        mock_sheets_service = MagicMock()
        mock_build.return_value = mock_sheets_service

        mock_batch = mock_sheets_service.spreadsheets().values().batchUpdate.return_value
        mock_batch.execute.return_value = {'totalUpdatedCells': 2}

        service = UserSheetService(self.shop)
        updates = [
            {'range': 'A2:B2', 'values': [['Malli', '=100*2']]}
        ]
        result = service.batch_update_rows('Flowers', updates)

        self.assertEqual(result.get('totalUpdatedCells'), 2)
        mock_sheets_service.spreadsheets().values().batchUpdate.assert_called_with(
            spreadsheetId='sheet_isolated_12345',
            body={
                'valueInputOption': 'USER_ENTERED',
                'data': [
                    {
                        'range': "'Flowers'!A2:B2",
                        'values': [['Malli', '\'=100*2']]
                    }
                ]
            }
        )

    @patch('apps.core.google_sheets_service.get_admin_credentials')
    @patch('apps.core.google_sheets_service.build')
    def test_get_tab_records(self, mock_build, mock_get_creds):
        mock_get_creds.return_value = MagicMock()
        mock_sheets_service = MagicMock()
        mock_build.return_value = mock_sheets_service

        mock_sheets_service.spreadsheets().values().get.return_value.execute.return_value = {
            'values': [
                ['Code', 'Name', 'Phone'],
                ['SUP-A', 'Malli Trader', '9800011111'],
                ['SUP-B', 'Rose Dealer', '9800022222']
            ]
        }

        service = UserSheetService(self.shop)
        records = service.get_tab_records('Suppliers')

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]['Code'], 'SUP-A')
        self.assertEqual(records[0]['Name'], 'Malli Trader')
        self.assertEqual(records[1]['Code'], 'SUP-B')

    @patch('time.sleep', return_value=None)
    def test_execute_with_retry_on_429_then_success(self, mock_sleep):
        mock_func = MagicMock()
        resp_429 = Response({'status': '429'})
        error_429 = HttpError(resp_429, b'Rate Limit Exceeded')

        # First call fails with 429, second succeeds
        mock_func.side_effect = [error_429, {'status': 'success'}]

        result = execute_with_retry(mock_func, max_retries=2, initial_delay=0.01)
        self.assertEqual(result, {'status': 'success'})
        self.assertEqual(mock_func.call_count, 2)
        mock_sleep.assert_called_once()

    @patch('time.sleep', return_value=None)
    def test_execute_with_retry_exhausted_raises_api_error(self, mock_sleep):
        mock_func = MagicMock()
        resp_503 = Response({'status': '503'})
        error_503 = HttpError(resp_503, b'Backend Error')
        mock_func.side_effect = error_503

        with self.assertRaises(GoogleSheetsAPIError):
            execute_with_retry(mock_func, max_retries=2, initial_delay=0.01)

        self.assertEqual(mock_func.call_count, 3)  # Initial + 2 retries
