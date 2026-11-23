from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

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
        lines.append(f"👤 {person} — jami {len(moves)} ta ({Region(region).label})")
        for m in moves:
            lines.append(f"   • {m.equipment.code} {m.equipment.name} → {m.holder or 'biriktirilmagan'}")
        lines.append("")
    return "\n".join(lines).strip()


def stats(period="oy"):
    days = PERIODS.get(period, 30)
    since = timezone.now() - timedelta(days=days)
    sums = defaultdict(lambda: [Decimal("0"), 0])
    for m in Movement.objects.filter(in_at__isnull=False, in_at__gte=since):
        s = sums[m.region]
        s[0] += m.work_hours
        s[1] += 1

    lines = [f"📊 Oxirgi {days} kun, o'rtacha ishlash vaqti:"]
    for value, label in Region.choices:
        total, count = sums.get(value, [Decimal("0"), 0])
        avg = (total / count).quantize(Decimal("0.01")) if count else Decimal("0")
        lines.append(f"• {label}: {avg} soat ({count} ta)")
    out = Equipment.objects.filter(status=Equipment.Status.OUT).count()
    lines.append(f"\nHozir tadbirda: {out} / {Equipment.objects.count()}")
    return "\n".join(lines)
