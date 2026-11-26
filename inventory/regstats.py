"""Viloyat -> joy -> tadbir bo'yicha statistika (sayt va Telegram bot uchun umumiy)."""
from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from .fmt import short_name
from .models import Movement, Region

NO_PLACE = "Joy ko'rsatilmagan"


def since_for(days):
    return timezone.now() - timedelta(days=days)


def _avg(total, n):
    return (total / n).quantize(Decimal("0.01")) if n else Decimal("0")


def _movements(since, region=None):
    qs = Movement.objects.filter(out_at__gte=since).select_related("equipment", "equipment__warehouse")
    if region:
        qs = qs.filter(region=region)
    return qs.order_by("-out_at")


def _event_key(m):
    # Bir chiqarish = bir xodim, bir vaqtda (checkout bitta vaqt belgisi qo'yadi), bir joyga
    return (m.taken_by, m.out_at, m.place.casefold().strip(), m.event)


def region_summary(since):
    """Har bir viloyat uchun: nechta joy, nechta tadbir (chiqarish), nechta texnika, o'rtacha ish vaqti."""
    data = OrderedDict((v, {"value": v, "label": l, "places": {}, "events": set(), "items": 0,
                            "work": Decimal("0"), "total": Decimal("0"), "done": 0})
                       for v, l in Region.choices)
    for m in _movements(since):
        r = data.setdefault(m.region, {"value": m.region, "label": Region.label_of(m.region), "places": {},
                                       "events": set(), "items": 0, "work": Decimal("0"),
                                       "total": Decimal("0"), "done": 0})
        if m.place.strip():
            r["places"].setdefault(m.place.casefold().strip(), m.place.strip())
        r["events"].add(_event_key(m))
        r["items"] += 1
        if m.in_at:
            r["done"] += 1
            r["work"] += m.work_hours
            r["total"] += m.total_hours
    rows = []
    for r in data.values():
        rows.append({
            "value": r["value"], "label": r["label"], "places": len(r["places"]), "events": len(r["events"]),
            "items": r["items"], "done": r["done"],
            "avg": _avg(r["work"], r["done"]), "avg_total": _avg(r["total"], r["done"]),
        })
    top = max((x["events"] for x in rows), default=0) or 1
    for x in rows:
        x["pct"] = round(x["events"] * 100 / top)
    # faol viloyatlar yuqorida, qolganlari alifbo tartibida pastda
    active = sorted((x for x in rows if x["items"]), key=lambda x: (-x["events"], x["label"]))
    idle = [x for x in rows if not x["items"] and x["value"] != Region.OTHER_REGIONS]
    return active + idle


def region_detail(since, region):
    """Viloyat ichida: joylar -> tadbirlar -> texnikalar."""
    places = OrderedDict()
    for m in _movements(since, region):
        key = m.place.casefold().strip()
        p = places.setdefault(key, {"name": m.place.strip() or NO_PLACE, "events": OrderedDict(),
                                    "items": 0, "people": set(), "last": m.out_at})
        p["items"] += 1
        p["people"].add(m.taken_by)
        e = p["events"].setdefault(_event_key(m), {
            "when": m.out_at, "person": m.taken_by, "event": m.event, "rows": [], "open": 0,
            "work": Decimal("0"), "done": 0,
        })
        e["rows"].append({
            "code": m.equipment.code, "name": short_name(m.equipment.name, 40),
            "holder": m.holder, "in_at": m.in_at, "warehouse": m.equipment.warehouse.name,
        })
        if m.in_at:
            e["done"] += 1
            e["work"] += m.work_hours
        else:
            e["open"] += 1
    out = []
    for p in places.values():
        evs = list(p["events"].values())
        for e in evs:
            e["avg"] = _avg(e["work"], e["done"]) if e["done"] else None
        out.append({"name": p["name"], "items": p["items"], "events": evs, "events_count": len(evs),
                    "people": sorted(p["people"]), "last": p["last"],
                    "open": sum(e["open"] for e in evs)})
    # joy ko'rsatilmaganlar oxirida
    out.sort(key=lambda x: (x["name"] == NO_PLACE, -x["events_count"], x["name"]))
    return out
