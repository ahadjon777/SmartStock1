from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseForbidden

from . import security


class ThreatMiddleware:
    """Bloklangan IP'larni to'sadi, lockdown'ni amalga oshiradi va skanerlashni aniqlaydi."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ip = security.client_ip(request)

        if security.is_blocked(ip):
            return HttpResponseForbidden("Ruxsat yo'q")

        if security.lockdown_on():
            user = request.user
            allowed = (user.is_authenticated and user.is_superuser) or request.path.startswith("/accounts/login")
            if not allowed:
                return HttpResponse("Tizim vaqtincha yopilgan.", status=503)

        response = self.get_response(request)

        if ip and response.status_code in (403, 404):
            key = f"sec:scan:{ip}"
            try:
                n = cache.incr(key)
            except ValueError:
                cache.set(key, 1, 60)
                n = 1
            if n == settings.SECURITY_SCAN_LIMIT:
                security.report_scan(ip, request.path)
        return response
