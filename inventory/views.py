import json
from datetime import timedelta
from collections import defaultdict
from decimal import Decimal

import segno
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Equipment, Movement, Region, Warehouse
from .notify import notify

PERIODS = {
    "week": ("Hafta", 7),
    "month": ("Oy", 30),
    "quarter": ("Chorak", 90),
    "half": ("Yarim yil", 182),
    "year": ("Yil", 365),
}


@login_required
def scan(request):
    return render(request, "inventory/scan.html", {"regions": Region.choices})


@login_required
@require_POST
def scan_api(request):
    """QR skanerlanganda: omborda bo'lsa chiqaradi, tadbirda bo'lsa qaytaradi."""
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"ok": False, "error": "Noto'g'ri so'rov"}, status=400)

    code = (data.get("code") or "").strip()
    now = timezone.now()

    with transaction.atomic():
        try:
            item = Equipment.objects.select_for_update().get(code=code)
        except Equipment.DoesNotExist:
            return JsonResponse({"ok": False, "error": "Bunday QR kodli texnika topilmadi"}, status=404)

        if item.status == Equipment.Status.IN_STOCK:
            taken_by = (data.get("taken_by") or "").strip()
            region = data.get("region")
            if not taken_by or region not in Region.values:
                return JsonResponse({"ok": False, "error": "F.I.Sh. va hududni kiriting"}, status=400)
            Movement.objects.create(
                equipment=item, issued_by=request.user, taken_by=taken_by,
                region=region, event=(data.get("event") or "").strip(), out_at=now,
            )
            item.status = Equipment.Status.OUT
            item.save(update_fields=["status"])
            notify(f"📤 {taken_by} oldi: {item.code} {item.name} ({Region(region).label})")
            return JsonResponse({"ok": True, "action": "out", "message": f"{item.name} chiqarildi"})

        movement = item.movements.filter(in_at__isnull=True).first()
        if movement:
            movement.in_at = now
            movement.save(update_fields=["in_at"])
        item.status = Equipment.Status.IN_STOCK
        item.save(update_fields=["status"])
        return JsonResponse({"ok": True, "action": "in", "message": f"{item.name} qaytarildi"})


@staff_member_required
def labels(request):
    """QR yorliqlarni chop etish: ?warehouse=<id>&q=<kod boshlanishi>&limit=<son>."""
    qs = Equipment.objects.select_related("warehouse").order_by("code")
    if request.GET.get("warehouse", "").isdigit():
        qs = qs.filter(warehouse_id=request.GET["warehouse"])
    if request.GET.get("q"):
        qs = qs.filter(code__startswith=request.GET["q"])
    limit = int(request.GET["limit"]) if request.GET.get("limit", "").isdigit() else 60
    items = [
        {"code": e.code, "name": e.name,
         "svg": segno.make(e.code, error="m").svg_inline(scale=4, border=1, dark="#000")}
        for e in qs[: min(limit, 500)]
    ]
    return render(request, "inventory/labels.html", {
        "items": items, "warehouses": Warehouse.objects.all(),
    })


@login_required
def assign(request):
    return render(request, "inventory/assign.html")


@login_required
@require_POST
def assign_api(request):
    """Tadbir joyida: javobgar olgan texnikalarni xodimga (F.I.Sh.) biriktiradi."""
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"ok": False, "error": "Noto'g'ri so'rov"}, status=400)

    holder = (data.get("holder") or "").strip()
    codes = [str(c).strip() for c in data.get("codes") or [] if str(c).strip()]
    if not holder or not codes:
        return JsonResponse({"ok": False, "error": "F.I.Sh. va kamida bitta kod kerak"}, status=400)

    movements = Movement.objects.filter(equipment__code__in=codes, in_at__isnull=True)
    found = set(movements.values_list("equipment__code", flat=True))
    missing = [c for c in codes if c not in found]
    movements.update(holder=holder)
    if found:
        notify(f"📌 {holder} ga biriktirildi: {len(found)} ta ({', '.join(sorted(found))})")
    return JsonResponse({
        "ok": bool(found), "assigned": len(found), "missing": missing,
        "message": f"{len(found)} ta texnika {holder} ga biriktirildi",
        "error": "Tadbirda bunday texnika yo'q" if not found else "",
    })


@login_required
def dashboard(request):
    key = request.GET.get("period", "month")
    if key not in PERIODS:
        key = "month"
    since = timezone.now() - timedelta(days=PERIODS[key][1])

    sums = defaultdict(lambda: [Decimal("0"), 0])
    qs = Movement.objects.filter(in_at__isnull=False, in_at__gte=since).select_related("equipment")
    for m in qs:
        s = sums[m.region]
        s[0] += m.work_hours
        s[1] += 1

    rows = []
    for value, label in Region.choices:
        total, count = sums.get(value, [Decimal("0"), 0])
        avg = (total / count).quantize(Decimal("0.01")) if count else Decimal("0")
        rows.append({"region": label, "count": count, "avg": avg})

    return render(request, "inventory/dashboard.html", {
        "rows": rows,
        "periods": [(k, v[0]) for k, v in PERIODS.items()],
        "current": key,
        "out_now": Equipment.objects.filter(status=Equipment.Status.OUT).count(),
        "total": Equipment.objects.count(),
    })
