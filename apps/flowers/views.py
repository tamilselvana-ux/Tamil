import json
from decimal import Decimal
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, Http404
from apps.core.decorators import shop_required, get_user_shop
from apps.flowers.models import Flower

@shop_required
def flowers_view(request):
    """Renders Flower Master catalogue strictly scoped to current shop."""
    shop = getattr(request, 'shop', None) or get_user_shop(request.user)
    flowers = Flower.objects.for_shop(shop).order_by('code')
    return render(request, 'flowers/flowers.html', {
        'flowers': flowers,
        'shop': shop
    })

@shop_required
def flowers_list_api(request):
    """API for autocomplete lookups on terminal grid strictly scoped to current shop."""
    shop = getattr(request, 'shop', None) or get_user_shop(request.user)
    q = request.GET.get('q', '').strip()
    qs = Flower.objects.for_shop(shop).filter(status='Active')
    if q:
        qs = qs.filter(code__icontains=q) | qs.filter(name__icontains=q)

    flower_list = []
    for f in qs:
        flower_list.append({
            'id': f.id,
            'code': f.code,
            'name': f.name,
            'default_rate': str(f.default_rate),
            'unit': f.unit
        })
    return JsonResponse({'status': 'success', 'flowers': flower_list})

@shop_required
def save_flower_api(request):
    """Creates or updates a flower strictly scoped to current shop with CSRF validation."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            shop = getattr(request, 'shop', None) or get_user_shop(request.user)
            flower_id = data.get('flower_id') or data.get('id')
            code = data.get('code', '').strip().upper()
            name = data.get('name', '').strip()
            rate_str = str(data.get('default_rate', '0.00'))

            if not code or not name:
                return JsonResponse({'status': 'error', 'message': 'Flower code and name are required.'}, status=400)

            default_rate = Decimal(rate_str)
            if default_rate < 0:
                return JsonResponse({'status': 'error', 'message': 'Rate cannot be negative.'}, status=400)

            if flower_id:
                flower = get_object_or_404(Flower, pk=flower_id, shop=shop)
                flower.code = code
                flower.name = name
                flower.default_rate = default_rate
                flower.save()
            else:
                if Flower.objects.for_shop(shop).filter(code__iexact=code).exists():
                    return JsonResponse({'status': 'error', 'message': f'Flower code {code} already exists for your shop.'}, status=400)

                flower = Flower.objects.create(
                    shop=shop,
                    code=code,
                    name=name,
                    default_rate=default_rate
                )

            return JsonResponse({
                'status': 'success',
                'flower': {
                    'id': flower.id,
                    'code': flower.code,
                    'name': flower.name,
                    'default_rate': str(flower.default_rate)
                }
            })
        except Http404:
            raise
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    return JsonResponse({'status': 'invalid_method'}, status=405)
