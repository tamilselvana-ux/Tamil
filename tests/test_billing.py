import json
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from apps.shops.models import Shop
from apps.accounts.models import ShopProfile
from apps.parties.models import Supplier
from apps.flowers.models import Flower
from apps.purchases.models import PurchaseLot, Posting


class BillingAndPostingTestCase(TestCase):
    def setUp(self):
        self.client = Client()

        # Shop 1 (AVT)
        self.shop1 = Shop.objects.create(code='shop-avt', name='AVT Flower Merchant')
        self.user1 = User.objects.create_user(username='avt_user', password='Password123!')
        self.profile1 = ShopProfile.objects.create(
            user=self.user1, shop=self.shop1, status=ShopProfile.STATUS_APPROVED
        )

        # Shop 2 (Other)
        self.shop2 = Shop.objects.create(code='shop-other', name='Other Merchant')
        self.user2 = User.objects.create_user(username='other_user', password='Password123!')
        self.profile2 = ShopProfile.objects.create(
            user=self.user2, shop=self.shop2, status=ShopProfile.STATUS_APPROVED
        )

        # Flowers
        self.fl_doly = Flower.objects.create(
            shop=self.shop1, code='DOLY', name='DOL YELLOW', default_rate=Decimal('40.00')
        )
        self.fl_pan = Flower.objects.create(
            shop=self.shop1, code='PAN', name='PANEER ROSE', default_rate=Decimal('80.00')
        )

        # Supplier with opening advance = 10,000.00
        self.supplier = Supplier.objects.create(
            shop=self.shop1,
            code='HMS DPS',
            name='HMS DOLL DPS',
            commission_pct=Decimal('15.00'),
            luggage_default=Decimal('150.00'),
            adv_opening=Decimal('10000.00')
        )

    def test_opening_advance_not_auto_deducted(self):
        """Opening advance must NOT be automatically deducted on bill preview."""
        self.client.force_login(self.user1)

        # Create an unposted lot
        PurchaseLot.objects.create(
            shop=self.shop1,
            purchase_date='2026-11-01',
            supplier=self.supplier,
            party_code=self.supplier.code,
            party_name=self.supplier.name,
            flower=self.fl_doly,
            flower_code=self.fl_doly.code,
            flower_name=self.fl_doly.name,
            weight=Decimal('100.000'),
            rate=Decimal('40.00'),
            gross_value=Decimal('4000.00'),
            boxes=2,
            lug_rate=Decimal('150.00'),
            luggage_amt=Decimal('300.00'),
            coolie_rate=Decimal('15.00'),
            coolie_amt=Decimal('30.00'),
            net_lot_value=Decimal('3670.00')
        )

        # Access invoice draft preview without specifying advance
        resp = self.client.get(f'/invoice/?supplier={self.supplier.code}&from_date=2026-11-01&to_date=2026-11-02')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['adv_deducted'], '0.00', "Opening advance was improperly auto-deducted")

    def test_advance_validation_against_outstanding_balance(self):
        """Deducted advance cannot exceed supplier's outstanding advance balance."""
        self.client.force_login(self.user1)

        # Create unposted lot
        PurchaseLot.objects.create(
            shop=self.shop1, purchase_date='2026-11-01',
            supplier=self.supplier, party_code=self.supplier.code, party_name=self.supplier.name,
            flower=self.fl_doly, flower_code=self.fl_doly.code, flower_name=self.fl_doly.name,
            weight=Decimal('50.000'), rate=Decimal('40.00'), gross_value=Decimal('2000.00'),
            boxes=1, lug_rate=Decimal('150.00'), luggage_amt=Decimal('150.00'),
            coolie_rate=Decimal('15.00'), coolie_amt=Decimal('15.00'), net_lot_value=Decimal('1835.00')
        )

        # Supplier outstanding is 10,000.00. Attempting to deduct 12,000.00 must return 400.
        payload = {
            'supplier_code': self.supplier.code,
            'from_date': '2026-11-01',
            'to_date': '2026-11-02',
            'adv_deducted': '12000.00'
        }
        resp = self.client.post(
            '/api/postings/create/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('exceeds supplier', resp.json()['message'])

    def test_posting_seals_lots_and_prevents_double_billing(self):
        """Cutoff posting seals lots, assigns sequential number, and prevents double billing."""
        self.client.force_login(self.user1)

        # Create 2 unposted lots
        lot1 = PurchaseLot.objects.create(
            shop=self.shop1, purchase_date='2026-11-01',
            supplier=self.supplier, party_code=self.supplier.code, party_name=self.supplier.name,
            flower=self.fl_doly, flower_code=self.fl_doly.code, flower_name=self.fl_doly.name,
            weight=Decimal('300.000'), rate=Decimal('40.00'), gross_value=Decimal('12000.00'),
            boxes=20, lug_rate=Decimal('150.00'), luggage_amt=Decimal('3000.00'),
            coolie_rate=Decimal('15.00'), coolie_amt=Decimal('300.00'), net_lot_value=Decimal('8700.00')
        )
        lot2 = PurchaseLot.objects.create(
            shop=self.shop1, purchase_date='2026-11-02',
            supplier=self.supplier, party_code=self.supplier.code, party_name=self.supplier.name,
            flower=self.fl_pan, flower_code=self.fl_pan.code, flower_name=self.fl_pan.name,
            weight=Decimal('300.000'), rate=Decimal('40.00'), gross_value=Decimal('12000.00'),
            boxes=20, lug_rate=Decimal('150.00'), luggage_amt=Decimal('3000.00'),
            coolie_rate=Decimal('15.00'), coolie_amt=Decimal('300.00'), net_lot_value=Decimal('8700.00')
        )

        # Execute cutoff posting
        payload = {
            'supplier_code': self.supplier.code,
            'from_date': '2026-11-01',
            'to_date': '2026-11-03',
            'adv_deducted': '0.00'
        }
        resp = self.client.post(
            '/api/postings/create/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        posting_id = data['posting_id']
        posting_no = data['posting_no']
        self.assertEqual(posting_no, '0001')

        # Check lots are sealed
        lot1.refresh_from_db()
        lot2.refresh_from_db()
        self.assertIsNotNone(lot1.posting)
        self.assertEqual(lot1.posting_no, '0001')
        self.assertTrue(lot1.is_posted)
        self.assertEqual(lot2.posting_no, '0001')

        # Check calculation on saved posting
        posting = Posting.objects.get(pk=posting_id)
        self.assertEqual(posting.gross_total, Decimal('24000.00'))
        self.assertEqual(posting.commission, Decimal('3600.00'))
        self.assertEqual(posting.total_less, Decimal('10200.00'))
        self.assertEqual(posting.net_balance, Decimal('13800.00'))

        # Attempting to post the same date range again must find 0 unposted lots (Double Billing Impossible)
        resp_double = self.client.post(
            '/api/postings/create/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(resp_double.status_code, 400)
        self.assertIn('No unposted lots found', resp_double.json()['message'])

    def test_posted_lot_cannot_be_edited(self):
        """Posted lots cannot be edited through batch save."""
        self.client.force_login(self.user1)

        lot = PurchaseLot.objects.create(
            shop=self.shop1, purchase_date='2026-11-01',
            supplier=self.supplier, party_code=self.supplier.code, party_name=self.supplier.name,
            flower=self.fl_doly, flower_code=self.fl_doly.code, flower_name=self.fl_doly.name,
            weight=Decimal('100.000'), rate=Decimal('40.00'), gross_value=Decimal('4000.00'),
            boxes=2, lug_rate=Decimal('150.00'), luggage_amt=Decimal('300.00'),
            coolie_rate=Decimal('15.00'), coolie_amt=Decimal('30.00'), net_lot_value=Decimal('3670.00'),
            posting_no='0032'
        )

        payload = {
            'lots': [{
                'lot_id': str(lot.lot_id),
                'party_code': self.supplier.code,
                'purchase_date': '2026-11-01',
                'flower_code': 'DOLY',
                'weight': '150.000',
                'rate': '50.00',
                'boxes': 3,
                'lug_rate': '150.00',
                'coolie_rate': '15.00'
            }]
        }
        resp = self.client.post(
            '/api/purchases/batch-save/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('sealed/posted', resp.json()['message'])

    def test_batch_save_atomicity_rolls_back_on_single_bad_row(self):
        """A single invalid row in batch save must roll back all rows (all or none)."""
        self.client.force_login(self.user1)

        initial_count = PurchaseLot.objects.filter(shop=self.shop1).count()

        payload = {
            'lots': [
                {
                    'party_code': self.supplier.code,
                    'purchase_date': '2026-11-01',
                    'flower_code': 'DOLY',
                    'weight': '50.000',
                    'rate': '40.00',
                    'boxes': 2,
                    'lug_rate': '150.00',
                    'coolie_rate': '15.00'
                },
                {
                    # Invalid row: negative weight
                    'party_code': self.supplier.code,
                    'purchase_date': '2026-11-01',
                    'flower_code': 'PAN',
                    'weight': '-10.000',
                    'rate': '80.00',
                    'boxes': 1,
                    'lug_rate': '150.00',
                    'coolie_rate': '15.00'
                }
            ]
        }
        resp = self.client.post(
            '/api/purchases/batch-save/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)

        # Verify no rows were inserted
        final_count = PurchaseLot.objects.filter(shop=self.shop1).count()
        self.assertEqual(final_count, initial_count, "Batch save was not atomic! Incomplete rows persisted.")

    def test_pdf_endpoint_returns_valid_pdf_and_404_for_other_shop(self):
        """PDF endpoint generates a valid PDF for current shop and 404 for another shop's posting."""
        self.client.force_login(self.user1)

        # Create posting for Shop 1
        posting1 = Posting.objects.create(
            shop=self.shop1, posting_no='0001', supplier=self.supplier,
            supplier_name=self.supplier.name, from_date='2026-11-01', to_date='2026-11-02',
            gross_total=Decimal('4000.00'), commission=Decimal('600.00'),
            total_luggage=Decimal('300.00'), total_coolie=Decimal('30.00'),
            total_expense=Decimal('0.00'), adv_deducted=Decimal('0.00'),
            total_less=Decimal('930.00'), net_balance=Decimal('3070.00')
        )

        # Posting for Shop 2
        sup2 = Supplier.objects.create(shop=self.shop2, code='SUP-2', name='Supplier Two')
        posting2 = Posting.objects.create(
            shop=self.shop2, posting_no='0001', supplier=sup2,
            supplier_name=sup2.name, from_date='2026-11-01', to_date='2026-11-02',
            gross_total=Decimal('5000.00'), commission=Decimal('750.00'),
            total_luggage=Decimal('200.00'), total_coolie=Decimal('20.00'),
            total_expense=Decimal('0.00'), adv_deducted=Decimal('0.00'),
            total_less=Decimal('970.00'), net_balance=Decimal('4030.00')
        )

        # User 1 requesting Shop 1's posting
        resp1 = self.client.get(f'/invoice/download-pdf/?posting_id={posting1.id}')
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp1['Content-Type'], 'application/pdf')
        self.assertTrue(resp1.content.startswith(b'%PDF-'), "Response is not a valid PDF")

        # User 1 requesting Shop 2's posting -> MUST RETURN 404
        resp2 = self.client.get(f'/invoice/download-pdf/?posting_id={posting2.id}')
        self.assertEqual(resp2.status_code, 404)
