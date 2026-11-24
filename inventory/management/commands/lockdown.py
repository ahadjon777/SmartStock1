from django.core.management.base import BaseCommand

from inventory import security


class Command(BaseCommand):
    help = "Lockdown rejimi: lockdown on | off (bot ishlamay qolsa ham o'chirish mumkin)"

    def add_arguments(self, parser):
        parser.add_argument("state", choices=["on", "off"])

    def handle(self, *args, **opts):
        _, text = security.set_lockdown(opts["state"] == "on")
        self.stdout.write(text)
