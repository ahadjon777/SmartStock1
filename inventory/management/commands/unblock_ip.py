from django.core.management.base import BaseCommand

from inventory import security
from inventory.models import BlockedIP


class Command(BaseCommand):
    help = "Bloklangan IP'ni ochadi: unblock_ip 1.2.3.4  yoki  unblock_ip all (o'zingizni bloklab qo'ysangiz ham ishlaydi)"

    def add_arguments(self, parser):
        parser.add_argument("ip")

    def handle(self, *args, **opts):
        if opts["ip"] == "all":
            n, _ = BlockedIP.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f"{n} ta IP blokdan chiqarildi"))
        else:
            _, text = security.unblock_ip(opts["ip"])
            self.stdout.write(text)
