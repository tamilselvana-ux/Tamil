import json
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, date
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.db import transaction
from django.utils.dateparse import parse_date

from apps.core.decorators import shop_required, get_user_shop
from apps.parties.models import Supplier
from apps.flowers.models import Flower
from apps.purchases.models import PurchaseLot, Posting
from apps.reports.pdf_generator import generate_koyambedu_bill_pdf

TWO_PLACES = Decimal('0.01')
THREE_PLACES = Decimal('0.001')

def quantize_money(val):
    if not isinstance(val, Decimal):
        val = Decimal(str(val))
    return val.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

def quantize_weight(val):
    if not isinstance(val, Decimal):
        val = Decimal(str(val))
    return val.quantize(THREE_PLACES, rounding=ROUND_HALF_UP)


@shop_required
def terminal_view(request):
    """Renders the main high-speed flower merchant trading terminal scoped to current shop."""
    shop = getattr(request, 'shop', None) or get_user_shop(request.user)
    suppliers = Supplier.objects.for_shop(shop).filter(status='Active').order_by('code')
    flowers = Flower.objects.for_shop(shop).filter(status='Active').order_by('code')
    
    return render(request, 'purchases/terminal.html', {
        'suppliers': suppliers,
        'flowers': flowers,
        'shop': shop,
    })


@shop_required
def purchase_list_api(request):
    """
    API to fetch purchase lots and supplier financial metadata for live terminal state.
    Strictly scoped to the logged-in user's shop.
    """
    shop = getattr(request, 'shop', None) or get_user_shop(request.user)
    supplier_param = request.GET.get('supplier', '').strip()
    date_val = request.GET.get('date', '').strip()
    from_date_str = request.GET.get('from_date', '').strip() or date_val
    to_date_str = request.GET.get('to_date', '').strip() or date_val
    unposted_only = request.GET.get('unposted_only', 'false').lower() in ('true', '1')

    qs = PurchaseLot.objects.for_shop(shop)

    supplier_info = {}
    if supplier_param:
        supplier_obj = Supplier.objects.for_shop(shop).filter(code__iexact=supplier_param).first()
        if not supplier_obj:
            # Also try matching by name or return 404
            supplier_obj = Supplier.objects.for_shop(shop).filter(name__iexact=supplier_param).first()

        if supplier_obj:
            qs = qs.filter(supplier=supplier_obj)
            supplier_info = {
                'id': supplier_obj.id,
                'code': supplier_obj.code,
                'name': supplier_obj.name,
                'area_name': supplier_obj.area_name or (supplier_obj.area.name if supplier_obj.area else ''),
                'commission_pct': str(supplier_obj.commission_pct),
                'luggage_default': str(supplier_obj.luggage_default),
                'adv_opening': str(supplier_obj.adv_opening),
                'outstanding_advance': str(supplier_obj.outstanding_advance),
                'status': supplier_obj.status
            }
        else:
            return JsonResponse({'status': 'error', 'message': f"Supplier '{supplier_param}' not found in your shop."}, status=404)

    if from_date_str and to_date_str:
        f_date = parse_date(from_date_str)
        t_date = parse_date(to_date_str)
        if f_date and t_date:
            qs = qs.filter(purchase_date__range=[f_date, t_date])
    elif date_val:
        d_val = parse_date(date_val)
        if d_val:
            qs = qs.filter(purchase_date=d_val)

    if unposted_only:
        qs = qs.filter(posting__isnull=True)

    qs = qs.order_by('purchase_date', 'created_at')

    lots = []
    for lot in qs:
        lots.append({
            'lot_id': lot.lot_id,
            'purchase_date': lot.purchase_date.strftime('%Y-%m-%d'),
            'party_code': lot.party_code,
            'party_name': lot.party_name,
            'flower_code': lot.flower_code,
            'flower_name': lot.flower_name,
            'weight': f"{lot.weight:.3f}",
            'rate': f"{lot.rate:.2f}",
            'gross_value': f"{lot.gross_value:.2f}",
            'boxes': lot.boxes,
            'lug_rate': f"{lot.lug_rate:.2f}",
            'luggage_amt': f"{lot.luggage_amt:.2f}",
            'coolie_rate': f"{lot.coolie_rate:.2f}",
            'coolie_amt': f"{lot.coolie_amt:.2f}",
            'net_lot_value': f"{lot.net_lot_value:.2f}",
            'posting_no': lot.posting_no or ''
        })

    return JsonResponse({
        'status': 'success',
        'lots': lots,
        'supplier': supplier_info
    })


@shop_required
def save_purchase_lots_batch_api(request):
    """
    Atomically persists a collection of purchase lots with server-side decimal math validation.
    Batch save is atomic: all lots saved or none. Posted lots cannot be edited.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'invalid_method'}, status=405)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON body.'}, status=400)

    lots_data = body.get('lots', [])
    if not lots_data:
        return JsonResponse({'status': 'error', 'message': 'No lots provided for batch save.'}, status=400)

    shop = getattr(request, 'shop', None) or get_user_shop(request.user)

    try:
        with transaction.atomic():
            saved_lots = []

            for data in lots_data:
                party_code = str(data.get('party_code', '')).strip()
                if not party_code:
                    raise ValueError("Party / Supplier code is required.")

                supplier = Supplier.objects.for_shop(shop).filter(code__iexact=party_code).first()
                if not supplier:
                    # Check by name fallback
                    supplier = Supplier.objects.for_shop(shop).filter(name__iexact=party_code).first()
                if not supplier:
                    raise ValueError(f"Unknown supplier '{party_code}'. Supplier must exist in your shop.")

                purchase_date_str = str(data.get('purchase_date', '')).strip()
                purchase_date = parse_date(purchase_date_str)
                if not purchase_date:
                    raise ValueError(f"Invalid purchase date: '{purchase_date_str}'. Must be YYYY-MM-DD.")

                flower_code = str(data.get('flower_code', '')).strip().upper()
                flower_name = str(data.get('flower_name', '')).strip() or flower_code
                flower_obj = Flower.objects.for_shop(shop).filter(code__iexact=flower_code).first()

                try:
                    weight = Decimal(str(data.get('weight', '0')))
                    rate = Decimal(str(data.get('rate', '0')))
                    boxes = int(data.get('boxes', 0))
                    lug_rate = Decimal(str(data.get('lug_rate', '0')))
                    coolie_rate = Decimal(str(data.get('coolie_rate', '0')))
                except Exception as num_err:
                    raise ValueError(f"Invalid numeric input in lot row: {num_err}")

                # Strict validation rules
                if weight <= Decimal('0'):
                    raise ValueError(f"Weight must be strictly greater than 0 kg. Given: {weight}")
                if rate < Decimal('0'):
                    raise ValueError(f"Rate must be non-negative. Given: {rate}")
                if boxes < 0:
                    raise ValueError(f"Boxes must be a non-negative integer. Given: {boxes}")
                if lug_rate < Decimal('0') or coolie_rate < Decimal('0'):
                    raise ValueError("Luggage and Coolie rates must be non-negative.")

                # Recompute strictly server-side with ROUND_HALF_UP
                weight_q = quantize_weight(weight)
                rate_q = quantize_money(rate)
                lug_rate_q = quantize_money(lug_rate)
                coolie_rate_q = quantize_money(coolie_rate)

                gross_value = quantize_money(weight_q * rate_q)
                luggage_amt = quantize_money(Decimal(boxes) * lug_rate_q)
                coolie_amt = quantize_money(Decimal(boxes) * coolie_rate_q)
                net_lot_value = quantize_money(gross_value - (luggage_amt + coolie_amt))

                lot_id = data.get('lot_id')
                if lot_id:
                    # Existing lot update
                    lot = PurchaseLot.objects.select_for_update().filter(shop=shop, lot_id=lot_id).first()
                    if not lot:
                        raise ValueError(f"Purchase lot with ID '{lot_id}' not found in your shop.")
                    if lot.is_posted:
                        raise ValueError(f"Cannot edit sealed/posted lot '{lot_id}' (Posting #{lot.posting_no}).")

                    lot.purchase_date = purchase_date
                    lot.supplier = supplier
                    lot.party_code = supplier.code
                    lot.party_name = supplier.name
                    lot.flower = flower_obj
                    lot.flower_code = flower_code
                    lot.flower_name = flower_name
                    lot.weight = weight_q
                    lot.rate = rate_q
                    lot.gross_value = gross_value
                    lot.boxes = boxes
                    lot.lug_rate = lug_rate_q
                    lot.luggage_amt = luggage_amt
                    lot.coolie_rate = coolie_rate_q
                    lot.coolie_amt = coolie_amt
                    lot.net_lot_value = net_lot_value
                    lot.save()
                else:
                    # New lot creation
                    lot = PurchaseLot.objects.create(
                        shop=shop,
                        purchase_date=purchase_date,
                        supplier=supplier,
                        party_code=supplier.code,
                        party_name=supplier.name,
                        flower=flower_obj,
                        flower_code=flower_code,
                        flower_name=flower_name,
                        weight=weight_q,
                        rate=rate_q,
                        gross_value=gross_value,
                        boxes=boxes,
                        lug_rate=lug_rate_q,
                        luggage_amt=luggage_amt,
                        coolie_rate=coolie_rate_q,
                        coolie_amt=coolie_amt,
                        net_lot_value=net_lot_value
                    )

                saved_lots.append({
                    'lot_id': lot.lot_id,
                    'purchase_date': lot.purchase_date.strftime('%Y-%m-%d'),
                    'party_code': lot.party_code,
                    'flower_code': lot.flower_code,
                    'weight': f"{lot.weight:.3f}",
                    'rate': f"{lot.rate:.2f}",
                    'gross_value': f"{lot.gross_value:.2f}",
                    'boxes': lot.boxes,
                    'net_lot_value': f"{lot.net_lot_value:.2f}"
                })

            return JsonResponse({
                'status': 'success',
                'saved_count': len(saved_lots),
                'lots': saved_lots
            })

    except ValueError as ve:
        return JsonResponse({'status': 'error', 'message': str(ve)}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f"Internal error during batch save: {str(e)}"}, status=400)


@shop_required
def save_purchase_lot_api(request):
    """Saves a single flower purchase lot directly with server-side decimal math validation."""
    if request.method != 'POST':
        return JsonResponse({'status': 'invalid_method'}, status=405)

    try:
        data = json.loads(request.body)
        body = {'lots': [data]}
        request._body = json.dumps(body).encode('utf-8')
        return save_purchase_lots_batch_api(request)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@shop_required
def create_posting_api(request):
    """
    Production Posting Cutoff Engine:
    - Atomically executed in transaction.atomic with select_for_update
    - Selects the supplier's unposted lots in date range
    - Validates advance deduction: 0 <= adv_deducted <= outstanding advance
    - Recomputes all totals on server using Decimal & ROUND_HALF_UP
    - Assigns race-safe sequential posting number per shop
    - Seals the lots with the posting foreign key and posting number
    - Tracks recovered advance against supplier balance
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'invalid_method'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON body.'}, status=400)

    shop = getattr(request, 'shop', None) or get_user_shop(request.user)
    supplier_param = str(data.get('supplier_code', '') or data.get('supplier_name', '')).strip()
    from_date_str = str(data.get('from_date', '')).strip()
    to_date_str = str(data.get('to_date', '')).strip()

    if not supplier_param:
        return JsonResponse({'status': 'error', 'message': 'Supplier code is a required parameter.'}, status=400)

    from_date = parse_date(from_date_str)
    to_date = parse_date(to_date_str)
    if not from_date or not to_date:
        return JsonResponse({'status': 'error', 'message': 'Valid from_date and to_date (YYYY-MM-DD) are required.'}, status=400)
    if from_date > to_date:
        return JsonResponse({'status': 'error', 'message': 'from_date cannot be after to_date.'}, status=400)

    try:
        adv_deducted_raw = Decimal(str(data.get('adv_deducted', '0.00')))
    except Exception:
        return JsonResponse({'status': 'error', 'message': 'Invalid advance deduction amount.'}, status=400)

    if adv_deducted_raw < Decimal('0'):
        return JsonResponse({'status': 'error', 'message': 'Advance deduction cannot be negative.'}, status=400)

    adv_deducted = quantize_money(adv_deducted_raw)

    try:
        with transaction.atomic():
            # Exact supplier lookup scoped to shop with lock
            supplier = Supplier.objects.select_for_update().filter(shop=shop, code__iexact=supplier_param).first()
            if not supplier:
                supplier = Supplier.objects.select_for_update().filter(shop=shop, name__iexact=supplier_param).first()
            if not supplier:
                return JsonResponse({'status': 'error', 'message': f"Supplier '{supplier_param}' not found in your shop."}, status=400)

            # Advance deduction validation: 0 <= amount <= outstanding advance balance
            outstanding = supplier.outstanding_advance
            if adv_deducted > outstanding:
                return JsonResponse({
                    'status': 'error',
                    'message': f"Advance deducted (₹{adv_deducted}) exceeds supplier's outstanding advance balance (₹{outstanding})."
                }, status=400)

            # Select unposted lots with lock
            lots = list(
                PurchaseLot.objects.select_for_update()
                .filter(
                    shop=shop,
                    supplier=supplier,
                    purchase_date__range=[from_date, to_date],
                    posting__isnull=True
                )
                .order_by('purchase_date', 'created_at')
            )

            if not lots:
                return JsonResponse({
                    'status': 'error',
                    'message': f"No unposted lots found for {supplier.name} between {from_date} and {to_date}."
                }, status=400)

            # Sequential race-safe posting sequence number per shop
            existing_postings = Posting.objects.select_for_update().filter(shop=shop)
            seq_nums = [int(p.posting_no) for p in existing_postings if p.posting_no and p.posting_no.isdigit()]
            next_seq = max(seq_nums, default=0) + 1
            posting_no = f"{next_seq:04d}"

            # Calculate server-side totals
            gross_total = quantize_money(sum(l.gross_value for l in lots))
            total_luggage = quantize_money(sum(l.luggage_amt for l in lots))
            total_coolie = quantize_money(sum(l.coolie_amt for l in lots))
            total_expense = quantize_money(Decimal(str(data.get('total_expense', '0.00'))))

            comm_pct = supplier.commission_pct
            commission = quantize_money(gross_total * (comm_pct / Decimal('100')))
            total_less = quantize_money(commission + total_luggage + total_coolie + total_expense + adv_deducted)
            net_balance = quantize_money(gross_total - total_less)

            posting = Posting.objects.create(
                shop=shop,
                posting_no=posting_no,
                supplier=supplier,
                supplier_name=f"{supplier.code} - {supplier.name}",
                from_date=from_date,
                to_date=to_date,
                gross_total=gross_total,
                commission=commission,
                total_luggage=total_luggage,
                total_coolie=total_coolie,
                total_expense=total_expense,
                adv_deducted=adv_deducted,
                total_less=total_less,
                net_balance=net_balance,
                created_by=request.user
            )

            # Seal matching lots
            for lot in lots:
                lot.posting = posting
                lot.posting_no = posting_no
                lot.save(update_fields=['posting', 'posting_no'])

            # Update supplier recovered advance
            if adv_deducted > Decimal('0'):
                supplier.advances_recovered = quantize_money(supplier.advances_recovered + adv_deducted)
                supplier.save(update_fields=['advances_recovered'])

            return JsonResponse({
                'status': 'success',
                'posting_id': posting.id,
                'posting_no': posting.posting_no,
                'sealed_lots_count': len(lots),
                'net_balance': f"{posting.net_balance:.2f}"
            })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@shop_required
def invoice_view(request):
    """
    Renders the official Koyambedu market bill view.
    Generated from either:
    1. A saved Posting (official sealed invoice)
    2. An explicit unposted date range & supplier (read-only draft preview)
    """
    shop = getattr(request, 'shop', None) or get_user_shop(request.user)
    posting_id = request.GET.get('posting_id')
    posting_no = request.GET.get('posting_no')

    posting = None
    is_draft = False

    if posting_id:
        posting = get_object_or_404(Posting, pk=posting_id, shop=shop)
    elif posting_no:
        posting = get_object_or_404(Posting, posting_no=posting_no, shop=shop)

    if posting:
        # Sealed bill from saved Posting
        from_date = posting.from_date.strftime('%Y-%m-%d')
        to_date = posting.to_date.strftime('%Y-%m-%d')
        supplier_obj = posting.supplier
        supplier_param = supplier_obj.code
        supplier_display_name = f"{supplier_obj.code} - {supplier_obj.name} ({supplier_obj.area_name or ''})"
        comm_pct = supplier_obj.commission_pct
        adv_deducted = posting.adv_deducted

        purchases = posting.lots.all().order_by('purchase_date', 'created_at')
        total_weight = sum(p.weight for p in purchases)
        total_boxes = sum(p.boxes for p in purchases)
        total_luggage = posting.total_luggage
        total_coolie = posting.total_coolie
        total_amt = posting.gross_total
        commission_amt = posting.commission
        total_less = posting.total_less
        net_balance = posting.net_balance
    else:
        # Draft Preview Mode
        is_draft = True
        supplier_param = request.GET.get('supplier', '').strip()
        from_date_str = request.GET.get('from_date', '').strip()
        to_date_str = request.GET.get('to_date', '').strip()

        if not supplier_param or not from_date_str or not to_date_str:
            # Fallback to current shop's first supplier and current date if none provided
            first_sup = Supplier.objects.for_shop(shop).filter(status='Active').first()
            if not supplier_param and first_sup:
                supplier_param = first_sup.code
            today_str = date.today().strftime('%Y-%m-%d')
            if not from_date_str:
                from_date_str = today_str
            if not to_date_str:
                to_date_str = today_str

        from_date_obj = parse_date(from_date_str)
        to_date_obj = parse_date(to_date_str)
        if not from_date_obj or not to_date_obj or from_date_obj > to_date_obj:
            return HttpResponseBadRequest("Invalid date range parameters.")

        from_date = from_date_str
        to_date = to_date_str

        supplier_obj = Supplier.objects.for_shop(shop).filter(code__iexact=supplier_param).first()
        if not supplier_obj:
            supplier_obj = Supplier.objects.for_shop(shop).filter(name__iexact=supplier_param).first()

        if not supplier_obj:
            return HttpResponseBadRequest(f"Supplier '{supplier_param}' not found in your shop.")

        supplier_display_name = f"{supplier_obj.code} - {supplier_obj.name} ({supplier_obj.area_name or ''})"
        comm_pct = supplier_obj.commission_pct

        # Fetch unposted lots in date range
        purchases = list(PurchaseLot.objects.for_shop(shop).filter(
            supplier=supplier_obj,
            purchase_date__range=[from_date_obj, to_date_obj],
            posting__isnull=True
        ).order_by('purchase_date', 'created_at'))

        # Opening advance is NOT auto-deducted
        adv_input = request.GET.get('advance')
        if adv_input is not None and adv_input != '':
            adv_deducted = quantize_money(Decimal(str(adv_input)))
            if adv_deducted > supplier_obj.outstanding_advance:
                adv_deducted = supplier_obj.outstanding_advance
        else:
            adv_deducted = Decimal('0.00')

        total_weight = sum(p.weight for p in purchases)
        total_boxes = sum(p.boxes for p in purchases)
        total_luggage = quantize_money(sum(p.luggage_amt for p in purchases))
        total_coolie = quantize_money(sum(p.coolie_amt for p in purchases))
        total_amt = quantize_money(sum(p.gross_value for p in purchases))

        commission_amt = quantize_money(total_amt * (comm_pct / Decimal('100')))
        total_less = quantize_money(commission_amt + total_luggage + total_coolie + adv_deducted)
        net_balance = quantize_money(total_amt - total_less)

    suppliers = Supplier.objects.for_shop(shop).filter(status='Active').order_by('code')

    context = {
        'from_date': from_date,
        'to_date': to_date,
        'supplier_name': supplier_param,
        'supplier_display_name': supplier_display_name,
        'purchases': purchases,
        'suppliers': suppliers,
        'total_weight': f"{total_weight:.3f}",
        'total_boxes': total_boxes,
        'total_luggage': f"{total_luggage:.2f}",
        'total_coolie': f"{total_coolie:.2f}",
        'total_amt': f"{total_amt:.2f}",
        'commission_pct': f"{comm_pct:.1f}",
        'commission_amt': f"{commission_amt:.2f}",
        'adv_deducted': f"{adv_deducted:.2f}",
        'total_less': f"{total_less:.2f}",
        'net_balance': f"{net_balance:.2f}",
        'is_draft': is_draft,
        'posting': posting
    }
    return render(request, 'reports/invoice.html', context)


@shop_required
def download_pdf_view(request):
    """
    Streams the generated ReportLab PDF matching Koyambedu physical bill.
    Strictly scoped to current shop.
    Returns 404 if another shop's posting or unowned supplier is requested.
    """
    shop = getattr(request, 'shop', None) or get_user_shop(request.user)
    posting_id = request.GET.get('posting_id')
    posting_no = request.GET.get('posting_no')

    posting = None
    is_draft = False

    if posting_id:
        posting = get_object_or_404(Posting, pk=posting_id, shop=shop)
    elif posting_no:
        posting = get_object_or_404(Posting, posting_no=posting_no, shop=shop)

    if posting:
        from_date = posting.from_date.strftime('%Y-%m-%d')
        to_date = posting.to_date.strftime('%Y-%m-%d')
        supplier_obj = posting.supplier
        party_name_str = f"{supplier_obj.name} - {supplier_obj.area_name or (supplier_obj.area.name if supplier_obj.area else '')}"
        comm_pct = supplier_obj.commission_pct
        adv_deducted = posting.adv_deducted
        purchases = posting.lots.all().order_by('purchase_date', 'created_at')

        total_weight = sum(p.weight for p in purchases)
        total_boxes = sum(p.boxes for p in purchases)
        total_luggage = posting.total_luggage
        total_coolie = posting.total_coolie
        total_amt = posting.gross_total
        commission_amt = posting.commission
        total_less = posting.total_less
        net_balance = posting.net_balance
    else:
        is_draft = True
        supplier_param = request.GET.get('supplier', '').strip()
        from_date_str = request.GET.get('from_date', '').strip()
        to_date_str = request.GET.get('to_date', '').strip()

        if not supplier_param or not from_date_str or not to_date_str:
            return HttpResponseBadRequest("supplier, from_date, and to_date are required parameters.")

        from_date_obj = parse_date(from_date_str)
        to_date_obj = parse_date(to_date_str)
        if not from_date_obj or not to_date_obj or from_date_obj > to_date_obj:
            return HttpResponseBadRequest("Invalid date range.")

        from_date = from_date_str
        to_date = to_date_str

        supplier_obj = get_object_or_404(Supplier, shop=shop, code__iexact=supplier_param)
        party_name_str = f"{supplier_obj.name} - {supplier_obj.area_name or (supplier_obj.area.name if supplier_obj.area else '')}"
        comm_pct = supplier_obj.commission_pct

        purchases = list(PurchaseLot.objects.for_shop(shop).filter(
            supplier=supplier_obj,
            purchase_date__range=[from_date_obj, to_date_obj],
            posting__isnull=True
        ).order_by('purchase_date', 'created_at'))

        adv_input = request.GET.get('advance')
        if adv_input is not None and adv_input != '':
            adv_deducted = quantize_money(Decimal(str(adv_input)))
            if adv_deducted > supplier_obj.outstanding_advance:
                adv_deducted = supplier_obj.outstanding_advance
        else:
            adv_deducted = Decimal('0.00')

        total_weight = sum(p.weight for p in purchases)
        total_boxes = sum(p.boxes for p in purchases)
        total_luggage = quantize_money(sum(p.luggage_amt for p in purchases))
        total_coolie = quantize_money(sum(p.coolie_amt for p in purchases))
        total_amt = quantize_money(sum(p.gross_value for p in purchases))

        commission_amt = quantize_money(total_amt * (comm_pct / Decimal('100')))
        total_less = quantize_money(commission_amt + total_luggage + total_coolie + adv_deducted)
        net_balance = quantize_money(total_amt - total_less)

    items = []
    for p in purchases:
        items.append({
            'date': p.purchase_date.strftime('%Y-%m-%d'),
            'flower': p.flower_name,
            'weight': f"{p.weight:.3f}",
            'rate': f"{p.rate:.2f}",
            'box': p.boxes,
            'luggage': f"{p.luggage_amt:.2f}",
            'coolie': f"{p.coolie_amt:.2f}",
            'total_amt': f"{p.gross_value:.2f}"
        })

    shop_title = shop.name or 'AVT Flower Merchants'
    market_addr = shop.market_address or 'FB-78, Kamarajar Flower Market, Koyambedu, Chennai-92'
    phone_no = shop.phone or '9360188707'

    title_suffix = " (DRAFT PREVIEW)" if is_draft else f" #{posting.posting_no if posting else ''}"

    bill_data = {
        'shop_name': shop_title,
        'devotional_motto': 'ARULMIGU VINAYAGA THUNAI   ARULMIGU VEERUCHINNAMMAL THUNAI',
        'market_address': market_addr,
        'phone': phone_no,
        'posting_upto': to_date + title_suffix,
        'party_name': party_name_str,
        'advance': f"{adv_deducted:.2f}",
        'items': items,
        'totals': {
            'total_weight': f"{total_weight:.3f}",
            'total_boxes': total_boxes,
            'total_luggage': f"{total_luggage:.2f}",
            'total_coolie': f"{total_coolie:.2f}",
            'total_amt': f"{total_amt:.2f}"
        },
        'deductions': {
            'commission_pct': f"{comm_pct:.1f}",
            'commission_amt': f"{commission_amt:.2f}",
            'total_luggage': f"{total_luggage:.2f}",
            'coolie': f"{total_coolie:.2f}",
            'total_expense': '0.00',
            'adv_deducted': f"{adv_deducted:.2f}",
            'total_less': f"{total_less:.2f}"
        },
        'settlement': {
            'total_amt': f"{total_amt:.2f}",
            'total_less': f"{total_less:.2f}",
            'net_balance': f"{net_balance:.2f}"
        }
    }

    pdf_bytes = generate_koyambedu_bill_pdf(bill_data)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    clean_name = party_name_str.replace(" ", "_").replace("/", "_")
    prefix = "DRAFT_" if is_draft else "POSTING_"
    response['Content-Disposition'] = f'attachment; filename="{prefix}Bill_{clean_name}_{from_date}_to_{to_date}.pdf"'
    return response
