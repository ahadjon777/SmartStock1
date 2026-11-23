from django.core.management.base import BaseCommand, CommandError

from inventory.importer import import_workbook


class Command(BaseCommand):
    help = "Excel'dan texnikalarni yuklaydi. Ustunlar: kod | nomi | ombor (1-qator sarlavha)"

    def add_arguments(self, parser):
        parser.add_argument("path", help=".xlsx fayl yo'li")

    def handle(self, *args, **opts):
        try:
            created, updated, skipped = import_workbook(opts["path"])
        except Exception as exc:
            raise CommandError(f"Faylni o'qib bo'lmadi: {exc}")
        self.stdout.write(self.style.SUCCESS(f"Yangi: {created}, yangilandi: {updated}, o'tkazildi: {skipped}"))
