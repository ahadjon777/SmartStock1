from django.core.management.base import BaseCommand, CommandError
from openpyxl import load_workbook

from inventory.models import Equipment, Warehouse


class Command(BaseCommand):
    help = "Excel'dan texnikalarni yuklaydi. Ustunlar: kod | nomi | ombor (1-qator sarlavha)"

    def add_arguments(self, parser):
        parser.add_argument("path", help=".xlsx fayl yo'li")

    def handle(self, *args, **opts):
        try:
            ws = load_workbook(opts["path"], read_only=True).active
        except Exception as exc:
            raise CommandError(f"Faylni o'qib bo'lmadi: {exc}")

        created = updated = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or not row[0]:
                continue
            code, name, wh_name = (str(c).strip() if c else "" for c in (row + (None, None, None))[:3])
            if not wh_name:
                continue
            warehouse, _ = Warehouse.objects.get_or_create(name=wh_name)
            _, was_created = Equipment.objects.update_or_create(
                code=code, defaults={"name": name or code, "warehouse": warehouse},
            )
            created += was_created
            updated += not was_created
        self.stdout.write(self.style.SUCCESS(f"Yangi: {created}, yangilandi: {updated}"))
