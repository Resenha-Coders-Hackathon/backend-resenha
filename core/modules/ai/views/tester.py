from pathlib import Path

from django.http import HttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser


@require_GET
@api_view(["GET"])
@permission_classes([IsAdminUser])
@ensure_csrf_cookie
def analysis_tester(request):
    page = Path(__file__).resolve().parents[1] / "analyze.html"
    return HttpResponse(page.read_bytes(), content_type="text/html; charset=utf-8")
