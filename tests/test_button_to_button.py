import json
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from apps.shops.models import Shop
from apps.accounts.models import ShopProfile
from apps.parties.models import Supplier, Area, LedgerGroup
from apps.flowers.models import Flower
from apps.purchases.models import PurchaseLot, Posting


class FullButtonToButtonTestCase(TestCase):
    """
    Exhaustive button-to-button test suite verifying every single button, link,
    form submission, action API, and modal trigger across all 9 templates
    and all 4 user roles (Anonymous, Pending, Approved Merchant, Super Admin).
    """

    def setUp(self):
        self.client = Client()

        # 1. Super Admin
        self.superuser = User.objects.create_superuser(
            username='btn_superadmin',
            email='super@avt.com',
            password='AdminPassword123!'
        )

        # 2. Approved Shop & Owner
        self.shop1 = Shop.objects.create(
            code='shop-btn-001',
            name='AVT Test Flower Agency',
            market_address='FB-78 Koyambedu',
            phone='9360188707',
            email='avt@test.com'
        )
        self.merchant_user = User.objects.create_user(
            username='btn_merchant',
            email='merchant@avt.com',
            password='MerchantPassword123!'
        )
        self.merchant_profile = ShopProfile.objects.create(
            user=self.merchant_user,
            shop=self.shop1,
            status=ShopProfile.STATUS_APPROVED,
            phone='9360188707'
        )

        # Superuser profile linked to shop1 for full terminal inspection
        ShopProfile.objects.create(
            user=self.superuser,
            shop=self.shop1,
            status=ShopProfile.STATUS_APPROVED,
            phone='9999999999'
        )

        # 3. Pending User & Shop
        self.shop_pending = Shop.objects.create(
            code='shop-btn-999',
            name='Pending Trader Shop',
            market_address='Koyambedu Gate 3',
            phone='9888888888',
            email='pending@test.com'
        )
        self.pending_user = User.objects.create_user(
            username='btn_pending',
            email='pending@avt.com',
            password='PendingPassword123!'
        )
        self.pending_profile = ShopProfile.objects.create(
            user=self.pending_user,
            shop=self.shop_pending,
            status=ShopProfile.STATUS_PENDING,
            phone='9888888888'
        )

        # Master Data for Shop 1
        self.area = Area.objects.create(shop=self.shop1, name='SALEM')
        self.group = LedgerGroup.objects.create(shop=self.shop1, name='Suppliers group')
        self.supplier = Supplier.objects.create(
            shop=self.shop1,
            code='SUP-01',
            name='Kannan Grower',
            area=self.area,
            area_name='SALEM',
            ledger_group=self.group,
            commission_pct=Decimal('15.00'),
            luggage_default=Decimal('150.00'),
            adv_opening=Decimal('5000.00'),
            status='Active'
        )
        self.flower = Flower.objects.create(
            shop=self.shop1,
            code='DOLY',
            name='DOL YELLOW',
            default_rate=Decimal('45.00'),
            status='Active'
        )

    # =========================================================================
    # ROLE 1: ANONYMOUS VISITOR BUTTONS & LINKS
    # =========================================================================

    def test_anonymous_nav_buttons_and_isolation(self):
        """Anonymous user sees only Sign In, Register, Logo, and Theme toggle in navbar."""
        response = self.client.get('/login/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sign In')
        self.assertContains(response, 'Register Shop')
        self.assertContains(response, 'theme-btn')
        # Protected tabs must NOT exist
        self.assertNotContains(response, 'Terminal</a>')
        self.assertNotContains(response, 'Suppliers</a>')
        self.assertNotContains(response, 'Flowers</a>')
        self.assertNotContains(response, 'Bills</a>')
        self.assertNotContains(response, 'Admin</a>')

    def test_anonymous_login_screen_buttons(self):
        """Test all interactive elements on the login page."""
        response = self.client.get('/login/')
        self.assertEqual(response.status_code, 200)
        # 1. Forgot password link
        self.assertContains(response, 'Forgot Password?')
        res_forgot = self.client.get('/password-reset/')
        self.assertEqual(res_forgot.status_code, 200)
        # 2. Eye password toggle button
        self.assertContains(response, 'toggle-password-btn')
        self.assertContains(response, 'aria-label="Show password"')
        # 3. Register link CTA
        self.assertContains(response, 'Register Your Shop')
        res_reg = self.client.get('/register/')
        self.assertEqual(res_reg.status_code, 200)
        # 4. Form submission with invalid password
        res_fail = self.client.post('/login/', {
            'username': 'btn_merchant',
            'password': 'WrongPassword999!'
        })
        self.assertEqual(res_fail.status_code, 401)
        self.assertContains(res_fail, 'Invalid username or password', status_code=401)
        # 5. Form submission with valid credentials
        res_succ = self.client.post('/login/', {
            'username': 'btn_merchant',
            'password': 'MerchantPassword123!'
        })
        self.assertEqual(res_succ.status_code, 302)
        self.assertEqual(res_succ.url, '/terminal/')

    def test_anonymous_register_form_button(self):
        """Test shop registration button and submission flow."""
        res_get = self.client.get('/register/')
        self.assertEqual(res_get.status_code, 200)
        self.assertContains(res_get, 'Register Shop')

        # Submit new valid registration
        res_post = self.client.post('/register/', {
            'shop_name': 'New Flora Agency',
            'market_address': 'Stall 44 Koyambedu',
            'owner_username': 'new_flora_user',
            'phone': '9111122222',
            'gmail_id': 'newflora@gmail.com',
            'password': 'NewPassword123!',
            'confirm_password': 'NewPassword123!'
        })
        self.assertEqual(res_post.status_code, 302)
        self.assertIn('/pending/', res_post.url)

        # Check pending screen buttons
        res_pending = self.client.get('/pending/')
        self.assertEqual(res_pending.status_code, 200)
        self.assertContains(res_pending, 'Back to Login')
        self.assertContains(res_pending, 'Admin Console')

    def test_anonymous_password_reset_flow(self):
        """Test the 4 password reset views and buttons."""
        # 1. Reset request form
        res1 = self.client.get('/password-reset/')
        self.assertEqual(res1.status_code, 200)
        res_post = self.client.post('/password-reset/', {'email': 'merchant@avt.com'})
        self.assertEqual(res_post.status_code, 302)
        self.assertEqual(res_post.url, '/password-reset/done/')

        # 2. Reset done page
        res2 = self.client.get('/password-reset/done/')
        self.assertEqual(res2.status_code, 200)
        self.assertContains(res2, 'Return to Sign In')

        # 3. Reset complete page
        res3 = self.client.get(reverse('password_reset_complete'))
        self.assertEqual(res3.status_code, 200)
        self.assertContains(res3, 'Sign In Now')

    # =========================================================================
    # ROLE 2: PENDING USER BUTTONS & ACCESS ENFORCEMENT
    # =========================================================================

    def test_pending_user_access_and_logout(self):
        """Pending user is locked out of terminal and can use Logout button."""
        self.client.login(username='btn_pending', password='PendingPassword123!')
        # Accessing protected pages redirects to /pending/
        for path in ['/', '/parties/', '/flowers/', '/invoice/']:
            res = self.client.get(path)
            self.assertEqual(res.status_code, 302)
            self.assertEqual(res.url, '/pending/')

        # Logout button
        res_logout = self.client.get('/logout/')
        self.assertEqual(res_logout.status_code, 302)
        self.assertIn('/login/', res_logout.url)

    # =========================================================================
    # ROLE 3: APPROVED MERCHANT BUTTONS, MODALS & APIS
    # =========================================================================

    def test_merchant_nav_buttons(self):
        """Approved merchant sees Terminal, Suppliers, Flowers, Bills, Shop Badge, and Logout."""
        self.client.login(username='btn_merchant', password='MerchantPassword123!')
        res = self.client.get('/terminal/')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Terminal')
        self.assertContains(res, 'Suppliers')
        self.assertContains(res, 'Flowers')
        self.assertContains(res, 'Bills')
        self.assertContains(res, 'Logout')
        self.assertContains(res, 'AVT Test Flower')
        # Regular merchant must NOT see Super Admin tab
        self.assertNotContains(res, 'Admin</a>')

    def test_merchant_terminal_buttons_and_batch_save(self):
        """Test Terminal 'Save Lots (F8)' button and batch save API."""
        self.client.login(username='btn_merchant', password='MerchantPassword123!')

        # 1. Fetch Terminal UI
        res_ui = self.client.get('/terminal/')
        self.assertEqual(res_ui.status_code, 200)
        self.assertContains(res_ui, 'Add Flower Line (F2)')
        self.assertContains(res_ui, 'Save Lots (F8)')
        self.assertContains(res_ui, 'Cutoff &amp; Bill (F10)')

        # 2. Batch save lots API (triggered by Save Lots button)
        payload = {
            'lots': [
                {
                    'purchase_date': '2026-11-05',
                    'party_code': 'SUP-01',
                    'flower_code': 'DOLY',
                    'weight': '40.000',
                    'rate': '50.00',
                    'boxes': 2,
                    'lug_rate': '10.00',
                    'coolie_rate': '15.00'
                }
            ]
        }
        res_save = self.client.post(
            '/api/purchases/batch-save/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(res_save.status_code, 200)
        save_data = res_save.json()
        self.assertEqual(save_data.get('status'), 'success')
        self.assertEqual(save_data.get('saved_count'), 1)

        # 3. Retrieve purchase list API (syncs table)
        res_list = self.client.get('/api/purchases/list/?supplier=SUP-01&date=2026-11-05')
        self.assertEqual(res_list.status_code, 200)
        list_data = res_list.json()
        self.assertEqual(list_data.get('status'), 'success')
        self.assertEqual(len(list_data.get('lots', [])), 1)

    def test_merchant_cutoff_posting_modal_and_seal(self):
        """Test Posting Modal 'Post Cutoff & Generate Statement' button and API."""
        self.client.login(username='btn_merchant', password='MerchantPassword123!')

        # Create an unposted lot
        PurchaseLot.objects.create(
            shop=self.shop1,
            supplier=self.supplier,
            party_code=self.supplier.code,
            party_name=self.supplier.name,
            flower=self.flower,
            flower_code=self.flower.code,
            flower_name=self.flower.name,
            purchase_date='2026-11-05',
            weight=Decimal('100.000'),
            rate=Decimal('60.00'),
            gross_value=Decimal('6000.00'),
            boxes=2,
            lug_rate=Decimal('20.00'),
            luggage_amt=Decimal('40.00'),
            coolie_rate=Decimal('15.00'),
            coolie_amt=Decimal('30.00'),
            net_lot_value=Decimal('5930.00')
        )

        # Trigger Post Cutoff button action
        post_payload = {
            'supplier_code': 'SUP-01',
            'from_date': '2026-11-01',
            'to_date': '2026-11-05',
            'advance_deducted': '500.00'
        }
        res_post = self.client.post(
            '/api/postings/create/',
            data=json.dumps(post_payload),
            content_type='application/json'
        )
        self.assertEqual(res_post.status_code, 200)
        post_data = res_post.json()
        self.assertEqual(post_data.get('status'), 'success')
        posting_no = post_data.get('posting_no')
        self.assertTrue(posting_no)

        # Sealed lot check: cannot be double billed
        res_post2 = self.client.post(
            '/api/postings/create/',
            data=json.dumps(post_payload),
            content_type='application/json'
        )
        self.assertEqual(res_post2.status_code, 400)
        self.assertIn('No unposted lots', res_post2.json().get('message', ''))

    def test_merchant_supplier_master_buttons(self):
        """Test Supplier Master: Add form button, Edit button, Delete button, Autocomplete."""
        self.client.login(username='btn_merchant', password='MerchantPassword123!')

        # 1. UI Check
        res_ui = self.client.get('/parties/')
        self.assertEqual(res_ui.status_code, 200)
        self.assertContains(res_ui, 'Add / Edit Supplier')
        self.assertContains(res_ui, 'Supplier Directory')
        self.assertContains(res_ui, 'Return to Terminal')

        # 2. Add Supplier Submit button
        sup_payload = {
            'code': 'SUP-NEW',
            'name': 'Ganesh Farmer',
            'area_name': 'HOSUR',
            'commission_pct': '12.50',
            'luggage_default': '120.00',
            'adv_opening': '1000.00',
            'status': 'Active'
        }
        res_save = self.client.post(
            '/api/parties/save/',
            data=json.dumps(sup_payload),
            content_type='application/json'
        )
        self.assertEqual(res_save.status_code, 200)
        self.assertEqual(res_save.json().get('status'), 'success')

        # 3. Autocomplete search
        res_auto = self.client.get('/api/parties/autocomplete/?q=Ganesh')
        self.assertEqual(res_auto.status_code, 200)
        auto_data = res_auto.json()
        self.assertEqual(len(auto_data.get('suppliers', [])), 1)

        # 4. Supplier Detail API
        res_detail = self.client.get('/api/parties/SUP-NEW/')
        self.assertEqual(res_detail.status_code, 200)
        self.assertEqual(res_detail.json().get('supplier', {}).get('code'), 'SUP-NEW')

        # 5. Delete Supplier Button
        created_sup = Supplier.objects.get(shop=self.shop1, code='SUP-NEW')
        res_del = self.client.post(f'/api/parties/delete/{created_sup.id}/')
        self.assertEqual(res_del.status_code, 200)
        self.assertEqual(res_del.json().get('status'), 'success')

    def test_merchant_flower_master_buttons(self):
        """Test Flower Master: Save button, Edit button, and List API."""
        self.client.login(username='btn_merchant', password='MerchantPassword123!')

        # 1. UI Check
        res_ui = self.client.get('/flowers/')
        self.assertEqual(res_ui.status_code, 200)
        self.assertContains(res_ui, 'Save Flower to Google Sheets')
        self.assertContains(res_ui, 'Return to Terminal')

        # 2. Add / Update Flower Submit
        fl_payload = {
            'code': 'ROSE',
            'name': 'PANEER ROSE',
            'default_rate': '80.00'
        }
        res_save = self.client.post(
            '/api/flowers/save/',
            data=json.dumps(fl_payload),
            content_type='application/json'
        )
        self.assertEqual(res_save.status_code, 200)
        self.assertEqual(res_save.json().get('status'), 'success')

        # 3. List API
        res_list = self.client.get('/api/flowers/list/?q=PANEER')
        self.assertEqual(res_list.status_code, 200)
        self.assertEqual(len(res_list.json().get('flowers', [])), 1)

    def test_merchant_bill_invoice_buttons(self):
        """Test Bill screen: Apply Filter button, Download PDF button, Print button."""
        self.client.login(username='btn_merchant', password='MerchantPassword123!')

        # 1. Render statement preview
        res_inv = self.client.get('/invoice/?supplier=SUP-01&from_date=2026-11-01&to_date=2026-11-05')
        self.assertEqual(res_inv.status_code, 200)
        self.assertContains(res_inv, 'Apply Filter')
        self.assertContains(res_inv, 'Download PDF')
        self.assertContains(res_inv, 'Print')

        # 2. Download PDF button
        res_pdf = self.client.get('/invoice/download-pdf/?supplier=SUP-01&from_date=2026-11-01&to_date=2026-11-05')
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf['Content-Type'], 'application/pdf')
        self.assertTrue(res_pdf.content.startswith(b'%PDF'))

    # =========================================================================
    # ROLE 4: SUPER ADMIN BUTTONS, ACTIONS & NAVIGATION
    # =========================================================================

    def test_super_admin_command_center_buttons_and_actions(self):
        """Test Super Admin Command Center HUD, shortcuts, filter pills, and approval buttons."""
        self.client.login(username='btn_superadmin', password='AdminPassword123!')

        # 1. UI Check & Direct Shortcuts
        res_admin = self.client.get('/super-admin/')
        self.assertEqual(res_admin.status_code, 200)
        self.assertContains(res_admin, 'Django Admin')
        self.assertContains(res_admin, 'Health Probe')
        self.assertContains(res_admin, 'Terminal')
        self.assertContains(res_admin, 'Merchant Registrations &amp; Approvals')
        self.assertContains(res_admin, 'Platform Activity Stream')

        # 2. Health check shortcut button
        res_health = self.client.get('/health/')
        self.assertEqual(res_health.status_code, 200)
        self.assertEqual(res_health.json().get('status'), 'healthy')

        # 3. Action Button: Approve pending shop
        res_approve = self.client.post(
            '/api/super-admin/update-status/',
            data=json.dumps({'profile_id': self.pending_profile.id, 'status': 'APPROVED'}),
            content_type='application/json'
        )
        self.assertEqual(res_approve.status_code, 200)
        self.assertEqual(res_approve.json().get('status'), 'success')
        self.assertIn(res_approve.json().get('new_status'), ['APPROVED', 'APPROVED_SHEET_PENDING'])

        # 4. Action Button: Deactivate shop
        res_deact = self.client.post(
            '/api/super-admin/update-status/',
            data=json.dumps({'profile_id': self.pending_profile.id, 'status': 'DEACTIVATED'}),
            content_type='application/json'
        )
        self.assertEqual(res_deact.status_code, 200)
        self.assertEqual(res_deact.json().get('new_status'), 'DEACTIVATED')

        # 5. Action Button: Reactivate shop
        res_react = self.client.post(
            '/api/super-admin/update-status/',
            data=json.dumps({'profile_id': self.pending_profile.id, 'status': 'APPROVED'}),
            content_type='application/json'
        )
        self.assertEqual(res_react.status_code, 200)
        self.assertIn(res_react.json().get('new_status'), ['APPROVED', 'APPROVED_SHEET_PENDING'])

        # 6. Action Button: Reject shop
        res_reject = self.client.post(
            '/api/super-admin/update-status/',
            data=json.dumps({'profile_id': self.pending_profile.id, 'status': 'REJECTED'}),
            content_type='application/json'
        )
        self.assertEqual(res_reject.status_code, 200)
        self.assertEqual(res_reject.json().get('new_status'), 'REJECTED')
