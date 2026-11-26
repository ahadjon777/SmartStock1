import json
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

import segno
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .access import display_name, is_admin, is_restricted, managed_warehouses
from .fmt import item_label, short_name
from .fmt import where as fmt_where
from . import regstats
from .models import Equipment, Movement, Region, Warehouse
from .notify import notify
from .version import BUILD


def make_qr(code):
    """Faqat oddiy (standart) QR. segno.make() qisqa raqamli kodlarni avtomatik «Micro QR» qilib yaratadi:
    telefon kamerasi va brauzer skaneri Micro QR'ni o'qiy olmaydi (faqat ayrim qo'l skanerlari o'qiydi)."""
    # mask=4: brauzer skaneri (zxing-js) 300 ta sinov kodining 299 tasini o'qidi; avtomatik tanlangan niqob esa 286 tasini
    return segno.make_qr(code, error="m", mask=4)


def qr_svg(code):
    # border=4: standart bo'yicha QR atrofidagi bo'sh maydon (quiet zone) kamida 4 modul bo'lishi kerak.
    # scale=6: ekranda va chop etishda modul kattaroq, telefon kamerasi uzoqdan ham o'qiy oladi
    return make_qr(code).svg_inline(scale=6, border=4, dark="#000", light="#fff")


QR_BUILD = BUILD  # /labels/ sahifasida ko'rinadi: server yangi kodda ishlayotganini tekshirish uchun

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
    moves = (
        Movement.objects.filter(in_at__isnull=True, holder_user=user)
        .select_related("equipment").order_by("equipment__code")
    )
    return [
        {
            "code": m.equipment.code, "name": m.equipment.name, "event": m.event,
            "region": Region.label_of(m.region), "place": m.place,
        }
        for m in moves
    ]


def _find_equipment(code):
    """QR kod bo'yicha texnikani topadi (avval aniq, keyin katta-kichik harfga e'tiborsiz). Faqat tranzaksiya ichida."""
    qs = Equipment.objects.select_for_update()
    try:
        return qs.get(code=code)
    except Equipment.DoesNotExist:
        return qs.filter(code__iexact=code).first()


def _equipment_lines(items, limit=35):
    """Telegram uchun avval texnika nomi, so'ng inventar/QR kodini ko'rsatadi."""
    lines = [f"• {item_label(item)}" for item in items[:limit]]
    if len(items) > limit:
        lines.append(f"… va yana {len(items) - limit} ta")
    return lines


@never_cache
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
        {"code": e.code, "name": short_name(e.name, 40), "svg": qr_svg(e.code)}
        for e in qs[: min(limit, 500)]
    ]
    sample = make_qr(items[0]["code"]) if items else None
    qr_info = None
    if sample is not None:
        side = sample.symbol_size(border=0)[0]
        qr_info = {"micro": sample.is_micro, "version": sample.version, "side": side, "build": QR_BUILD}
    return render(request, "inventory/labels.html", {
        "items": items, "warehouses": Warehouse.objects.all(), "qr_info": qr_info,
    })


@login_required
def scan(request):
    """Bosh menyu."""
    return render(request, "inventory/scan.html", {
        "me": display_name(request.user),
        "mine_count": Movement.objects.filter(in_at__isnull=True, holder_user=request.user).count(),
    })


@login_required
def checkout(request):
    places = defaultdict(list)
    for region, place in (Movement.objects.exclude(place="").values_list("region", "place")
                          .distinct().order_by("place")):
        if place not in places[region]:
            places[region].append(place)
    return render(request, "inventory/out.html", {"regions": Region.selectable(), "places": dict(places)})


@login_required
@require_POST
def checkout_api(request):
    """Ombordan ko'p texnikani bir marta chiqaradi va bajargan xodimni qayd etadi."""
    data = _body(request)
    if data is None:
        return _bad("Noto'g'ri so'rov")
    codes = _codes(data)
    region = data.get("region")
    event = (data.get("event") or "").strip()[:200]
    place = " ".join((data.get("place") or "").split())[:200]
    if not codes:
        return _bad("Kamida bitta texnikani skanerlang")
    if region not in dict(Region.selectable()):
        return _bad("Viloyatni tanlang")

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
                    region=region, place=place, event=event, out_at=now,
                )
                e.status = Equipment.Status.OUT
                e.save(update_fields=["status"])
                done.append(code)
                completed_items.append(e)

    if done:
        place = fmt_where(Region.label_of(region), place) + (f", {event}" if event else "")
        text = f"📤 OMBORDAN CHIQARILDI\n👤 Mas'ul: {me}\n📍 Manzil: {place}\n📦 Soni: {len(done)}\n\n"
        text += "\n".join(_equipment_lines(completed_items))
        notify(text, [[("📦 Tadbirda nima bor", "n:out")]])
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
    """Bitta texnikani skanerlagan xodimga biriktiradi. Takroriy so'rov xavfsiz (idempotent)."""
    data = _body(request)
    if data is None:
        return _bad("Noto'g'ri so'rov")
    code = str(data.get("code") or "").strip()
    if not code:
        return _bad("QR kod bo'sh")
    force = bool(data.get("force"))
    me = display_name(request.user)
    previous = ""

    with transaction.atomic():
        item = _find_equipment(code)
        if item is None:
            return JsonResponse({"ok": False, "code": code, "error": f"«{code}» kodli texnika topilmadi"}, status=404)
        move = item.movements.filter(in_at__isnull=True).first()
        if move is None:
            return JsonResponse({
                "ok": False, "code": item.code,
                "error": f"{item.name} tadbirda emas (avval ombordan chiqarilishi kerak)",
            }, status=400)
        if move.holder_user_id == request.user.id:
            return JsonResponse({
                "ok": True, "already": True, "code": item.code, "mine": _mine(request.user),
                "message": f"{item.name} allaqachon sizga biriktirilgan",
            })
        if move.holder and not force:
            return JsonResponse({
                "ok": False, "confirm": True, "code": item.code, "name": item.name, "holder": move.holder,
                "error": f"{item.name} hozir {move.holder} ga biriktirilgan",
            })
        previous = move.holder
        # Boshqa xodim shu zahoti biriktirib qo'ygan bo'lsa, uning ustidan jim yozib yubormaymiz
        changed = Movement.objects.filter(
            pk=move.pk, in_at__isnull=True, holder=move.holder, holder_user_id=move.holder_user_id,
        ).update(holder=me, holder_user=request.user)
        if not changed:
            return JsonResponse({
                "ok": False, "code": item.code,
                "error": f"{item.name} shu zahoti o'zgartirildi, qaytadan skanerlang",
            }, status=409)

    text = f"📌 Texnika biriktirildi\n👤 {me}\n🔧 {item_label(item)}"
    if move.event:
        text += f"\n🎪 {move.event}"
    if previous:
        text += f"\n↪️ avval: {previous}"
    notify(text)
    return JsonResponse({
        "ok": True, "code": item.code, "mine": _mine(request.user),
        "message": f"{item.name} sizga biriktirildi",
    })


@login_required
@require_POST
def release_api(request):
    """Xodim o'ziga adashib biriktirilgan texnikani bo'shatadi (tadbirda qoladi, biriktirilmagan bo'ladi)."""
    data = _body(request)
    if data is None:
        return _bad("Noto'g'ri so'rov")
    codes = _codes(data)
    if not codes:
        return _bad("Texnika tanlanmadi")
    released = Movement.objects.filter(
        in_at__isnull=True, holder_user=request.user, equipment__code__in=codes,
    ).update(holder="", holder_user=None)
    return JsonResponse({
        "ok": released > 0, "released": released, "mine": _mine(request.user),
        "message": f"{released} ta texnika bo'shatildi",
        "error": "" if released else "Bu texnika sizga biriktirilmagan",
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
        notify(text, [[("📦 Tadbirda nima bor", "n:out")]])
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

    rows = regstats.region_summary(since)
    by_item = defaultdict(int)
    by_person = defaultdict(int)
    for m in Movement.objects.filter(out_at__gte=since).select_related("equipment"):
        by_item[(m.equipment.code, m.equipment.name)] += 1
        by_person[m.taken_by] += 1

    out_now = Equipment.objects.filter(status=Equipment.Status.OUT).count()
    total = Equipment.objects.count()
    top_items = sorted(by_item.items(), key=lambda kv: -kv[1])[:5]
    top_people = sorted(by_person.items(), key=lambda kv: -kv[1])[:5]
    return render(request, "inventory/dashboard.html", {
        "rows": rows,
        "periods": [(k, v[0]) for k, v in PERIODS.items()],
        "current": key,
        "period_label": PERIODS[key][0],
        "out_now": out_now,
        "total": total,
        "out_pct": round(out_now * 100 / total) if total else 0,
        "events": sum(r["events"] for r in rows),
        "places": sum(r["places"] for r in rows),
        "regions_active": sum(1 for r in rows if r["items"]),
        "top_items": [{"code": c, "name": short_name(n), "count": k} for (c, n), k in top_items],
        "top_people": [{"name": n, "count": k} for n, k in top_people],
        "now": timezone.now(),
    })


@login_required
def stats_region(request, region):
    """Bitta viloyat: qaysi joylarda, qachon, kim, qaysi texnika bilan tadbir bo'lgani."""
    if region not in Region.values:
        raise Http404
    key = request.GET.get("period", "month")
    if key not in PERIODS:
        key = "month"
    places = regstats.region_detail(timezone.now() - timedelta(days=PERIODS[key][1]), region)
    return render(request, "inventory/stats_region.html", {
        "region_label": Region.label_of(region), "places": places, "current": key,
        "period_label": PERIODS[key][0],
        "periods": [(k, v[0]) for k, v in PERIODS.items()],
        "events": sum(p["events_count"] for p in places),
        "items": sum(p["items"] for p in places),
        "place_count": sum(1 for p in places if p["name"] != regstats.NO_PLACE),
    })
