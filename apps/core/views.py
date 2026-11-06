from datetime import datetime
from django.http import JsonResponse
from apps.shops.models import Shop
from apps.parties.models import Supplier
from apps.purchases.models import PurchaseLot, Posting

def health_check_view(request):
    """
    Production health check and diagnostic probe.
    Returns JSON response for uptime monitors, Docker healthchecks, and Kubernetes liveness probes.
    """
    try:
        shops_count = Shop.objects.count()
        suppliers_count = Supplier.objects.count()
        purchases_count = PurchaseLot.objects.count()
        postings_count = Posting.objects.count()

        return JsonResponse({
            "status": "healthy",
            "service": "AVT Flower Merchant & Commission Agent System",
            "version": "2.0.0",
            "timestamp": datetime.now().isoformat(),
            "database": {
                "engine": "Django ORM (PostgreSQL / SQLite)",
                "connected": True,
                "records": {
                    "shops": shops_count,
                    "suppliers": suppliers_count,
                    "purchases": purchases_count,
                    "postings": postings_count
                }
            }
        }, status=200)
    except Exception as e:
        return JsonResponse({
            "status": "degraded",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }, status=503)
