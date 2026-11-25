import json
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

import segno
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .access import display_name, is_admin, is_restricted, managed_warehouses
from .models import Equipment, Movement, Region, Warehouse
from .notify import notify

PERIODS = {
    "week": ("Hafta", 7),
    "month": ("Oy", 30),
    "quarter": ("Chorak", 90),
    "half": ("Yarim yil", 182),
    "year": ("Yil", 365),
}


def _body(request):
    try:
        data = json.loads(request.body)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _codes(data):
    codes = []
    for c in data.get("codes") or []:
        c = str(c).strip()
        if c and c not in codes:
            codes.append(c)
    return codes


def _bad(text, status=400):
    return JsonResponse({"ok": False, "error": text}, status=status)


def _mine(user):
    moves = Movement.objects.filter(in_at__isnull=True, holder_user=user).select_related("equipment")
    return [{"code": m.equipment.code, "name": m.equipment.name} for m in moves]


def _equipment_lines(items, limit=35):
    """Telegram uchun avval texnika nomi, so'ng inventar/QR kodini ko'rsatadi."""
    lines = [f"• {item.name} — {item.code}" for item in items[:limit]]
    if len(items) > limit:
        lines.append(f"… va yana {len(items) - limit} ta")
    return lines


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
def scan(request):
    """Bosh menyu."""
    return render(request, "inventory/scan.html", {"me": display_name(request.user)})


@login_required
def checkout(request):
    return render(request, "inventory/out.html", {"regions": Region.choices})


@login_required
@require_POST
def checkout_api(request):
    """Ombordan ko'p texnikani bir marta chiqaradi va bajargan xodimni qayd etadi."""
    data = _body(request)
    if data is None:
        return _bad("Noto'g'ri so'rov")
    codes = _codes(data)
    region = data.get("region")
    event = (data.get("event") or "").strip()
    if not codes:
        return _bad("Kamida bitta texnikani skanerlang")
    if region not in Region.values:
        return _bad("Hududni tanlang")

    me = display_name(request.user)
    now = timezone.now()
    restricted = is_restricted(request.user)
    mine = set(managed_warehouses(request.user).values_list("pk", flat=True)) if restricted else set()
    done, skipped, completed_items = [], [], []

    with transaction.atomic():
        items = {e.code: e for e in Equipment.objects.select_for_update().filter(code__in=codes)}
        for code in codes:
            e = items.get(code)
            if e is None:
                skipped.append({"code": code, "reason": "topilmadi"})
            elif restricted and e.warehouse_id not in mine:
                skipped.append({"code": code, "reason": "boshqa omborniki"})
            elif e.status != Equipment.Status.IN_STOCK:
                skipped.append({"code": code, "reason": "omborda emas"})
            else:
                Movement.objects.create(
                    equipment=e, issued_by=request.user, taken_by=me,
                    region=region, event=event, out_at=now,
                )
                e.status = Equipment.Status.OUT
                e.save(update_fields=["status"])
                done.append(code)
                completed_items.append(e)

    if done:
        place = Region(region).label + (f", {event}" if event else "")
        text = f"📤 OMBORDAN CHIQARILDI\n👤 Mas'ul: {me}\n📍 Manzil: {place}\n📦 Soni: {len(done)}\n\n"
        text += "\n".join(_equipment_lines(completed_items))
        notify(text)
    return JsonResponse({
        "ok": bool(done), "done": len(done), "skipped": skipped,
        "message": f"{len(done)} ta texnika chiqarildi",
        "error": "" if done else "Birorta texnika chiqarilmadi",
    })


@login_required
def take(request):
    """Xodim o'z telefonida texnikani skanerlab, o'ziga biriktiradi."""
    return render(request, "inventory/take.html", {"me": display_name(request.user), "mine": _mine(request.user)})


@login_required
@require_POST
def take_api(request):
    data = _body(request)
    if data is None:
        return _bad("Noto'g'ri so'rov")
    code = str(data.get("code") or "").strip()
    force = bool(data.get("force"))
    me = display_name(request.user)

    with transaction.atomic():
        try:
            item = Equipment.objects.select_for_update().get(code=code)
        except Equipment.DoesNotExist:
            return _bad("Bunday QR kodli texnika topilmadi", 404)
        move = item.movements.filter(in_at__isnull=True).first()
        if move is None:
            return _bad(f"{item.name} tadbirda emas (avval ombordan chiqarilishi kerak)")
        if move.holder_user_id == request.user.id:
            return JsonResponse({
                "ok": True, "already": True, "mine": _mine(request.user),
                "message": f"{item.name} allaqachon sizga biriktirilgan",
            })
        if move.holder and not force:
            return JsonResponse({
                "ok": False, "confirm": True, "holder": move.holder,
                "error": f"{item.name} hozir {move.holder} ga biriktirilgan",
            })
        move.holder = me
        move.holder_user = request.user
        move.save(update_fields=["holder", "holder_user"])

    notify(f"📌 TEXNIKA BIRIKTIRILDI\n👤 Xodim: {me}\n🏷 {item.name} — {item.code}")
    return JsonResponse({
        "ok": True, "mine": _mine(request.user),
        "message": f"{item.name} sizga biriktirildi",
    })


@login_required
def checkin(request):
    return render(request, "inventory/in.html")


@login_required
@require_POST
def checkin_api(request):
    """Ko'p texnikani qaytaradi; qaytargan xodim harakat tarixiga yoziladi."""
    data = _body(request)
    if data is None:
        return _bad("Noto'g'ri so'rov")
    codes = _codes(data)
    if not codes:
        return _bad("Kamida bitta texnikani skanerlang")

    now = timezone.now()
    restricted = is_restricted(request.user)
    mine = set(managed_warehouses(request.user).values_list("pk", flat=True)) if restricted else set()
    done, skipped, completed_items = [], [], []

    with transaction.atomic():
        items = {e.code: e for e in Equipment.objects.select_for_update().filter(code__in=codes)}
        for code in codes:
            e = items.get(code)
            if e is None:
                skipped.append({"code": code, "reason": "topilmadi"})
                continue
            if restricted and e.warehouse_id not in mine:
                skipped.append({"code": code, "reason": "boshqa omborniki"})
                continue
            move = e.movements.filter(in_at__isnull=True).first()
            if e.status != Equipment.Status.OUT or move is None:
                skipped.append({"code": code, "reason": "tadbirda emas"})
                continue
            move.in_at = now
            move.returned_by = request.user
            move.save(update_fields=["in_at", "returned_by"])
            e.status = Equipment.Status.IN_STOCK
            e.save(update_fields=["status"])
            done.append(code)
            completed_items.append(e)

    pending = Movement.objects.filter(in_at__isnull=True, issued_by=request.user).select_related("equipment")
    missing = [
        {"code": m.equipment.code, "name": m.equipment.name, "holder": m.holder or "biriktirilmagan"}
        for m in pending
    ]
    if done:
        text = f"📥 OMBORGA QAYTARILDI\n👤 Qabul qilgan: {display_name(request.user)}\n📦 Soni: {len(done)}\n\n"
        text += "\n".join(_equipment_lines(completed_items))
        if missing:
            text += f"\n\n⚠️ Shu mas'ul bo'yicha hali qaytmagan: {len(missing)} ta"
        notify(text)
    return JsonResponse({
        "ok": bool(done), "done": len(done), "skipped": skipped, "missing": missing,
        "message": f"{len(done)} ta texnika qaytarildi",
        "error": "" if done else "Birorta texnika qaytarilmadi",
    })


@login_required
def progress(request):
    """Javobgar uchun: olingan texnikalar nechtasi xodimlarga biriktirilgan."""
    qs = Movement.objects.filter(in_at__isnull=True).select_related("equipment", "issued_by").order_by("equipment__code")
    if not is_admin(request.user):
        qs = qs.filter(issued_by=request.user)
    groups = {}
    for m in qs:
        key = m.issued_by_id
        g = groups.setdefault(key, {"leader": m.taken_by, "rows": [], "assigned": 0})
        g["rows"].append(m)
        g["assigned"] += bool(m.holder)
    for g in groups.values():
        g["total"] = len(g["rows"])
        g["left"] = g["total"] - g["assigned"]
    return render(request, "inventory/progress.html", {"groups": list(groups.values())})


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
