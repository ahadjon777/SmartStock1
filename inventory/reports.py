from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from . import regstats
from .models import Equipment, Movement, Region

PERIODS = {"hafta": 7, "oy": 30, "chorak": 90, "yarim": 182, "yil": 365}


def who_has_what():
    """Hozir tadbirda bo'lgan texnikalar: kim jami olgan va kimga biriktirilgan (F.I.Sh. bilan)."""
    open_moves = Movement.objects.filter(in_at__isnull=True).select_related("equipment").order_by("taken_by", "equipment__code")
    groups = defaultdict(list)
    for m in open_moves:
        groups[(m.taken_by, m.region)].append(m)
    if not groups:
        return "Hozir tadbirda texnika yo'q."

    lines = []
    for (person, region), moves in groups.items():
        lines.append(f"👤 {person} — jami {len(moves)} ta ({Region.label_of(region)})")
        for m in moves:
            lines.append(f"   • {m.equipment.code} {m.equipment.name} → {m.holder or 'biriktirilmagan'}")
        lines.append("")
    return "\n".join(lines).strip()


def stats(period="oy"):
    days = PERIODS.get(period, 30)
    rows = [r for r in regstats.region_summary(regstats.since_for(days)) if r["items"]]
    lines = [f"📊 Oxirgi {days} kun, viloyatlar bo'yicha:"]
    for n, r in enumerate(rows, 1):
        work = f", o'rtacha ish {r['avg']} soat" if r["done"] else ""
        lines.append(f"{n}. {r['label']}: {r['places']} ta joyda, {r['events']} ta tadbir, {r['items']} ta texnika{work}")
    if not rows:
        lines.append("Bu davrda tadbir bo'lmagan.")
    out = Equipment.objects.filter(status=Equipment.Status.OUT).count()
    lines.append(f"\nHozir tadbirda: {out} / {Equipment.objects.count()}")
    return "\n".join(lines)
