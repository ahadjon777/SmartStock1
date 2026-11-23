from openpyxl import load_workbook

from .models import Equipment, Warehouse


def import_workbook(source):
    """Excel (yo'l yoki fayl obyekti). Ustunlar: kod | nomi | ombor (1-qator sarlavha).
    Qaytaradi: (yangi, yangilangan, o'tkazib yuborilgan)."""
    ws = load_workbook(source, read_only=True).active
    created = updated = skipped = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        code, name, wh_name = (str(c).strip() if c else "" for c in (tuple(row) + (None, None, None))[:3])
        if not wh_name:
            skipped += 1
            continue
        warehouse, _ = Warehouse.objects.get_or_create(name=wh_name)
        _, was_created = Equipment.objects.update_or_create(
            code=code, defaults={"name": name or code, "warehouse": warehouse},
        )
        created += was_created
        updated += not was_created
    return created, updated, skipped
