from openpyxl import load_workbook

from .models import Equipment, Warehouse


COLUMN_NAMES = (
    "№",
    "Texnika nomi",
    "Ishlab chiqarilgan yili",
    "Inventar raqami",
)


def import_workbook(source, warehouse):
    """Excel faylidan texnikalar import qiladi.

    Ustun tartibi: № | Texnika nomi | Ishlab chiqarilgan yili | Inventar raqami
    """
    ws = load_workbook(source, read_only=True, data_only=True).active

    headers = [str(cell.value).strip() if cell.value is not None else "" for cell in ws[1]]

    if headers[:4] != list(COLUMN_NAMES):
        raise ValueError(
            "Excel ustunlari: №, Texnika nomi, Ishlab chiqarilgan yili, Inventar raqami bo'lishi kerak"
        )

    created = updated = skipped = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or all(value is None for value in row[:4]):
            continue

        _, name, manufactured_year, inventory_number = (
            tuple(str(value).strip() if value is not None else "" for value in row[:4])
        )

        if not name or not inventory_number:
            skipped += 1
            continue

        try:
            year = int(manufactured_year) if manufactured_year else None
        except (TypeError, ValueError):
            year = None

        equipment, was_created = Equipment.objects.update_or_create(
            code=inventory_number,
            defaults={
                "name": name,
                "manufactured_year": year,
                "warehouse": warehouse,
            },
        )
        created += was_created
        updated += not was_created

    return created, updated, skipped
