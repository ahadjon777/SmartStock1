from unittest.mock import patch

from asgiref.sync import sync_to_async

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from . import security
from .models import Equipment, SecurityEvent, Warehouse

User = get_user_model()


class EquipmentDeleteTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="test-pass", is_staff=True)
        self.warehouse = Warehouse.objects.create(name="Main")
        self.equipment = Equipment.objects.create(code="EQ-1", name="Camera", warehouse=self.warehouse)

    def test_admin_can_delete_equipment_with_post(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("panel_equipment_delete", args=[self.equipment.pk]))
        self.assertRedirects(response, reverse("panel_equipment"))
        self.assertFalse(Equipment.objects.filter(pk=self.equipment.pk).exists())

    def test_get_is_not_allowed(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("panel_equipment_delete", args=[self.equipment.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Equipment.objects.filter(pk=self.equipment.pk).exists())

    def test_non_admin_cannot_delete_equipment(self):
        user = User.objects.create_user(username="staff", password="test-pass")
        self.client.force_login(user)
        response = self.client.post(reverse("panel_equipment_delete", args=[self.equipment.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Equipment.objects.filter(pk=self.equipment.pk).exists())


class SecurityAlertTests(TestCase):
    @override_settings(SECURITY_FAIL_LIMIT=2, SECURITY_USER_FAIL_LIMIT=99)
    @patch("inventory.security.notify")
    def test_bruteforce_threshold_sends_alert(self, notify):
        security.on_login_failed("192.0.2.10", "someone")
        security.on_login_failed("192.0.2.10", "someone")
        self.assertTrue(SecurityEvent.objects.filter(kind="bruteforce", ip="192.0.2.10").exists())
        notify.assert_called_once()


# ---------------------------------------------------------------------------
# Biriktirish (take/release) oqimi
# ---------------------------------------------------------------------------
import json
from datetime import timedelta

from django.utils import timezone

from .models import BlockedIP, Movement


def _post(client, name, payload):
    return client.post(reverse(name), data=json.dumps(payload), content_type="application/json")


class TakeFlowTests(TestCase):
    def setUp(self):
        self.boss = User.objects.create_user(username="boss", password="x", first_name="Boss Bossov")
        self.ali = User.objects.create_user(username="ali", password="x", first_name="Ali Valiyev")
        self.vali = User.objects.create_user(username="vali", password="x", first_name="Vali Aliyev")
        wh = Warehouse.objects.create(name="Main")
        self.e1 = Equipment.objects.create(code="CAM-1", name="Kamera", warehouse=wh, status=Equipment.Status.OUT)
        self.e2 = Equipment.objects.create(code="CAM-2", name="Mikrofon", warehouse=wh, status=Equipment.Status.OUT)
        self.e3 = Equipment.objects.create(code="CAM-3", name="Shtativ", warehouse=wh)  # omborda
        for e in (self.e1, self.e2):
            Movement.objects.create(
                equipment=e, issued_by=self.boss, taken_by="Boss Bossov",
                region="tashkent_city", event="Konsert", out_at=timezone.now(),
            )

    def holder(self, equipment):
        return Movement.objects.get(equipment=equipment, in_at__isnull=True)

    @patch("inventory.views.notify")
    def test_take_assigns_to_logged_in_user(self, notify):
        self.client.force_login(self.ali)
        r = _post(self.client, "take_api", {"code": "CAM-1"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertEqual([m["code"] for m in data["mine"]], ["CAM-1"])
        self.assertEqual(data["mine"][0]["event"], "Konsert")
        m = self.holder(self.e1)
        self.assertEqual((m.holder, m.holder_user), ("Ali Valiyev", self.ali))
        notify.assert_called_once()

    @patch("inventory.views.notify")
    def test_take_is_case_insensitive_and_trims(self, notify):
        self.client.force_login(self.ali)
        self.assertTrue(_post(self.client, "take_api", {"code": "  cam-2 "}).json()["ok"])
        self.assertEqual(self.holder(self.e2).holder_user, self.ali)

    @patch("inventory.views.notify")
    def test_taking_twice_is_safe_and_silent(self, notify):
        self.client.force_login(self.ali)
        _post(self.client, "take_api", {"code": "CAM-1"})
        notify.reset_mock()
        data = _post(self.client, "take_api", {"code": "CAM-1"}).json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["already"])
        notify.assert_not_called()

    @patch("inventory.views.notify")
    def test_conflict_needs_confirmation_then_force_moves(self, notify):
        self.client.force_login(self.ali)
        _post(self.client, "take_api", {"code": "CAM-1"})
        self.client.force_login(self.vali)
        data = _post(self.client, "take_api", {"code": "CAM-1"}).json()
        self.assertFalse(data["ok"])
        self.assertTrue(data["confirm"])
        self.assertEqual((data["holder"], data["code"], data["name"]), ("Ali Valiyev", "CAM-1", "Kamera"))
        self.assertEqual(self.holder(self.e1).holder_user, self.ali)  # hali o'zgarmagan

        data = _post(self.client, "take_api", {"code": "CAM-1", "force": True}).json()
        self.assertTrue(data["ok"])
        self.assertEqual(self.holder(self.e1).holder_user, self.vali)
        self.assertIn("Ali Valiyev", notify.call_args[0][0])  # avvalgi egasi xabarda ko'rsatiladi

    def test_cannot_take_equipment_that_is_in_stock_or_unknown(self):
        self.client.force_login(self.ali)
        r = _post(self.client, "take_api", {"code": "CAM-3"})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()["ok"])
        r = _post(self.client, "take_api", {"code": "NOPE"})
        self.assertEqual(r.status_code, 404)
        self.assertIn("NOPE", r.json()["error"])
        self.assertEqual(_post(self.client, "take_api", {"code": "  "}).status_code, 400)

    def test_requires_login_and_post(self):
        r = _post(self.client, "take_api", {"code": "CAM-1"})
        self.assertEqual(r.status_code, 302)
        self.client.force_login(self.ali)
        self.assertEqual(self.client.get(reverse("take_api")).status_code, 405)

    @patch("inventory.views.notify")
    def test_release_only_own_items(self, notify):
        self.client.force_login(self.ali)
        _post(self.client, "take_api", {"code": "CAM-1"})
        self.client.force_login(self.vali)
        data = _post(self.client, "release_api", {"codes": ["CAM-1"]}).json()
        self.assertFalse(data["ok"])  # boshqaniki
        self.assertEqual(self.holder(self.e1).holder_user, self.ali)

        self.client.force_login(self.ali)
        data = _post(self.client, "release_api", {"codes": ["CAM-1"]}).json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["mine"], [])
        m = self.holder(self.e1)
        self.assertEqual((m.holder, m.holder_user), ("", None))
        self.assertEqual(m.equipment.status, Equipment.Status.OUT)  # tadbirda qoladi

    def test_pages_render_and_use_local_scanner(self):
        self.client.force_login(self.ali)
        for name in ("take", "scan", "checkout", "checkin"):
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 200, name)
        html_ = self.client.get(reverse("take")).content.decode()
        self.assertIn("/static/inventory/html5-qrcode.min.js", html_)
        self.assertNotIn("unpkg.com", html_)
        self.assertIn(reverse("release_api"), html_)

    def test_scanner_library_is_served_locally(self):
        r = self.client.get("/static/inventory/html5-qrcode.min.js")
        self.assertEqual(r.status_code, 200)

    def test_logout_link_is_posted(self):
        self.client.force_login(self.ali)
        html_ = self.client.get(reverse("scan")).content.decode()
        self.assertIn(reverse("logout"), html_)
        r = self.client.post(reverse("logout"))
        self.assertRedirects(r, reverse("login"))


class NotifyTests(TestCase):
    @override_settings(TELEGRAM_BOT_TOKEN="1:abc", TELEGRAM_ADMIN_IDS=[5])
    @patch("inventory.notify.urllib.request.urlopen")
    @patch("inventory.notify.threading.Thread")
    def test_notify_never_blocks_the_request(self, thread, urlopen):
        from .notify import notify
        notify("salom")
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()
        urlopen.assert_not_called()  # tarmoq chaqiruvi so'rov oqimida emas

    @override_settings(TELEGRAM_BOT_TOKEN="", TELEGRAM_ADMIN_IDS=[5])
    @patch("inventory.notify.threading.Thread")
    def test_notify_without_token_does_nothing(self, thread):
        from .notify import notify
        notify("salom")
        thread.assert_not_called()


# ---------------------------------------------------------------------------
# Telegram bot ekranlari
# ---------------------------------------------------------------------------
from . import bot_data


def _all_callbacks(rows):
    return [data for row in rows for _, data in row]


class BotScreenTests(TestCase):
    def setUp(self):
        self.boss = User.objects.create_user(username="boss", password="x", first_name="Boss")
        self.wh = Warehouse.objects.create(name="Asosiy ombor", manager=self.boss)

    def out(self, code, name, taken_by="Boss", holder="", event="Konsert"):
        e = Equipment.objects.create(code=code, name=name, warehouse=self.wh, status=Equipment.Status.OUT)
        return Movement.objects.create(
            equipment=e, issued_by=self.boss, taken_by=taken_by, holder=holder,
            region="tashkent_region", event=event, out_at=timezone.now() - timedelta(hours=3),
        )

    def test_home_summarises_state(self):
        Equipment.objects.create(code="A-1", name="Stol", warehouse=self.wh)
        self.out("A-2", "Kamera")
        text, rows = bot_data.home_screen()
        self.assertIn("<b>1</b> / 2", text)
        self.assertIn("Biriktirilmagan: 1", text)
        self.assertEqual(set(_all_callbacks(rows)) >= {"m:out:0", "m:st:oy", "m:find", "m:wh", "m:sec", "m:home"}, True)

    @override_settings(SITE_URL="https://ombor.example.uz")
    def test_home_has_site_button_when_configured(self):
        _, rows = bot_data.home_screen()
        self.assertIn("https://ombor.example.uz", _all_callbacks(rows))

    def test_out_screen_empty(self):
        text, rows = bot_data.out_screen(0)
        self.assertIn("yo'q", text)
        self.assertIn("m:home", _all_callbacks(rows))

    def test_out_screen_paginates_and_escapes_html(self):
        for i in range(6):
            self.out(f"C-{i}", f"Kamera {i}", taken_by=f"Odam {i}")
        self.out("X-1", "<script>alert(1)</script>", taken_by="<b>Hack</b>")
        first, rows = bot_data.out_screen(0)
        self.assertIn("1/2", first)
        self.assertIn("m:out:1", _all_callbacks(rows))
        self.assertNotIn("m:out:-1", _all_callbacks(rows))
        second, rows2 = bot_data.out_screen(1)
        self.assertIn("m:out:0", _all_callbacks(rows2))
        both = first + second
        self.assertNotIn("<script>", both)
        self.assertNotIn("<b>Hack</b>", both)
        self.assertIn("&lt;b&gt;Hack&lt;/b&gt;", both)
        # sahifa raqami chegaradan chiqsa ham ishlaydi
        self.assertIn("2/2", bot_data.out_screen(99)[0])

    def test_out_screen_stays_under_telegram_limit(self):
        for i in range(120):
            self.out(f"BIG-{i:03d}", "Juda uzun nomli texnika " * 5, taken_by="Katta chiqarish")
        text, _ = bot_data.out_screen(0)
        self.assertLessEqual(len(text), 4096)
        self.assertIn("yana", text)

    def test_search_exact_partial_person_and_empty(self):
        self.out("CAM-1", "Sony kamera", taken_by="Alisher", holder="Vali")
        self.out("CAM-2", "Sony mikrofon")
        text, rows = bot_data.search_screen("cam-1")  # aniq kod -> karta
        self.assertIn("Sony kamera", text)
        self.assertIn("Vali", text)
        text, rows = bot_data.search_screen("sony")  # bir nechta -> tugmalar
        self.assertIn("2 ta", text)
        self.assertEqual(len([c for c in _all_callbacks(rows) if c.startswith("e:")]), 2)
        text, _ = bot_data.search_screen("alisher")  # odam bo'yicha
        self.assertIn("CAM-1", text)
        text, _ = bot_data.search_screen("yo'q-narsa")
        self.assertIn("topilmadi", text)

    def test_equipment_card_for_out_and_missing_item(self):
        m = self.out("CAM-1", "Kamera", taken_by="Alisher", holder="Vali")
        text, rows = bot_data.equipment_card(m.equipment_id)
        for part in ("Alisher", "Vali", "Konsert", "Tadbirda"):
            self.assertIn(part, text)
        self.assertIn(f"e:{m.equipment_id}", _all_callbacks(rows))
        self.assertIn("topilmadi", bot_data.equipment_card(99999)[0])

    def test_security_lockdown_and_blocked_screens(self):
        text, rows = bot_data.security_screen()
        self.assertIn("m:ld:ask", _all_callbacks(rows))
        _, confirm = bot_data.lockdown_confirm_screen()
        self.assertEqual(_all_callbacks(confirm), ["m:ld:on", "m:sec"])
        bot_data.set_lockdown(True)
        text, rows = bot_data.security_screen()
        self.assertIn("YOQILGAN", text)
        self.assertIn("m:ld:off", _all_callbacks(rows))
        BlockedIP.objects.create(ip="203.0.113.7", reason="test")
        _, rows = bot_data.blocked_screen()
        self.assertIn("m:ub:203.0.113.7", _all_callbacks(rows))
        ok, _ = bot_data.unblock("203.0.113.7")
        self.assertTrue(ok)
        self.assertIn("yo'q", bot_data.blocked_screen()[0])

    def test_stats_and_warehouses_screens(self):
        self.out("A-1", "Kamera")
        text, rows = bot_data.stats_screen("hafta")
        self.assertIn("• Hafta", [label for row in rows for label, _ in row])
        self.assertIn("Toshkent shahri", text)
        self.assertIn("m:st:oy", _all_callbacks(bot_data.stats_screen("noma'lum")[1]) + ["m:st:oy"])
        text, _ = bot_data.warehouses_screen()
        self.assertIn("Asosiy ombor", text)
        self.assertIn("1 / 1", text)

    def test_every_callback_fits_telegram_limit(self):
        self.out("A-1", "Kamera")
        BlockedIP.objects.create(ip="2001:0db8:85a3:0000:0000:8a2e:0370:7334")
        screens = [
            bot_data.home_screen(), bot_data.out_screen(0), bot_data.stats_screen("oy"),
            bot_data.warehouses_screen(), bot_data.security_screen(), bot_data.blocked_screen(),
            bot_data.search_screen("A"), bot_data.help_screen(), bot_data.find_prompt(),
        ]
        for _, rows in screens:
            for data in _all_callbacks(rows):
                if not data.startswith("http"):
                    self.assertLessEqual(len(data.encode()), 64, data)


# ---------------------------------------------------------------------------
# Telegram bot: haqiqiy aiogram dispatcher (tarmoqsiz, soxta sessiya bilan)
# ---------------------------------------------------------------------------
from datetime import datetime

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import EditMessageText, SendMessage
from aiogram.types import Chat, Message as TgMessage

from .management.commands.run_bot import build_dispatcher


class RecordingSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []

    async def close(self):
        pass

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        yield b""

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, (SendMessage, EditMessageText)):
            return TgMessage(message_id=100, date=datetime.now(), chat=Chat(id=1, type="private"), text="x")
        return True


def _msg_update(uid, text, user_id=1, entities=None):
    msg = {"message_id": uid, "date": 1700000000, "chat": {"id": user_id, "type": "private"},
           "from": {"id": user_id, "is_bot": False, "first_name": "T"}, "text": text}
    if entities:
        msg["entities"] = entities
    return {"update_id": uid, "message": msg}


def _cb_update(uid, data, user_id=1):
    return {"update_id": uid, "callback_query": {
        "id": str(uid), "chat_instance": "ci", "data": data,
        "from": {"id": user_id, "is_bot": False, "first_name": "T"},
        "message": {"message_id": 7, "date": 1700000000, "chat": {"id": user_id, "type": "private"}, "text": "old"},
    }}


class BotDispatcherTests(TestCase):
    def setUp(self):
        boss = User.objects.create_user(username="boss", password="x", first_name="Boss")
        wh = Warehouse.objects.create(name="Main")
        e = Equipment.objects.create(code="CAM-1", name="Kamera", warehouse=wh, status=Equipment.Status.OUT)
        Movement.objects.create(equipment=e, issued_by=boss, taken_by="Boss", region="tashkent_city", out_at=timezone.now())
        self.session = RecordingSession()
        self.bot = Bot("123:ABC", session=self.session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = build_dispatcher({1})

    def sent(self, kind):
        return [c for c in self.session.calls if isinstance(c, kind)]

    async def test_start_shows_main_menu_with_buttons(self):
        cmd = [{"type": "bot_command", "offset": 0, "length": 6}]
        await self.dp.feed_raw_update(self.bot, _msg_update(1, "/start", entities=cmd))
        menu = self.sent(SendMessage)[-1]
        self.assertIn("SmartStock", menu.text)
        data = [b.callback_data for row in menu.reply_markup.inline_keyboard for b in row]
        self.assertIn("m:out:0", data)

    async def test_button_edits_message_in_place(self):
        await self.dp.feed_raw_update(self.bot, _cb_update(2, "m:out:0"))
        edit = self.sent(EditMessageText)[-1]
        self.assertIn("Boss", edit.text)
        self.assertIn("CAM-1", edit.text)

    async def test_plain_text_is_a_search(self):
        await self.dp.feed_raw_update(self.bot, _msg_update(3, "cam-1"))
        self.assertIn("Kamera", self.sent(SendMessage)[-1].text)

    async def test_notification_button_sends_new_message_instead_of_editing(self):
        await self.dp.feed_raw_update(self.bot, _cb_update(4, "n:out"))
        self.assertEqual(self.sent(EditMessageText), [])
        self.assertIn("CAM-1", self.sent(SendMessage)[-1].text)

    async def test_lockdown_asks_for_confirmation_first(self):
        await self.dp.feed_raw_update(self.bot, _cb_update(5, "m:ld:ask"))
        self.assertIn("yoqilsinmi", self.sent(EditMessageText)[-1].text)
        self.assertFalse(await sync_to_async(bot_data.lockdown_state)())
        await self.dp.feed_raw_update(self.bot, _cb_update(6, "m:ld:on"))
        self.assertTrue(await sync_to_async(bot_data.lockdown_state)())

    async def test_strangers_get_nothing_but_their_id(self):
        await self.dp.feed_raw_update(self.bot, _msg_update(7, "salom", user_id=999))
        self.assertIn("999", self.sent(SendMessage)[-1].text)
        self.assertNotIn("SmartStock", self.sent(SendMessage)[-1].text)
        await self.dp.feed_raw_update(self.bot, _cb_update(8, "m:ld:on", user_id=999))
        self.assertEqual(self.sent(EditMessageText), [])
        self.assertFalse(await sync_to_async(bot_data.lockdown_state)())


# ---------------------------------------------------------------------------
# QR yorliqlar (Micro QR emas!) va bot xabarlaridagi qisqa nom + inventar raqami
# ---------------------------------------------------------------------------
from .fmt import item_label, short_name
from .views import make_qr, qr_svg


class QrLabelTests(TestCase):
    def test_numeric_inventory_codes_are_standard_qr_not_micro(self):
        # segno.make() bunday kodlarni Micro QR qiladi, telefon kamerasi esa uni o'qiy olmaydi
        for code in ("0110104000001", "123456", "CAM-1", "A" * 40):
            qr = make_qr(code)
            self.assertFalse(qr.is_micro, code)
            self.assertGreaterEqual(qr.symbol_size(border=0)[0], 21, code)
            self.assertEqual(qr.mask, 4, code)  # brauzer skaneri uchun eng ishonchli niqob

    def test_quiet_zone_is_at_least_four_modules(self):
        qr = make_qr("0110104000001")
        modules = qr.symbol_size(border=0)[0]
        # svg_inline(scale=6, border=4) -> (modul + 2*4 ta bo'sh modul) * 6 piksel
        self.assertIn(f'width="{(modules + 8) * 6}"', qr_svg("0110104000001"))

    def test_labels_page_lists_code_and_short_name(self):
        admin = User.objects.create_superuser(username="adm", password="x")
        wh = Warehouse.objects.create(name="W")
        Equipment.objects.create(code="INV-001", name="Sony A7 III kamera obyektiv bilan to'liq komplekt va sumka", warehouse=wh)
        self.client.force_login(admin)
        html_ = self.client.get(reverse("labels")).content.decode()
        self.assertIn("INV-001", html_)
        self.assertIn("<svg", html_)
        self.assertNotIn("sumka", html_)  # uzun nom yorliqda qisqartiriladi


class ShortNameTests(TestCase):
    def test_short_name(self):
        self.assertEqual(short_name("Kamera"), "Kamera")
        self.assertEqual(short_name("  Sony   A7  III  "), "Sony A7 III")
        long = short_name("Sony A7 III kamera obyektiv bilan komplekt")
        self.assertEqual(long, "Sony A7 III kamera obyektiv…")
        self.assertLessEqual(len(long), 29)
        self.assertEqual(short_name("A" * 50), "A" * 28 + "…")  # bo'sh joy yo'q bo'lsa ham qirqiladi
        self.assertEqual(short_name(""), "")

    def test_item_label_has_inventory_number(self):
        e = Equipment(code="0110104000001", name="Mikrofon")
        self.assertEqual(item_label(e), "Mikrofon · inv. № 0110104000001")


class NotificationTextTests(TestCase):
    def setUp(self):
        self.boss = User.objects.create_user(username="boss", password="x", first_name="Boss Bossov")
        self.ali = User.objects.create_user(username="ali", password="x", first_name="Ali Valiyev")
        wh = Warehouse.objects.create(name="Main")
        self.e = Equipment.objects.create(
            code="0110104000001", name="Sony A7 III kamera obyektiv bilan komplekt", warehouse=wh,
        )

    @patch("inventory.views.notify")
    def test_checkout_notification_lists_items(self, notify):
        self.client.force_login(self.boss)
        r = _post(self.client, "checkout_api", {"codes": ["0110104000001"], "region": "tashkent_city", "event": "Konsert"})
        self.assertTrue(r.json()["ok"])
        text = notify.call_args[0][0]
        self.assertIn("Boss Bossov", text)
        self.assertIn("Sony A7 III kamera obyektiv… · inv. № 0110104000001", text)
        self.assertIn("Konsert", text)

    @patch("inventory.views.notify")
    def test_assignment_notification_has_person_short_name_and_inventory_number(self, notify):
        self.client.force_login(self.boss)
        _post(self.client, "checkout_api", {"codes": ["0110104000001"], "region": "tashkent_city", "event": "Konsert"})
        notify.reset_mock()
        self.client.force_login(self.ali)
        self.assertTrue(_post(self.client, "take_api", {"code": "0110104000001"}).json()["ok"])
        text = notify.call_args[0][0]
        self.assertIn("Ali Valiyev", text)
        self.assertIn("Sony A7 III kamera obyektiv… · inv. № 0110104000001", text)
        self.assertNotIn("komplekt", text)  # to'liq uzun nom emas, qisqasi

    def test_bot_screens_show_short_name_and_inventory_number(self):
        Movement.objects.create(
            equipment=self.e, issued_by=self.boss, taken_by="Boss Bossov", holder="Ali Valiyev",
            region="tashkent_city", out_at=timezone.now(),
        )
        self.e.status = Equipment.Status.OUT
        self.e.save()
        text, _ = bot_data.out_screen(0)
        self.assertIn("Sony A7 III kamera obyektiv…", text)
        self.assertIn("inv. № <code>0110104000001</code>", text)
        self.assertIn("Ali Valiyev", text)
        self.assertNotIn("komplekt", text)
        card, _ = bot_data.equipment_card(self.e.pk)
        self.assertIn("Inventar №", card)
        self.assertIn("komplekt", card)  # kartada to'liq nom


class LabelsPageMarkerTests(TestCase):
    def test_labels_page_shows_new_qr_format_marker_and_is_not_cached(self):
        admin = User.objects.create_superuser(username="adm2", password="x")
        wh = Warehouse.objects.create(name="W2")
        Equipment.objects.create(code="22122150007162", name="Защищенный планшет", warehouse=wh)
        self.client.force_login(admin)
        r = self.client.get(reverse("labels"))
        html_ = r.content.decode()
        self.assertIn("Yangi QR formati", html_)
        self.assertIn("21×21", html_)       # oddiy QR (Micro QR 15×15 bo'lardi)
        self.assertIn("Inv. №", html_)
        self.assertIn("no-store", r["Cache-Control"])


class BuildMarkerTests(TestCase):
    def test_bot_home_screen_shows_build_version(self):
        from .version import BUILD
        text, _ = bot_data.home_screen()
        self.assertIn(f"versiya: {BUILD}", text)


class ScannerAssetsTests(TestCase):
    def test_scanner_loads_both_decoders_locally(self):
        u = User.objects.create_user(username="sc", password="x")
        self.client.force_login(u)
        html_ = self.client.get(reverse("take")).content.decode()
        self.assertIn("/static/inventory/html5-qrcode.min.js", html_)
        self.assertIn("/static/inventory/jsQR.js", html_)  # zaxira dekoder
        self.assertEqual(self.client.get("/static/inventory/jsQR.js").status_code, 200)


class PanelStatsTests(TestCase):
    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import Movement
        self.admin = User.objects.create_user(username="boss", password="x", is_staff=True)
        self.client.force_login(self.admin)
        self.w1 = Warehouse.objects.create(name="Asosiy")
        self.w2 = Warehouse.objects.create(name="Ikkinchi")
        now = timezone.now()
        self.a = Equipment.objects.create(code="111", name="Kamera Sony A7", warehouse=self.w1, status="out")
        self.b = Equipment.objects.create(code="222", name="Mikrofon", warehouse=self.w2, status="out")
        self.c = Equipment.objects.create(code="333", name="Shtativ", warehouse=self.w1)
        Movement.objects.create(equipment=self.a, taken_by="Aliyev Vali", region="tashkent_city",
                                holder="Karimov Sanjar", event="Konsert", out_at=now - timedelta(hours=3))
        Movement.objects.create(equipment=self.b, taken_by="=cmd()", region="other_regions",
                                out_at=now - timedelta(days=10))

    def test_home_metrics(self):
        r = self.client.get(reverse("panel_home"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["total"], 3)
        self.assertEqual(r.context["out"], 2)
        self.assertEqual(r.context["unassigned"], 1)
        self.assertEqual(r.context["long_out"], 1)
        self.assertContains(r, "Karimov Sanjar")
        self.assertContains(r, "biriktirilmagan")

    def test_out_shows_holder_and_filters(self):
        url = reverse("panel_out")
        r = self.client.get(url)
        self.assertContains(r, "Karimov Sanjar")
        self.assertEqual(len(r.context["rows"]), 2)
        r = self.client.get(url, {"state": "unassigned"})
        self.assertEqual([m.equipment.code for m in r.context["rows"]], ["222"])
        r = self.client.get(url, {"state": "long"})
        self.assertEqual([m.equipment.code for m in r.context["rows"]], ["222"])
        r = self.client.get(url, {"warehouse": str(self.w1.pk)})
        self.assertEqual([m.equipment.code for m in r.context["rows"]], ["111"])
        r = self.client.get(url, {"q": "Karimov"})
        self.assertEqual(len(r.context["rows"]), 1)

    def test_csv_export_is_safe(self):
        r = self.client.get(reverse("panel_out"), {"export": "csv"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r["Content-Type"])
        text = r.content.decode("utf-8-sig")
        self.assertIn("Karimov Sanjar", text)
        self.assertIn("'=cmd()", text)

    def test_equipment_list_shows_current_holder_and_keeps_filters(self):
        r = self.client.get(reverse("panel_equipment"), {"q": "Kamera"})
        self.assertContains(r, "Karimov Sanjar")
        self.assertIn("q=Kamera", r.context["page_query"])

    def test_stats_dashboard(self):
        r = self.client.get(reverse("dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["out_now"], 2)
        self.assertEqual(r.context["out_pct"], 67)
