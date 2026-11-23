import json
import logging
import urllib.request

from django.conf import settings

log = logging.getLogger(__name__)


def notify(text):
    """Adminlarga Telegram orqali xabar yuboradi (token sozlanmagan bo'lsa jim o'tadi)."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        return
    for chat_id in settings.TELEGRAM_ADMIN_IDS:
        try:
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=json.dumps({"chat_id": chat_id, "text": text}).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as exc:  # xabar yuborilmasa ham asosiy ish to'xtamasin
            log.warning("Telegram xabari yuborilmadi: %s", exc)
