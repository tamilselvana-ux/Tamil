import json
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from apps.shops.models import Shop
from apps.accounts.models import ShopProfile
from apps.parties.models import Supplier, Area, LedgerGroup
from apps.flowers.models import Flower
from apps.purchases.models import PurchaseLot, Posting


class TenantIsolationTestCase(TestCase):
    def setUp(self):
        self.client = Client()

        # Shop A
        self.shop_a = Shop.objects.create(code='shop-a', name='Shop Alpha')
        self.user_a = User.objects.create_user(username='user_a', password='Password123!')
        self.profile_a = ShopProfile.objects.create(
            user=self.user_a, shop=self.shop_a, status=ShopProfile.STATUS_APPROVED
        )

        # Shop B
        self.shop_b = Shop.objects.create(code='shop-b', name='Shop Beta')
        self.user_b = User.objects.create_user(username='user_b', password='Password123!')
        self.profile_b = ShopProfile.objects.create(
            user=self.user_b, shop=self.shop_b, status=ShopProfile.STATUS_APPROVED
        )

        # Data for Shop A
        self.sup_a = Supplier.objects.create(
            shop=self.shop_a, code='SUP-A1', name='Supplier Alpha One',
            commission_pct=Decimal('15.00'), luggage_default=Decimal('150.00'),
            adv_opening=Decimal('5000.00')
        )
        self.flower_a = Flower.objects.create(
            shop=self.shop_a, code='ROSE-A', name='Red Rose Alpha',
            default_rate=Decimal('50.00')
        )
        self.lot_a = PurchaseLot.objects.create(
            shop=self.shop_a, purchase_date='2026-11-01',
            supplier=self.sup_a, party_code='SUP-A1', party_name=self.sup_a.name,
            flower=self.flower_a, flower_code='ROSE-A', flower_name=self.flower_a.name,
            weight=Decimal('100.000'), rate=Decimal('40.00'),
            gross_value=Decimal('4000.00'), boxes=5, lug_rate=Decimal('100.00'),
            luggage_amt=Decimal('500.00'), coolie_rate=Decimal('15.00'),
            coolie_amt=Decimal('75.00'), net_lot_value=Decimal('3425.00')
        )

        # Data for Shop B
        self.sup_b = Supplier.objects.create(
            shop=self.shop_b, code='SUP-B1', name='Supplier Beta One',
            commission_pct=Decimal('12.00'), luggage_default=Decimal('120.00'),
            adv_opening=Decimal('3000.00')
        )
        self.flower_b = Flower.objects.create(
            shop=self.shop_b, code='LILY-B', name='White Lily Beta',
            default_rate=Decimal('60.00')
        )
        self.posting_b = Posting.objects.create(
            shop=self.shop_b, posting_no='0001', supplier=self.sup_b,
            supplier_name=self.sup_b.name, from_date='2026-11-01', to_date='2026-11-02',
            gross_total=Decimal('5000.00'), commission=Decimal('600.00'),
            total_luggage=Decimal('200.00'), total_coolie=Decimal('50.00'),
            total_expense=Decimal('0.00'), adv_deducted=Decimal('0.00'),
            total_less=Decimal('850.00'), net_balance=Decimal('4150.00')
        )

    def test_shop_a_cannot_see_shop_b_suppliers_in_autocomplete(self):
        """Supplier autocomplete must only return suppliers belonging to user's shop."""
        self.client.force_login(self.user_a)
        resp = self.client.get('/api/parties/autocomplete/?q=Beta')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['suppliers']), 0, "Shop A saw Shop B's supplier")

        resp_a = self.client.get('/api/parties/autocomplete/?q=Alpha')
        self.assertEqual(resp_a.status_code, 200)
        self.assertEqual(len(resp_a.json()['suppliers']), 1)
        self.assertEqual(resp_a.json()['suppliers'][0]['code'], 'SUP-A1')

    def test_shop_a_cannot_access_shop_b_supplier_detail(self):
        """Looking up a supplier code from another shop must return 404."""
        self.client.force_login(self.user_a)
        resp = self.client.get('/api/parties/SUP-B1/')
        self.assertEqual(resp.status_code, 404)

    def test_shop_a_cannot_delete_or_modify_shop_b_supplier(self):
        """Deleting a supplier from another shop must return 404."""
        self.client.force_login(self.user_a)
        resp = self.client.post(f'/api/parties/delete/{self.sup_b.id}/')
        self.assertEqual(resp.status_code, 404)
        # Verify supplier B still exists
        self.assertTrue(Supplier.objects.filter(pk=self.sup_b.id).exists())

    def test_shop_a_cannot_view_or_edit_shop_b_flowers(self):
        """Shop A flower list must not contain Shop B flowers."""
        self.client.force_login(self.user_a)
        resp = self.client.get('/api/flowers/list/')
        self.assertEqual(resp.status_code, 200)
        flower_codes = [f['code'] for f in resp.json()['flowers']]
        self.assertIn('ROSE-A', flower_codes)
        self.assertNotIn('LILY-B', flower_codes)

        # Attempt to edit flower B
        payload = {
            'flower_id': self.flower_b.id,
            'code': 'LILY-HACK',
            'name': 'Hacked Lily',
            'default_rate': '99.00'
        }
        resp_edit = self.client.post(
            '/api/flowers/save/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(resp_edit.status_code, 404)
        self.flower_b.refresh_from_db()
        self.assertEqual(self.flower_b.code, 'LILY-B')

    def test_shop_a_cannot_view_or_post_shop_b_lots(self):
        """Shop A lot list query for Shop B supplier returns 404 error."""
        self.client.force_login(self.user_a)
        resp = self.client.get('/api/purchases/list/?supplier=SUP-B1')
        self.assertEqual(resp.status_code, 404)

    def test_shop_a_cannot_view_or_download_shop_b_posting(self):
        """Shop A invoice or PDF download for Shop B posting returns 404."""
        self.client.force_login(self.user_a)
        resp_inv = self.client.get(f'/invoice/?posting_id={self.posting_b.id}')
        self.assertEqual(resp_inv.status_code, 404)

        resp_pdf = self.client.get(f'/invoice/download-pdf/?posting_id={self.posting_b.id}')
        self.assertEqual(resp_pdf.status_code, 404)
