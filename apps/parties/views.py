import json
from decimal import Decimal
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, Http404
from apps.core.decorators import shop_required, get_user_shop
from apps.parties.models import Supplier, Area, LedgerGroup
from apps.flowers.models import Flower

@shop_required
def suppliers_view(request):
    """Renders the 11-field Koyambedu Supplier/Party Master screen scoped to current shop."""
    shop = getattr(request, 'shop', None) or get_user_shop(request.user)
    suppliers = Supplier.objects.for_shop(shop).select_related('ledger_group', 'area').order_by('code')
    flowers = Flower.objects.for_shop(shop).order_by('code')
    areas = Area.objects.for_shop(shop).order_by('name')
    ledger_groups = LedgerGroup.objects.for_shop(shop).order_by('name')

    return render(request, 'parties/suppliers.html', {
        'suppliers': suppliers,
        'flowers': flowers,
        'areas': areas,
        'ledger_groups': ledger_groups,
        'shop': shop
    })

@shop_required
def supplier_autocomplete_api(request):
    """
    Explicit search / autocomplete endpoint.
    Filters by prefix/substring of code or name, strictly scoped to current shop.
    """
    shop = getattr(request, 'shop', None) or get_user_shop(request.user)
    q = request.GET.get('q', '').strip()
    qs = Supplier.objects.for_shop(shop).filter(status='Active')
    if q:
        qs = qs.filter(code__icontains=q) | qs.filter(name__icontains=q)

    results = []
    for s in qs[:20]:
        results.append({
            'id': s.id,
            'code': s.code,
            'name': s.name,
            'area_name': s.area_name or (s.area.name if s.area else ''),
            'commission_pct': str(s.commission_pct),
            'luggage_default': str(s.luggage_default),
            'outstanding_advance': str(s.outstanding_advance)
        })
    return JsonResponse({'status': 'success', 'suppliers': results})

@shop_required
def supplier_detail_api(request, code):
    """
    Exact case-insensitive match on supplier code.
    Returns 404 error if unknown supplier, never a silent default.
    """
    shop = getattr(request, 'shop', None) or get_user_shop(request.user)
    supplier = get_object_or_404(Supplier, shop=shop, code__iexact=code.strip())
    return JsonResponse({
        'status': 'success',
        'supplier': {
            'id': supplier.id,
            'code': supplier.code,
            'name': supplier.name,
            'area_name': supplier.area_name or (supplier.area.name if supplier.area else ''),
            'commission_pct': str(supplier.commission_pct),
            'luggage_default': str(supplier.luggage_default),
            'outstanding_advance': str(supplier.outstanding_advance),
            'status': supplier.status
        }
    })

@shop_required
def save_supplier_api(request):
    """Saves or updates a supplier record strictly scoped to current shop with CSRF validation."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            shop = getattr(request, 'shop', None) or get_user_shop(request.user)
            supplier_id = data.get('supplier_id') or data.get('id')
            code = data.get('code', '').strip().upper()
            name = data.get('name', '').strip()

            if not code or not name:
                return JsonResponse({'status': 'error', 'message': 'Supplier Code and Name are required.'}, status=400)

            commission_pct = Decimal(str(data.get('commission_pct', '15.00')))
            if commission_pct < 0 or commission_pct > 100:
                return JsonResponse({'status': 'error', 'message': 'Commission percentage must be between 0 and 100.'}, status=400)

            luggage_default = Decimal(str(data.get('luggage_default', '150.00')))
            if luggage_default < 0:
                return JsonResponse({'status': 'error', 'message': 'Luggage rate must be non-negative.'}, status=400)

            adv_opening = Decimal(str(data.get('adv_opening', '0.00')))
            ledger_op_bal = Decimal(str(data.get('ledger_op_bal', '0.00')))
            interest_pct = Decimal(str(data.get('interest_pct', '0.00')))
            area_name = data.get('area_name', '').strip().upper()
            flower_name = data.get('flower_name', '').strip()
            gate_charges = bool(data.get('gate_charges', True))
            status = data.get('status', 'Active')

            # Area & LedgerGroup resolution
            area_obj = None
            if area_name:
                area_obj, _ = Area.objects.get_or_create(shop=shop, name=area_name)

            lg_name = data.get('ledger_group', 'Suppliers group')
            lg_obj, _ = LedgerGroup.objects.get_or_create(shop=shop, name=lg_name)

            if supplier_id:
                supplier = get_object_or_404(Supplier, pk=supplier_id, shop=shop)
                supplier.code = code
                supplier.name = name
                supplier.ledger_group = lg_obj
                supplier.ledger_op_bal = ledger_op_bal
                supplier.area = area_obj
                supplier.area_name = area_name
                supplier.flower_name = flower_name
                supplier.adv_opening = adv_opening
                supplier.commission_pct = commission_pct
                supplier.luggage_default = luggage_default
                supplier.gate_charges = gate_charges
                supplier.status = status
                supplier.interest_pct = interest_pct
                supplier.save()
                mode = 'updated'
            else:
                # Check for duplicate code within shop
                if Supplier.objects.for_shop(shop).filter(code__iexact=code).exists():
                    return JsonResponse({'status': 'error', 'message': f'Supplier code {code} already exists for your shop.'}, status=400)

                supplier = Supplier.objects.create(
                    shop=shop,
                    code=code,
                    name=name,
                    ledger_group=lg_obj,
                    ledger_op_bal=ledger_op_bal,
                    area=area_obj,
                    area_name=area_name,
                    flower_name=flower_name,
                    adv_opening=adv_opening,
                    commission_pct=commission_pct,
                    luggage_default=luggage_default,
                    gate_charges=gate_charges,
                    status=status,
                    interest_pct=interest_pct
                )
                mode = 'created'

            return JsonResponse({
                'status': 'success',
                'mode': mode,
                'supplier': {
                    'id': supplier.id,
                    'code': supplier.code,
                    'name': supplier.name,
                    'area_name': supplier.area_name,
                    'commission_pct': str(supplier.commission_pct),
                    'luggage_default': str(supplier.luggage_default),
                    'status': supplier.status
                }
            })
        except Http404:
            raise
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    return JsonResponse({'status': 'invalid_method'}, status=405)

@shop_required
def delete_supplier_api(request, supplier_id):
    """Deletes a supplier record strictly scoped to current shop with CSRF validation."""
    if request.method in ['POST', 'DELETE']:
        shop = getattr(request, 'shop', None) or get_user_shop(request.user)
        supplier = get_object_or_404(Supplier, pk=supplier_id, shop=shop)
        # Check if supplier has posted lots
        if supplier.postings.exists() or supplier.lots.filter(posting__isnull=False).exists():
            return JsonResponse({'status': 'error', 'message': 'Cannot delete supplier with posted lots. Please deactivate instead.'}, status=400)

        supplier.delete()
        return JsonResponse({'status': 'success'})

    return JsonResponse({'status': 'invalid_method'}, status=405)
