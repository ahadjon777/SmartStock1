from django.conf import settings
from django.contrib.auth import logout
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone

from . import security


class IdleTimeoutMiddleware:
    """10 daqiqalik faolsizlikdan keyin sessiyani tugatadi."""

    timeout_seconds = 10 * 60

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            now = timezone.now().timestamp()
            last_activity = request.session.get("last_activity")

            if last_activity and now - float(last_activity) > self.timeout_seconds:
                logout(request)
                return HttpResponseRedirect(f'{reverse(settings.LOGIN_URL)}?timeout=1')

            request.session["last_activity"] = now

        return self.get_response(request)


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
