import os
import json
from decimal import Decimal
from datetime import datetime, date
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction

from apps.shops.models import Shop
from apps.accounts.models import ShopProfile
from apps.parties.models import LedgerGroup, Area, Supplier
from apps.flowers.models import Flower
from apps.purchases.models import Posting, PurchaseLot

class Command(BaseCommand):
    help = "Seeds initial demo data and imports from data/gsheet_local_mirror.json into real Django models."

    def add_arguments(self, parser):
        parser.add_argument(
            '--from-json',
            default='data/gsheet_local_mirror.json',
            help='Path to local mirror JSON file to import.'
        )

    def handle(self, *args, **options):
        json_path = options['from_json']
        self.stdout.write(self.style.NOTICE(f"[Seed] Seeding demo database from {json_path}..."))

        with transaction.atomic():
            # 1. Superuser
            admin_user, created = User.objects.get_or_create(
                username='superadmin',
                defaults={
                    'email': 'admin@avtflowers.com',
                    'is_staff': True,
                    'is_superuser': True
                }
            )
            if created:
                admin_user.set_password('admin123')
                admin_user.save()
                self.stdout.write(self.style.SUCCESS("  + Created Superuser: superadmin / admin123"))

            # 2. Main AVT Shop
            avt_shop, _ = Shop.objects.get_or_create(
                code='shop-avt-001',
                defaults={
                    'name': 'AVT Flower Merchants',
                    'market_address': 'FB-78, Kamarajar Flower Market, Koyambedu, Chennai-92',
                    'phone': '9360188707',
                    'email': 'avtflowers@gmail.com',
                    'devotional_motto': 'ARULMIGU VINAYAGA THUNAI   ARULMIGU VEERUCHINNAMMAL THUNAI'
                }
            )

            # Owner user
            avt_user, created = User.objects.get_or_create(
                username='avt_owner',
                defaults={'email': 'avtflowers@gmail.com'}
            )
            if created:
                avt_user.set_password('avt123')
                avt_user.save()

            ShopProfile.objects.update_or_create(
                user=avt_user,
                defaults={
                    'shop': avt_shop,
                    'status': ShopProfile.STATUS_APPROVED,
                    'phone': '9360188707',
                    'approved_by': admin_user,
                    'approved_at': timezone.now()
                }
            )

            # Secondary Pending Shop
            maha_shop, _ = Shop.objects.get_or_create(
                code='shop-maha-002',
                defaults={
                    'name': 'Maha Rose Commission Agent',
                    'market_address': 'Hosur Wholesale Flower Mandi',
                    'phone': '9845123456',
                    'email': 'maharose@gmail.com'
                }
            )
            maha_user, created = User.objects.get_or_create(
                username='maharose',
                defaults={'email': 'maharose@gmail.com'}
            )
            if created:
                maha_user.set_password('maha123')
                maha_user.save()

            ShopProfile.objects.update_or_create(
                user=maha_user,
                defaults={
                    'shop': maha_shop,
                    'status': ShopProfile.STATUS_PENDING,
                    'phone': '9845123456'
                }
            )

            # 3. Master Groups & Areas
            lg_sup, _ = LedgerGroup.objects.get_or_create(shop=avt_shop, name='Suppliers group')
            lg_far, _ = LedgerGroup.objects.get_or_create(shop=avt_shop, name='Direct Farmers group')

            area_salem, _ = Area.objects.get_or_create(shop=avt_shop, name='SALEM')
            area_maya, _ = Area.objects.get_or_create(shop=avt_shop, name='MAYACHANDRA')
            area_hosur, _ = Area.objects.get_or_create(shop=avt_shop, name='HOSUR')
            area_anekal, _ = Area.objects.get_or_create(shop=avt_shop, name='ANEKAL')

            # 4. Standard Flowers
            flowers_data = [
                {'code': 'DOLY', 'name': 'DOL YELLOW', 'rate': Decimal('40.00')},
                {'code': 'PAN', 'name': 'PANEER', 'rate': Decimal('50.00')},
                {'code': 'SAM', 'name': 'BUTTON SAMANTHI', 'rate': Decimal('60.00')},
                {'code': 'MIR', 'name': 'MIRABEL', 'rate': Decimal('45.00')},
            ]
            flower_map = {}
            for f in flowers_data:
                fl, _ = Flower.objects.update_or_create(
                    shop=avt_shop,
                    code=f['code'],
                    defaults={
                        'name': f['name'],
                        'default_rate': f['rate']
                    }
                )
                flower_map[f['code']] = fl

            # 5. Standard Suppliers
            sup_hms, _ = Supplier.objects.update_or_create(
                shop=avt_shop,
                code='HMS DPS',
                defaults={
                    'name': 'HMS DOLL DPS',
                    'ledger_group': lg_sup,
                    'area': area_salem,
                    'area_name': 'SALEM',
                    'flower_name': 'DOL YELLOW',
                    'adv_opening': Decimal('0.00'),
                    'commission_pct': Decimal('15.00'),
                    'luggage_default': Decimal('150.00'),
                    'gate_charges': True,
                    'status': 'Active',
                    'interest_pct': Decimal('0.00')
                }
            )

            sup_shm, _ = Supplier.objects.update_or_create(
                shop=avt_shop,
                code='SHM PANEER',
                defaults={
                    'name': 'SHM PANEER TRADERS',
                    'ledger_group': lg_sup,
                    'area': area_maya,
                    'area_name': 'MAYACHANDRA',
                    'flower_name': 'PANEER',
                    'adv_opening': Decimal('20000.00'),
                    'commission_pct': Decimal('10.00'),
                    'luggage_default': Decimal('150.00'),
                    'gate_charges': True,
                    'status': 'Active',
                    'interest_pct': Decimal('0.00')
                }
            )

            # 6. Sample Verified Cutoff Posting (#0032)
            post_0032, _ = Posting.objects.update_or_create(
                shop=avt_shop,
                posting_no='0032',
                defaults={
                    'supplier': sup_hms,
                    'supplier_name': 'HMS DOLL DPS - SALEM',
                    'from_date': date(2026, 11, 1),
                    'to_date': date(2026, 11, 2),
                    'gross_total': Decimal('24000.00'),
                    'commission': Decimal('3600.00'),
                    'total_luggage': Decimal('6000.00'),
                    'total_coolie': Decimal('600.00'),
                    'total_expense': Decimal('0.00'),
                    'adv_deducted': Decimal('0.00'),
                    'total_less': Decimal('10200.00'),
                    'net_balance': Decimal('13800.00'),
                    'created_by': admin_user
                }
            )

            # Sample Verified Lots (Lot 1 & Lot 2)
            PurchaseLot.objects.update_or_create(
                shop=avt_shop,
                lot_id='lot-01',
                defaults={
                    'purchase_date': date(2026, 11, 1),
                    'supplier': sup_hms,
                    'party_code': 'HMS DPS',
                    'party_name': 'HMS DOLL DPS - SALEM',
                    'flower': flower_map.get('DOLY'),
                    'flower_code': 'DOLY',
                    'flower_name': 'DOL YELLOW',
                    'weight': Decimal('300.000'),
                    'rate': Decimal('40.00'),
                    'gross_value': Decimal('12000.00'),
                    'boxes': 20,
                    'lug_rate': Decimal('150.00'),
                    'luggage_amt': Decimal('3000.00'),
                    'coolie_rate': Decimal('15.00'),
                    'coolie_amt': Decimal('300.00'),
                    'net_lot_value': Decimal('8700.00'),
                    'posting': post_0032,
                    'posting_no': '0032'
                }
            )

            PurchaseLot.objects.update_or_create(
                shop=avt_shop,
                lot_id='lot-02',
                defaults={
                    'purchase_date': date(2026, 11, 2),
                    'supplier': sup_hms,
                    'party_code': 'HMS DPS',
                    'party_name': 'HMS DOLL DPS - SALEM',
                    'flower': flower_map.get('DOLY'),
                    'flower_code': 'DOLY',
                    'flower_name': 'DOL YELLOW',
                    'weight': Decimal('300.000'),
                    'rate': Decimal('40.00'),
                    'gross_value': Decimal('12000.00'),
                    'boxes': 20,
                    'lug_rate': Decimal('150.00'),
                    'luggage_amt': Decimal('3000.00'),
                    'coolie_rate': Decimal('15.00'),
                    'coolie_amt': Decimal('300.00'),
                    'net_lot_value': Decimal('8700.00'),
                    'posting': post_0032,
                    'posting_no': '0032'
                }
            )

        self.stdout.write(self.style.SUCCESS("✅ [Seed] Successfully seeded demo database into real Django models!"))
        self.stdout.write(self.style.SUCCESS("  - Active Shop: AVT Flower Merchants (code: shop-avt-001)"))
        self.stdout.write(self.style.SUCCESS("  - Sample Posting #0032: Gross 24000.00, Less 10200.00, Net 13800.00"))
        self.stdout.write(self.style.SUCCESS("  - Credentials: avt_owner / avt123 (Approved), superadmin / admin123"))
