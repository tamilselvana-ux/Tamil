from decimal import Decimal, ROUND_HALF_UP
from django.test import TestCase


def calculate_lot_values(weight, rate, boxes, lug_rate, coolie_rate):
    """Core lot formula validation helper."""
    w = Decimal(str(weight)).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
    r = Decimal(str(rate)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    b = int(boxes)
    lr = Decimal(str(lug_rate)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    cr = Decimal(str(coolie_rate)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    gross = (w * r).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    luggage = (Decimal(b) * lr).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    coolie = (Decimal(b) * cr).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    net_lot = (gross - (luggage + coolie)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return gross, luggage, coolie, net_lot


def calculate_posting_statement(gross_total, commission_pct, total_luggage, total_coolie, expenses, advance_deducted):
    """Core billing cutoff statement formula validation helper."""
    gt = Decimal(str(gross_total)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    cp = Decimal(str(commission_pct))
    tl = Decimal(str(total_luggage)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    tc = Decimal(str(total_coolie)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    exp = Decimal(str(expenses)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    adv = Decimal(str(advance_deducted)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    commission = (gt * (cp / Decimal('100'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    total_less = (commission + tl + tc + exp + adv).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    net_balance = (gt - total_less).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return commission, total_less, net_balance


class CalculationEngineTestCase(TestCase):
    def test_sample_result_accounting_verification(self):
        """
        Verify the canonical flower market sample result:
        gross 24000.00, commission 3600.00 (15%), total less 10200.00, net balance 13800.00.
        """
        # Lot 1: 300.000 kg @ ₹40.00 = ₹12,000.00, 20 boxes @ ₹150 lug = 3000, 20 boxes @ 15 coolie = 300
        g1, lug1, cool1, net1 = calculate_lot_values('300.000', '40.00', 20, '150.00', '15.00')
        self.assertEqual(g1, Decimal('12000.00'))
        self.assertEqual(lug1, Decimal('3000.00'))
        self.assertEqual(cool1, Decimal('300.00'))

        # Lot 2: 300.000 kg @ ₹40.00 = ₹12,000.00, 20 boxes @ ₹150 lug = 3000, 20 boxes @ 15 coolie = 300
        g2, lug2, cool2, net2 = calculate_lot_values('300.000', '40.00', 20, '150.00', '15.00')
        self.assertEqual(g2, Decimal('12000.00'))
        self.assertEqual(lug2, Decimal('3000.00'))
        self.assertEqual(cool2, Decimal('300.00'))

        total_gross = g1 + g2  # 24,000.00
        total_lug = lug1 + lug2  # 6,000.00
        total_cool = cool1 + cool2  # 600.00

        # Cutoff statement calculation with 15% commission, 0 expense, 0 advance deducted:
        # total_less = 3600 (comm) + 6000 (lug) + 600 (coolie) = 10200.00
        comm, total_less, net_balance = calculate_posting_statement(
            gross_total=total_gross,
            commission_pct='15.00',
            total_luggage=total_lug,
            total_coolie=total_cool,
            expenses='0.00',
            advance_deducted='0.00'
        )

        self.assertEqual(total_gross, Decimal('24000.00'))
        self.assertEqual(comm, Decimal('3600.00'))
        self.assertEqual(total_less, Decimal('10200.00'))
        self.assertEqual(net_balance, Decimal('13800.00'))

    def test_decimal_rounding_half_up(self):
        """Rounding half up test for money (0.005 -> 0.01) and weight."""
        # 12.345 * 10 = 123.450 -> 123.45
        # 12.355 * 10 = 123.55
        # 33.333 kg @ 33.33/kg
        w = Decimal('33.333')
        r = Decimal('33.33')
        gross = (w * r).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        # 33.333 * 33.33 = 1110.98889 -> 1110.99
        self.assertEqual(gross, Decimal('1110.99'))

        # Half up: 1.005 -> 1.01
        half = Decimal('1.005').quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.assertEqual(half, Decimal('1.01'))

        # Half up: 1.004 -> 1.00
        half_down = Decimal('1.004').quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.assertEqual(half_down, Decimal('1.00'))

    def test_zero_lot_and_zero_boxes(self):
        """Validates calculations with 0 boxes and positive weight."""
        g, lug, cool, net = calculate_lot_values('15.500', '120.00', 0, '150.00', '15.00')
        self.assertEqual(g, Decimal('1860.00'))
        self.assertEqual(lug, Decimal('0.00'))
        self.assertEqual(cool, Decimal('0.00'))
        self.assertEqual(net, Decimal('1860.00'))
