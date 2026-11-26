"""Telegram xabarlari va ro'yxatlar uchun qisqa ko'rinish: «qisqa nom · inv. № raqam»."""
import re


def short_name(name, limit=28):
    """Uzun nomni so'z chegarasida qisqartiradi: «Sony A7 III kamera obyektiv bilan komplekt» -> «Sony A7 III kamera…»."""
    name = re.sub(r"\s+", " ", name or "").strip()
    if len(name) <= limit:
        return name
    cut = name[:limit].rsplit(" ", 1)[0] or name[:limit]
    return cut.rstrip(" ,.;:-") + "…"


def item_label(equipment, limit=28):
    """«Kamera · inv. № 011010400001»: inventar raqami = texnikaning QR kodi."""
    return f"{short_name(equipment.name, limit)} · inv. № {equipment.code}"


def where(region_label, place=""):
    """Hudud va joyni bitta qatorga: «Samarqand viloyati · Urgut tumani»."""
    return " · ".join(x for x in (region_label, (place or "").strip()) if x)
