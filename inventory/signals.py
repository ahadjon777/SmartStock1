import logging

from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from . import security

log = logging.getLogger(__name__)


@receiver(user_login_failed)
def _login_failed(sender, credentials=None, request=None, **kwargs):
    try:
        ip = security.client_ip(request) if request is not None else None
        security.on_login_failed(ip, str((credentials or {}).get("username") or ""))
    except Exception:  # xavfsizlik kuzatuvi kirish jarayonini buzmasligi kerak
        log.exception("login_failed hodisasini qayd etib bo'lmadi")


@receiver(user_logged_in)
def _login_ok(sender, request=None, user=None, **kwargs):
    try:
        security.on_login_ok(user, security.client_ip(request) if request is not None else None)
    except Exception:
        log.exception("login hodisasini qayd etib bo'lmadi")
