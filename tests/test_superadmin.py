import json
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from apps.shops.models import Shop
from apps.accounts.models import ShopProfile
from apps.parties.models import Supplier
from apps.flowers.models import Flower
from apps.purchases.models import PurchaseLot, Posting


class SuperAdminCommandCenterTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        # Superuser
        self.superuser = User.objects.create_superuser(
            username='superboss',
            email='super@boss.com',
            password='SuperPassword123!'
        )
        # Approved Shop 1
        self.shop1 = Shop.objects.create(
            code='shop-1',
            name='Alpha Flora',
            market_address='Koyambedu Stall 1'
        )
        self.user1 = User.objects.create_user(
            username='alpha_owner',
            email='alpha@flora.com',
            password='AlphaPassword123!'
        )
        self.profile1 = ShopProfile.objects.create(
            user=self.user1,
            shop=self.shop1,
            status=ShopProfile.STATUS_APPROVED
        )
        # Create some lot data for turnover test
        self.flower = Flower.objects.create(shop=self.shop1, name='Rose', code='RS', default_rate=100)
        self.supplier = Supplier.objects.create(shop=self.shop1, name='Kannan Farmer', code='SUP-K')
        PurchaseLot.objects.create(
            shop=self.shop1,
            supplier=self.supplier,
            party_code=self.supplier.code,
            party_name=self.supplier.name,
            flower=self.flower,
            flower_code=self.flower.code,
            flower_name=self.flower.name,
            purchase_date='2026-11-05',
            weight=Decimal('50.000'),
            rate=Decimal('100.00'),
            gross_value=Decimal('5000.00'),
            boxes=2,
            lug_rate=Decimal('10.00'),
            luggage_amt=Decimal('20.00'),
            coolie_rate=Decimal('15.00'),
            coolie_amt=Decimal('30.00'),
            net_lot_value=Decimal('4950.00')
        )
        # Pending Shop 2
        self.shop2 = Shop.objects.create(
            code='shop-2',
            name='Beta Blooms',
            market_address='Koyambedu Stall 2'
        )
        self.user2 = User.objects.create_user(
            username='beta_applicant',
            email='beta@blooms.com',
            password='BetaPassword123!'
        )
        self.profile2 = ShopProfile.objects.create(
            user=self.user2,
            shop=self.shop2,
            status=ShopProfile.STATUS_PENDING
        )

    def test_anonymous_access_denied(self):
        """Anonymous access to /super-admin/ redirects to login; API returns 401."""
        res_view = self.client.get('/super-admin/')
        self.assertEqual(res_view.status_code, 302)
        self.assertIn('/login/', res_view.url)

        res_api = self.client.post(
            '/api/super-admin/update-status/',
            data=json.dumps({'profile_id': self.profile2.id, 'status': 'APPROVED'}),
            content_type='application/json'
        )
        self.assertEqual(res_api.status_code, 401)

    def test_regular_merchant_forbidden(self):
        """Non-superuser access returns 403 Forbidden on both view and API."""
        self.client.login(username='alpha_owner', password='AlphaPassword123!')
        res_view = self.client.get('/super-admin/')
        self.assertEqual(res_view.status_code, 403)

        res_api = self.client.post(
            '/api/super-admin/update-status/',
            data=json.dumps({'profile_id': self.profile2.id, 'status': 'APPROVED'}),
            content_type='application/json'
        )
        self.assertEqual(res_api.status_code, 403)

    def test_superuser_can_view_command_center(self):
        """Superuser gets 200 and views platform statistics and pending shops."""
        self.client.login(username='superboss', password='SuperPassword123!')
        response = self.client.get('/super-admin/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Command Center')
        self.assertContains(response, 'Beta Blooms')
        self.assertContains(response, 'Alpha Flora')
        # Check context statistics
        context = response.context
        self.assertEqual(context['total_shops'], 2)
        self.assertEqual(context['pending_count'], 1)
        self.assertEqual(context['active_count'], 1)
        self.assertEqual(context['total_lots'], 1)
        self.assertEqual(context['total_turnover'], '5,000.00')

    def test_superuser_can_approve_pending_shop(self):
        """Superuser approves a pending merchant registration via AJAX API."""
        self.client.login(username='superboss', password='SuperPassword123!')
        response = self.client.post(
            '/api/super-admin/update-status/',
            data=json.dumps({'profile_id': self.profile2.id, 'status': 'APPROVED'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'success')
        self.assertIn(data.get('new_status'), ['APPROVED', 'APPROVED_SHEET_PENDING'])

        self.profile2.refresh_from_db()
        self.assertTrue(self.profile2.is_approved)
        self.assertEqual(self.profile2.approved_by, self.superuser)
        self.assertIsNotNone(self.profile2.approved_at)

    def test_superuser_can_reject_or_deactivate_shop(self):
        """Superuser rejects pending shop or deactivates active shop."""
        self.client.login(username='superboss', password='SuperPassword123!')

        # Reject pending
        res_reject = self.client.post(
            '/api/super-admin/update-status/',
            data=json.dumps({'profile_id': self.profile2.id, 'status': 'REJECTED'}),
            content_type='application/json'
        )
        self.assertEqual(res_reject.status_code, 200)
        self.profile2.refresh_from_db()
        self.assertEqual(self.profile2.status, ShopProfile.STATUS_REJECTED)

        # Deactivate active shop
        res_deact = self.client.post(
            '/api/super-admin/update-status/',
            data=json.dumps({'profile_id': self.profile1.id, 'status': 'DEACTIVATED'}),
            content_type='application/json'
        )
        self.assertEqual(res_deact.status_code, 200)
        self.profile1.refresh_from_db()
        self.assertEqual(self.profile1.status, ShopProfile.STATUS_DEACTIVATED)

    def test_invalid_status_rejected(self):
        """Invalid status returns 400 Bad Request."""
        self.client.login(username='superboss', password='SuperPassword123!')
        response = self.client.post(
            '/api/super-admin/update-status/',
            data=json.dumps({'profile_id': self.profile2.id, 'status': 'INVALID_STATUS'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    def test_superuser_without_shopprofile_can_access_terminal_and_views(self):
        """Superuser without a direct shopprofile can access terminal and masters without crashing."""
        self.client.login(username='superboss', password='SuperPassword123!')
        res_terminal = self.client.get('/')
        self.assertEqual(res_terminal.status_code, 200)
        self.assertContains(res_terminal, 'Alpha Flora')

        res_parties = self.client.get('/parties/')
        self.assertEqual(res_parties.status_code, 200)

        res_flowers = self.client.get('/flowers/')
        self.assertEqual(res_flowers.status_code, 200)

