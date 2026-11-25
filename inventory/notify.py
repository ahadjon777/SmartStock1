import json
import logging
import threading
import urllib.request

from django.conf import settings

log = logging.getLogger(__name__)


def _send(text, buttons):
    token = settings.TELEGRAM_BOT_TOKEN
    for chat_id in settings.TELEGRAM_ADMIN_IDS:
        payload = {"chat_id": chat_id, "text": text}
        if buttons:
            payload["reply_markup"] = {
                "inline_keyboard": [[{"text": label, "callback_data": data} for label, data in row] for row in buttons]
            }
        try:
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=8)
        except Exception as exc:  # xabar yuborilmasa ham asosiy ish to'xtamasin
            log.warning("Telegram xabari yuborilmadi: %s", exc)


def notify(text, buttons=None, background=True):
    """Adminlarga Telegram xabari. buttons: qatorlar ro'yxati, har biri [(matn, callback_data), ...].

    Standart bo'yicha alohida oqimda yuboriladi: Telegram sekin yoki yopiq bo'lsa ham
    skanerlash va biriktirish so'rovlari kutib qolmaydi.
    """
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ADMIN_IDS:
        return
    if background:
        threading.Thread(target=_send, args=(text, buttons), daemon=True).start()
    else:
        _send(text, buttons)
