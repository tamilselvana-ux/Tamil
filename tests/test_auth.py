import json
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from apps.shops.models import Shop
from apps.accounts.models import ShopProfile
from apps.parties.models import Supplier
from apps.flowers.models import Flower
from apps.core.security import reset_login_attempts


class AuthAndPermissionsTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        # Superuser
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@avt.com',
            password='AdminPassword123!'
        )
        # Approved Shop & Owner
        self.shop1 = Shop.objects.create(
            code='shop-avt-001',
            name='AVT Flower Merchants',
            market_address='FB-78 Koyambedu',
            phone='9360188707'
        )
        self.user1 = User.objects.create_user(
            username='avt_owner',
            email='avt@market.com',
            password='OwnerPassword123!'
        )
        self.profile1 = ShopProfile.objects.create(
            user=self.user1,
            shop=self.shop1,
            status=ShopProfile.STATUS_APPROVED,
            phone='9360188707'
        )
        # Pending Shop & Owner
        self.shop_pending = Shop.objects.create(
            code='shop-pending-999',
            name='New Trader Flower Shop',
            market_address='Koyambedu Gate 2'
        )
        self.user_pending = User.objects.create_user(
            username='pending_user',
            email='pending@market.com',
            password='PendingPassword123!'
        )
        self.profile_pending = ShopProfile.objects.create(
            user=self.user_pending,
            shop=self.shop_pending,
            status=ShopProfile.STATUS_PENDING
        )

    def test_anonymous_user_redirected_with_next_param(self):
        """Anonymous users must be redirected to /login/?next=... on protected views."""
        protected_urls = [
            '/',
            '/terminal/',
            '/parties/',
            '/flowers/',
            '/invoice/',
            '/super-admin/',
        ]
        for url in protected_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, f"URL {url} did not redirect anonymous user")
            self.assertIn('/login/', response.url)
            self.assertIn('next=', response.url)

    def test_anonymous_user_denied_on_protected_apis(self):
        """Unauthenticated API calls must return 401 or redirect to login, never 200, and data remains unchanged."""
        sup_count_before = Supplier.objects.count()
        fl_count_before = Flower.objects.count()

        api_urls = [
            ('/api/purchases/list/', 'GET', {}),
            ('/api/purchases/batch-save/', 'POST', {'lots': []}),
            ('/api/postings/create/', 'POST', {'supplier_code': 'HMS DPS'}),
            ('/api/parties/autocomplete/', 'GET', {}),
            ('/api/parties/save/', 'POST', {'code': 'HACK', 'name': 'Hacker'}),
            ('/api/flowers/list/', 'GET', {}),
            ('/api/flowers/save/', 'POST', {'code': 'HACK', 'name': 'Hacker Flower'}),
            ('/api/super-admin/update-status/', 'POST', {'shop_id': 'shop-pending-999', 'status': 'APPROVED'}),
        ]
        for url, method, payload in api_urls:
            if method == 'GET':
                resp = self.client.get(url)
            else:
                resp = self.client.post(url, data=json.dumps(payload), content_type='application/json')
            self.assertIn(
                resp.status_code,
                [302, 401, 403],
                f"API {url} allowed unauthenticated access (status {resp.status_code})"
            )

        # Assert no data was inserted
        self.assertEqual(Supplier.objects.count(), sup_count_before)
        self.assertEqual(Flower.objects.count(), fl_count_before)

    def test_pending_shop_user_cannot_access_protected_views(self):
        """Users with PENDING shop profile are redirected to /pending/."""
        self.client.force_login(self.user_pending)
        resp = self.client.get('/terminal/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/pending/', resp.url)

    def test_non_superuser_cannot_access_super_admin(self):
        """Regular approved shop users get 403 on super admin portal."""
        self.client.force_login(self.user1)
        resp = self.client.get('/super-admin/')
        self.assertEqual(resp.status_code, 403)

    def test_non_superuser_cannot_approve_shops(self):
        """Regular users cannot invoke the update-status API to approve shops."""
        self.client.force_login(self.user1)
        payload = {'shop_id': self.shop_pending.code, 'status': ShopProfile.STATUS_APPROVED}
        resp = self.client.post(
            '/api/super-admin/update-status/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 403)
        self.profile_pending.refresh_from_db()
        self.assertEqual(self.profile_pending.status, ShopProfile.STATUS_PENDING)

    def test_superuser_can_access_super_admin_and_approve_shop(self):
        """Superusers have full authority to view super-admin and approve shops."""
        self.client.force_login(self.superuser)
        resp = self.client.get('/super-admin/')
        self.assertEqual(resp.status_code, 200)

        payload = {'shop_id': self.shop_pending.code, 'status': ShopProfile.STATUS_APPROVED}
        resp_api = self.client.post(
            '/api/super-admin/update-status/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(resp_api.status_code, 200)
        self.profile_pending.refresh_from_db()
        self.assertTrue(self.profile_pending.is_approved)
        self.assertIn(self.profile_pending.status, [ShopProfile.STATUS_APPROVED, ShopProfile.STATUS_APPROVED_SHEET_PENDING])

    def test_wrong_password_and_unknown_user_give_generic_error(self):
        """Both wrong password and unknown user must return 401 with generic message, keeping entered username."""
        # Unknown user
        resp1 = self.client.post('/login/', {
            'username': 'non_existent_user',
            'password': 'AnyPassword123!'
        })
        self.assertEqual(resp1.status_code, 401)
        self.assertIn('Invalid username or password.', resp1.context['error'])
        self.assertEqual(resp1.context['entered_username'], 'non_existent_user')

        # Existing user with wrong password
        resp2 = self.client.post('/login/', {
            'username': 'avt_owner',
            'password': 'WrongPassword999!'
        })
        self.assertEqual(resp2.status_code, 401)
        self.assertIn('Invalid username or password.', resp2.context['error'])
        self.assertEqual(resp2.context['entered_username'], 'avt_owner')

    def test_email_login_case_insensitive(self):
        """Login works via case-insensitive email as well as username."""
        resp = self.client.post('/login/', {
            'username': 'AVT@MARKET.COM',
            'password': 'OwnerPassword123!'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/terminal/', resp.url)

    def test_open_redirect_attempt_is_safely_ignored(self):
        """Open redirect attempt (?next=https://evil.com) must be ignored and default to terminal."""
        resp = self.client.post('/login/?next=https://evil.com/phish', {
            'username': 'avt_owner',
            'password': 'OwnerPassword123!'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('evil.com', resp.url)
        self.assertEqual(resp.url, '/terminal/')

    def test_safe_same_host_next_redirect(self):
        """Valid same-host ?next=/suppliers/ is honored on successful login."""
        resp = self.client.post('/login/?next=/suppliers/', {
            'username': 'avt_owner',
            'password': 'OwnerPassword123!'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/suppliers/')

    def test_login_lockout_after_repeated_failures(self):
        """5 consecutive failed attempts must trigger 15-minute lockout with HTTP 429."""
        ip = "127.0.0.1"
        reset_login_attempts(ip)

        for i in range(5):
            resp = self.client.post('/login/', {
                'username': 'avt_owner',
                'password': 'BadPassword!'
            })
            self.assertEqual(resp.status_code, 401)

        # 6th attempt must be locked out with HTTP 429
        resp_lockout = self.client.post('/login/', {
            'username': 'avt_owner',
            'password': 'OwnerPassword123!'
        })
        self.assertEqual(resp_lockout.status_code, 429)
        self.assertIn('Too many failed login attempts', resp_lockout.context['error'])
        reset_login_attempts(ip)

    def test_password_reset_views_render_200(self):
        """Password reset views must all render with 200 OK."""
        res_reset = self.client.get('/password-reset/')
        self.assertEqual(res_reset.status_code, 200)

        res_done = self.client.get('/password-reset/done/')
        self.assertEqual(res_done.status_code, 200)

        res_complete = self.client.get('/reset/done/')
        self.assertEqual(res_complete.status_code, 200)
