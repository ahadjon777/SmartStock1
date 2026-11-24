from django.core.management.base import BaseCommand

from inventory import security

FAKE_IP = "203.0.113.7"  # hujjatlar uchun ajratilgan IP: haqiqiy hech kimga tegishli emas


class Command(BaseCommand):
    help = "Telegram ogohlantirish va tugmalarni xavfsiz sinash: soxta brute-force hujumi yaratadi"

    def add_arguments(self, parser):
        parser.add_argument("--username", default="admin")

    def handle(self, *args, **opts):
        security.BACKGROUND = False
        for _ in range(security.settings.SECURITY_FAIL_LIMIT):
            security.on_login_failed(FAKE_IP, opts["username"])
        self.stdout.write(self.style.SUCCESS(
            f"Soxta hujum yaratildi ({FAKE_IP}). Telegram'da ogohlantirish va tugmalar kelishi kerak. "
            "Bir xil IP uchun 10 daqiqada faqat bitta ogohlantirish yuboriladi."
        ))
