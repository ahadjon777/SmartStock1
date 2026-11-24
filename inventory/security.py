import ipaddress
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

from .models import BlockedIP, SecurityEvent, SecurityState
from .notify import notify

log = logging.getLogger(__name__)
User = get_user_model()

CACHE_TTL = 10  # soniya: boshqa jarayonda (bot) qilingan o'zgarish shu vaqtda ko'rinadi
BACKGROUND = True  # ogohlantirish alohida oqimda yuboriladi (so'rovni sekinlashtirmaslik uchun)


# ---------- IP va holat ----------

def client_ip(request):
    ip = request.META.get("REMOTE_ADDR") or None
    if settings.TRUST_X_FORWARDED_FOR:
        # Ishonchli proksi so'nggi yozuvni o'zi qo'shadi, chap tomondagilarni soxtalashtirish mumkin
        last = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[-1].strip()
        try:
            ip = str(ipaddress.ip_address(last))
        except ValueError:
            pass
    return ip


def blocked_ips():
    return cache.get_or_set("sec:blocked", lambda: set(BlockedIP.objects.values_list("ip", flat=True)), CACHE_TTL)


def is_blocked(ip):
    return bool(ip) and ip in blocked_ips()


def lockdown_on():
    return cache.get_or_set("sec:lockdown", lambda: SecurityState.objects.filter(pk=1, lockdown=True).exists(), CACHE_TTL)


# ---------- Harakatlar (Telegram tugmalari ham shularni chaqiradi) ----------

def block_ip(ip, reason=""):
    try:
        ip = str(ipaddress.ip_address(ip))
    except (ValueError, TypeError):
        return False, "IP noto'g'ri"
    if ip in settings.SECURITY_ALLOWLIST_IPS:
        return False, f"{ip} ruxsat etilgan ro'yxatda, bloklanmadi"
    _, created = BlockedIP.objects.get_or_create(ip=ip, defaults={"reason": reason[:200]})
    cache.delete("sec:blocked")
    return True, f"🚫 {ip} bloklandi" if created else f"{ip} allaqachon bloklangan"


def unblock_ip(ip):
    deleted, _ = BlockedIP.objects.filter(ip=ip).delete()
    cache.delete("sec:blocked")
    return (True, f"♻️ {ip} blokdan chiqarildi") if deleted else (False, f"{ip} bloklanganlar ro'yxatida yo'q")


def lock_user(username):
    user = User.objects.filter(username=username).first()
    if user is None:
        return False, f"'{username}' degan foydalanuvchi yo'q"
    if user.is_superuser and user.is_active and not User.objects.filter(is_superuser=True, is_active=True).exclude(pk=user.pk).exists():
        return False, "Bu yagona faol superuser: qulflasangiz o'zingiz kira olmaysiz. Buning o'rniga IP'ni bloklang yoki lockdown yoqing."
    user.is_active = False  # faol sessiyalar ham darhol yaroqsiz bo'ladi
    user.save(update_fields=["is_active"])
    return True, f"🔒 '{username}' akkaunti qulflandi"


def set_lockdown(on):
    SecurityState.objects.update_or_create(pk=1, defaults={"lockdown": bool(on)})
    cache.delete("sec:lockdown")
    return True, "🛑 Lockdown YOQILDI: faqat superuserlar ishlay oladi" if on else "🔓 Lockdown o'chirildi"


def handle_action(action, arg):
    """Telegram tugmasi bosilganda. Qaytaradi: (muvaffaqiyatli, matn)."""
    if action == "ldon":
        return set_lockdown(True)
    if action == "ldoff":
        return set_lockdown(False)
    if action == "ub":
        return unblock_ip(arg)
    event = SecurityEvent.objects.filter(pk=arg).first() if str(arg).isdigit() else None
    if event is None:
        return False, "Hodisa topilmadi"
    if action == "ok":
        SecurityEvent.objects.filter(pk=event.pk).update(handled=True)
        return True, "✅ Ko'rib chiqildi deb belgilandi"
    if action == "blk":
        ok, text = block_ip(event.ip, f"{event.kind}: {event.detail}")
    elif action == "lock":
        ok, text = lock_user(event.username)
    else:
        return False, "Noma'lum amal"
    if ok:
        SecurityEvent.objects.filter(pk=event.pk).update(handled=True)
    return ok, text


# ---------- Hodisalarni qayd etish va ogohlantirish ----------

def record(kind, ip=None, username="", detail=""):
    return SecurityEvent.objects.create(kind=kind, ip=ip or None, username=(username or "")[:150], detail=detail[:300])


def _since(minutes):
    return timezone.now() - timedelta(minutes=minutes)


def _recent(kind, minutes, **filters):
    return SecurityEvent.objects.filter(kind=kind, created_at__gte=_since(minutes), **filters).exists()


def alert(event, text, block=True, lock=True):
    buttons = []
    if block and event.ip and not is_blocked(event.ip):
        buttons.append([(f"🚫 {event.ip} ni bloklash", f"sec:blk:{event.pk}")])
    if lock and event.username and User.objects.filter(username=event.username, is_active=True).exists():
        buttons.append([(f"🔒 '{event.username}' ni qulflash", f"sec:lock:{event.pk}")])
    buttons.append([("🛑 Lockdown (hammasini yopish)", "sec:ldon:0")])
    buttons.append([("✅ Ko'rib chiqdim", f"sec:ok:{event.pk}")])
    notify(text, buttons, background=BACKGROUND)


def on_login_failed(ip, username):
    record("login_failed", ip, username)
    if ip:
        n = SecurityEvent.objects.filter(kind="login_failed", ip=ip, created_at__gte=_since(5)).count()
        if n >= settings.SECURITY_FAIL_LIMIT and not _recent("bruteforce", 10, ip=ip):
            ev = record("bruteforce", ip, username, f"{n} marta noto'g'ri parol")
            alert(ev, f"🚨 Parol tanlash (brute-force) hujumi ehtimoli\nIP: {ip}\nLogin: {username or '—'}\n"
                      f"So'nggi 5 daqiqada {n} marta noto'g'ri parol kiritildi.")
    if username:
        m = SecurityEvent.objects.filter(kind="login_failed", username=username, created_at__gte=_since(10)).count()
        if m >= settings.SECURITY_USER_FAIL_LIMIT and not _recent("user_attack", 10, username=username):
            ev = record("user_attack", ip, username, f"{m} marta noto'g'ri parol")
            alert(ev, f"🚨 '{username}' akkauntiga ko'p urinish (turli IP'lardan bo'lishi mumkin)\n"
                      f"So'nggi 10 daqiqada {m} marta noto'g'ri parol.")


def on_login_ok(user, ip):
    seen = SecurityEvent.objects.filter(kind="login_ok", username=user.username, ip=ip).exists()
    record("login_ok", ip, user.username)
    if (user.is_staff or user.is_superuser) and not seen:
        ev = record("admin_login", ip, user.username, "yangi IP'dan admin kirishi")
        alert(ev, f"🔑 Admin akkauntiga yangi IP'dan kirildi\nLogin: {user.username}\nIP: {ip}\n"
                  f"Bu siz bo'lmasangiz, darhol choralarni ko'ring.")


def report_scan(ip, path):
    if _recent("scan", 10, ip=ip):
        return
    ev = record("scan", ip, "", f"oxirgi yo'l: {path}"[:300])
    alert(ev, f"🔎 Skanerlash ehtimoli\nIP: {ip}\nBir daqiqada {settings.SECURITY_SCAN_LIMIT}+ ta mavjud bo'lmagan "
              f"yoki taqiqlangan sahifa so'raldi (oxirgisi: {path}).", lock=False)


# ---------- Bot buyruqlari uchun matnlar ----------

def recent_events_text(limit=10):
    events = SecurityEvent.objects.exclude(kind__in=["login_failed", "login_ok"])[:limit]
    if not events:
        return "Xavfli hodisa yo'q ✅"
    tz = timezone.get_current_timezone()
    lines = []
    for e in events:
        when = timezone.localtime(e.created_at, tz).strftime("%d.%m %H:%M")
        mark = "✔" if e.handled else "❗"
        lines.append(f"{mark} {when} {e.kind} {e.ip or ''} {e.username} {e.detail}".strip())
    state = "YOQILGAN 🛑" if lockdown_on() else "o'chiq"
    return "So'nggi xavfsizlik hodisalari:\n" + "\n".join(lines) + f"\n\nLockdown: {state}"
