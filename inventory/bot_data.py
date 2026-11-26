"""Telegram bot ekranlari: har bir funksiya (HTML matn, tugmalar) juftligini qaytaradi.

Tugmalar: qatorlar ro'yxati, har biri [(matn, callback_data), ...]. callback_data "http" bilan boshlansa, u havola tugmasi.
Bu modul Telegram kutubxonasiga bog'liq emas, shuning uchun oddiy Django testlarida tekshiriladi.
"""
import html
import math
from collections import OrderedDict
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from . import reports, security
from .access import display_name
from .fmt import short_name, where
from .version import BUILD
from .models import BlockedIP, Equipment, Movement, Region, SecurityEvent, SecurityState, Warehouse

PER_PAGE = 4       # "Tadbirda" ro'yxatida bir sahifadagi chiqarishlar soni
MAX_ITEMS = 10     # bitta chiqarishda ko'rsatiladigan texnikalar soni
MAX_HITS = 8       # qidiruv natijalari tugmalari soni
TG_LIMIT = 3900    # Telegram xabari 4096 belgidan oshmasin

STATUS_ICON = {Equipment.Status.IN_STOCK: "🟢", Equipment.Status.OUT: "🔴"}
PERIOD_BUTTONS = [("hafta", "Hafta"), ("oy", "Oy"), ("chorak", "Chorak"), ("yarim", "Yarim yil"), ("yil", "Yil")]
NOISE_KINDS = ["login_failed", "login_ok"]

esc = html.escape


# ---------- yordamchilar ----------

def clip(text, limit=TG_LIMIT):
    if len(text) <= limit:
        return text
    return text[:limit].rsplit("\n", 1)[0] + "\n…"


def when(dt):
    return timezone.localtime(dt).strftime("%d.%m %H:%M")


def ago(dt):
    mins = max(int((timezone.now() - dt).total_seconds() // 60), 0)
    days, rest = divmod(mins, 1440)
    hours, minutes = divmod(rest, 60)
    if days:
        return f"{days} kun {hours} soat"
    if hours:
        return f"{hours} soat {minutes} daq"
    return f"{minutes} daq"


def region_label(value):
    return Region.label_of(value)


def _tail(refresh):
    return [[("🔄 Yangilash", refresh), ("🏠 Menyu", "m:home")]]


def lockdown_state():
    """Bot alohida jarayon: keshga emas, bazaga qaraymiz."""
    return SecurityState.objects.filter(pk=1, lockdown=True).exists()


def _alerts_count():
    return SecurityEvent.objects.exclude(kind__in=NOISE_KINDS).filter(handled=False).count()


# ---------- bosh menyu ----------

def home_screen():
    total = Equipment.objects.count()
    out = Equipment.objects.filter(status=Equipment.Status.OUT).count()
    open_moves = Movement.objects.filter(in_at__isnull=True)
    people = open_moves.values("taken_by").distinct().count()
    unassigned = open_moves.filter(holder="").count()
    alerts = _alerts_count()

    lines = ["<b>📦 SmartStock</b> · admin", ""]
    lines.append(f"Tadbirda: <b>{out}</b> / {total} texnika")
    if out:
        lines.append(f"Mas'ullar: {people} kishi")
        if unassigned:
            lines.append(f"⚠️ Biriktirilmagan: {unassigned} ta")
    if lockdown_state():
        lines.append("🛑 <b>Lockdown yoqilgan</b>")
    elif alerts:
        lines.append(f"❗ Ko'rilmagan xavfsizlik hodisalari: {alerts} ta")
    else:
        lines.append("🛡 Xavfsizlik: tinch ✅")
    lines += ["", "Bo'limni tanlang 👇", f"<i>versiya: {BUILD}</i>"]

    sec_label = "🛡 Xavfsizlik" + (f" ({alerts})" if alerts else "")
    rows = [
        [("📦 Tadbirda", "m:out:0"), ("📊 Statistika", "m:st:oy")],
        [("🔎 Qidirish", "m:find"), ("🏭 Omborlar", "m:wh")],
        [(sec_label, "m:sec")],
    ]
    if settings.SITE_URL.startswith("http"):
        rows.append([("🌐 Saytni ochish", settings.SITE_URL)])
    rows.append([("🔄 Yangilash", "m:home")])
    return "\n".join(lines), rows


def help_screen():
    text = (
        "<b>Qanday ishlaydi</b>\n\n"
        "Hamma narsa /menu dagi tugmalar orqali. Xabar yozsangiz, bot uni <b>qidiruv</b> deb qabul qiladi: "
        "texnika kodi, nomi yoki odam ismini yozing.\n\n"
        "/menu — asosiy menyu\n"
        "/kim — tadbirda kimda nima\n"
        "/stat [hafta|oy|chorak|yarim|yil] — statistika\n"
        "/find &lt;so'z&gt; — qidirish\n"
        "/xavf — xavfsizlik\n"
        "/bloklar — bloklangan IP'lar\n"
        "/lockdown on|off — favqulodda yopish"
    )
    return text, [[("🏠 Menyu", "m:home")]]


# ---------- tadbirda ----------

def out_screen(page=0):
    moves = list(
        Movement.objects.filter(in_at__isnull=True)
        .select_related("equipment").order_by("taken_by", "region", "place", "event", "equipment__code")
    )
    if not moves:
        return "<b>📦 Tadbirda</b>\n\nHozir tadbirda texnika yo'q ✅", _tail("m:out:0")

    groups = OrderedDict()
    for m in moves:
        groups.setdefault((m.taken_by, m.region, m.place, m.event), []).append(m)
    items = list(groups.items())
    pages = max(1, math.ceil(len(items) / PER_PAGE))
    page = min(max(int(page), 0), pages - 1)

    lines = [f"<b>📦 Tadbirda</b> — {len(moves)} ta texnika, {len(items)} ta chiqarish"]
    if pages > 1:
        lines[0] += f" · {page + 1}/{pages}"
    lines.append("")
    for (person, region, place, event), rows_ in items[page * PER_PAGE:(page + 1) * PER_PAGE]:
        head = f"👤 <b>{esc(person)}</b> · {len(rows_)} ta · 📍 {esc(where(region_label(region), place))}"
        if event:
            head += f" · «{esc(event)}»"
        head += f" · ⏱ {ago(min(m.out_at for m in rows_))}"
        lines.append(head)
        for n, m in enumerate(rows_[:MAX_ITEMS], 1):
            who = esc(m.holder) if m.holder else "<i>biriktirilmagan</i>"
            lines.append(f"   {n}. {esc(short_name(m.equipment.name))} · inv. № <code>{esc(m.equipment.code)}</code> → {who}")
        if len(rows_) > MAX_ITEMS:
            lines.append(f"   … yana {len(rows_) - MAX_ITEMS} ta")
        lines.append("")

    nav = []
    if page > 0:
        nav.append(("⬅️", f"m:out:{page - 1}"))
    if pages > 1:
        nav.append((f"{page + 1}/{pages}", "m:noop"))
    if page < pages - 1:
        nav.append(("➡️", f"m:out:{page + 1}"))
    rows = ([nav] if nav else []) + _tail(f"m:out:{page}")
    return clip("\n".join(lines).strip()), rows


# ---------- statistika va omborlar ----------

def stats_screen(period="oy"):
    if period not in reports.PERIODS:
        period = "oy"
    row = [(("• " if key == period else "") + label, f"m:st:{key}") for key, label in PERIOD_BUTTONS]
    rows = [row[:3], row[3:]] + _tail(f"m:st:{period}")
    head, _, rest = reports.stats(period).partition("\n")
    return f"<b>{esc(head)}</b>\n{esc(rest)}", rows


def warehouses_screen():
    qs = Warehouse.objects.select_related("manager").annotate(
        total=Count("equipment"),
        out=Count("equipment", filter=Q(equipment__status=Equipment.Status.OUT)),
    ).order_by("name")
    lines = ["<b>🏭 Omborlar</b>", ""]
    for w in qs:
        line = f"• <b>{esc(w.name)}</b> — tadbirda {w.out} / {w.total}"
        if w.manager:
            line += f" · mas'ul: {esc(display_name(w.manager))}"
        lines.append(line)
    if len(lines) == 2:
        lines.append("Omborlar yo'q.")
    return clip("\n".join(lines)), _tail("m:wh")


# ---------- qidiruv va texnika kartasi ----------

def find_prompt():
    return (
        "<b>🔎 Qidirish</b>\n\nTexnika <b>kodi</b>, <b>nomi</b> yoki odam <b>ismini</b> yozib yuboring.",
        [[("🏠 Menyu", "m:home")]],
    )


def search_screen(query):
    q = (query or "").strip()[:60]
    if not q:
        return find_prompt()

    exact = Equipment.objects.filter(code__iexact=q).first()
    if exact:
        return equipment_card(exact.pk)

    hits = Equipment.objects.filter(Q(code__icontains=q) | Q(name__icontains=q)).order_by("code")
    total = hits.count()
    if total == 1:
        return equipment_card(hits.first().pk)
    if total:
        rows = [
            [(f"{STATUS_ICON.get(e.status, '⚪')} {short_name(e.name, 24)} · {e.code}"[:60], f"e:{e.pk}")]
            for e in hits[:MAX_HITS]
        ]
        text = f"<b>🔎 «{esc(q)}»</b> — {total} ta texnika"
        if total > MAX_HITS:
            text += f" (dastlabki {MAX_HITS} tasi)"
        return text, rows + [[("🔎 Yangi qidiruv", "m:find"), ("🏠 Menyu", "m:home")]]

    people = list(
        Movement.objects.filter(in_at__isnull=True)
        .filter(Q(taken_by__icontains=q) | Q(holder__icontains=q))
        .select_related("equipment").order_by("equipment__code")[:15]
    )
    if people:
        lines = [f"<b>🔎 «{esc(q)}»</b> — hozir tadbirdagi texnikalar", ""]
        for m in people:
            lines.append(
                f"• {esc(short_name(m.equipment.name))} · inv. № <code>{esc(m.equipment.code)}</code>\n"
                f"   olgan: {esc(m.taken_by)} → {esc(m.holder) if m.holder else '<i>biriktirilmagan</i>'}"
            )
        return clip("\n".join(lines)), [[("🔎 Yangi qidiruv", "m:find"), ("🏠 Menyu", "m:home")]]

    return f"«{esc(q)}» bo'yicha hech narsa topilmadi.", [[("🔎 Yangi qidiruv", "m:find"), ("🏠 Menyu", "m:home")]]


def equipment_card(pk):
    e = Equipment.objects.select_related("warehouse").filter(pk=pk).first()
    if e is None:
        return "Texnika topilmadi (o'chirilgan bo'lishi mumkin).", [[("🏠 Menyu", "m:home")]]

    lines = [f"<b>{esc(e.name)}</b>", f"Inventar №: <code>{esc(e.code)}</code>", f"🏭 Ombor: {esc(e.warehouse.name)}"]
    if e.manufactured_year:
        lines.append(f"📅 Ishlab chiqarilgan: {e.manufactured_year}")
    lines.append(f"Holati: {STATUS_ICON.get(e.status, '⚪')} {e.get_status_display()}")

    moves = list(e.movements.all()[:4])
    current = next((m for m in moves if m.in_at is None), None)
    if current:
        lines += ["", f"👤 Olgan: {esc(current.taken_by)}"]
        place = esc(where(region_label(current.region), current.place)) + (f" · «{esc(current.event)}»" if current.event else "")
        lines.append(f"📍 {place}")
        lines.append(f"📌 Biriktirilgan: {esc(current.holder) if current.holder else '<i>biriktirilmagan</i>'}")
        lines.append(f"⏱ Chiqqan: {when(current.out_at)} ({ago(current.out_at)} oldin)")
    history = [m for m in moves if m.in_at is not None][:3]
    if history:
        lines += ["", "<b>So'nggi harakatlar</b>"]
        for m in history:
            hours = m.work_hours
            lines.append(
                f"• {when(m.out_at)} → {when(m.in_at)} · {esc(m.taken_by)} · {esc(where(region_label(m.region), m.place))}"
                + (f" · ish: {hours.quantize(Decimal('0.1'))} soat" if hours is not None else "")
            )
    rows = [[("🔄 Yangilash", f"e:{pk}"), ("🔎 Yangi qidiruv", "m:find")], [("🏠 Menyu", "m:home")]]
    return clip("\n".join(lines)), rows


# ---------- xavfsizlik ----------

def security_screen():
    on = lockdown_state()
    events = SecurityEvent.objects.exclude(kind__in=NOISE_KINDS)[:8]
    lines = ["<b>🛡 Xavfsizlik</b>", ""]
    lines.append("Lockdown: " + ("<b>YOQILGAN 🛑</b>" if on else "o'chiq"))
    lines.append(f"Bloklangan IP'lar: {BlockedIP.objects.count()} ta")
    lines.append("")
    if events:
        lines.append("<b>So'nggi hodisalar</b>")
        for ev in events:
            mark = "✔" if ev.handled else "❗"
            lines.append(esc(f"{mark} {when(ev.created_at)} {ev.kind} {ev.ip or ''} {ev.username} {ev.detail}".strip()))
    else:
        lines.append("Xavfli hodisa yo'q ✅")

    rows = [[("🔓 Lockdown'ni o'chirish", "m:ld:off")] if on else [("🛑 Lockdown'ni yoqish", "m:ld:ask")]]
    rows.append([(f"🚫 Bloklangan IP'lar ({BlockedIP.objects.count()})", "m:bl")])
    return clip("\n".join(lines)), rows + _tail("m:sec")


def lockdown_confirm_screen():
    text = (
        "<b>🛑 Lockdown yoqilsinmi?</b>\n\n"
        "Yoqilsa, faqat superuserlar tizimda ishlay oladi, qolgan hamma xodimlarga "
        "«Tizim vaqtincha yopilgan» chiqadi."
    )
    return text, [[("✅ Ha, yoqish", "m:ld:on"), ("↩️ Bekor qilish", "m:sec")]]


def blocked_screen():
    ips = list(BlockedIP.objects.order_by("-created_at"))
    if not ips:
        return "<b>🚫 Bloklangan IP'lar</b>\n\nBloklangan IP yo'q ✅", [[("⬅️ Xavfsizlik", "m:sec"), ("🏠 Menyu", "m:home")]]
    lines = [f"<b>🚫 Bloklangan IP'lar</b> — {len(ips)} ta", ""]
    for b in ips[:30]:
        lines.append(esc(f"• {b.ip} · {when(b.created_at)}" + (f" · {b.reason}" if b.reason else "")))
    rows = [[(f"♻️ {b.ip} ni ochish", f"m:ub:{b.ip}")] for b in ips[:30]]
    return clip("\n".join(lines)), rows + [[("⬅️ Xavfsizlik", "m:sec"), ("🏠 Menyu", "m:home")]]


def set_lockdown(on):
    return security.set_lockdown(on)


def unblock(ip):
    return security.unblock_ip(ip)
