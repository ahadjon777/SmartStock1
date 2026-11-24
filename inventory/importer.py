from openpyxl import load_workbook

from .models import Equipment


COLUMN_NAMES = ("№", "Texnika nomi", "Ishlab chiqarilgan yili", "Inventar raqami")


def import_workbook(source, warehouse):
    """Import Excel rows; each row represents one item and inventory number is its unique QR code."""
    ws = load_workbook(source, read_only=True, data_only=True).active
    headers = [str(cell.value).strip() if cell.value is not None else "" for cell in ws[1]]
    if headers[:4] != list(COLUMN_NAMES):
        raise ValueError(
            "Excel ustunlari: №, Texnika nomi, Ishlab chiqarilgan yili, Inventar raqami bo'lishi kerak"
        )

    created = updated = skipped = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        values = tuple(row[:4]) + (None,) * max(0, 4 - len(row[:4]))
        if all(value is None for value in values):
            continue
        _, raw_name, raw_year, raw_code = values
        name = str(raw_name).strip() if raw_name is not None else ""
        code = str(raw_code).strip() if raw_code is not None else ""
        if not name or not code:
            skipped += 1
            continue
        try:
            year = int(raw_year) if raw_year not in (None, "") else None
        except (TypeError, ValueError):
            skipped += 1
            continue

        _, was_created = Equipment.objects.update_or_create(
            code=code,
            defaults={"name": name, "manufactured_year": year, "warehouse": warehouse},
        )
        created += int(was_created)
        updated += int(not was_created)
    return created, updated, skipped
