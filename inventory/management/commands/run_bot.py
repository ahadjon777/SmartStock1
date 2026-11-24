import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramRetryAfter, TelegramUnauthorizedError
from aiogram.filters import Command as TgCommand, CommandObject  # "Command" nomi Django buyrug'i sinfi bilan to'qnashadi
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from inventory import reports, security
from inventory.models import BlockedIP


def build_dispatcher(admins):
    dp = Dispatcher()

    def allowed(message: Message) -> bool:
        return bool(message.from_user and message.from_user.id in admins)

    @dp.message(TgCommand("start"))
    async def start(message: Message):
        if not allowed(message):
            await message.answer(f"Ruxsat yo'q. Sizning ID: {message.from_user.id}")
            return
        await message.answer(
            "SmartStock admin bot.\n"
            "/kim — kim nima olgan\n/stat [hafta|oy|chorak|yarim|yil]\n"
            "/xavf — so'nggi xavfsizlik hodisalari\n/bloklar — bloklangan IP'lar\n"
            "/lockdown on|off — favqulodda yopish"
        )

    @dp.message(TgCommand("kim"))
    async def kim(message: Message):
        if allowed(message):
            await message.answer(await sync_to_async(reports.who_has_what)())

    @dp.message(TgCommand("stat"))
    async def stat(message: Message, command: CommandObject):
        if allowed(message):
            period = (command.args or "oy").strip().lower()
            await message.answer(await sync_to_async(reports.stats)(period))

    @dp.message(TgCommand("xavf"))
    async def xavf(message: Message):
        if allowed(message):
            await message.answer(await sync_to_async(security.recent_events_text)())

    @dp.message(TgCommand("bloklar"))
    async def bloklar(message: Message):
        if not allowed(message):
            return
        ips = await sync_to_async(lambda: list(BlockedIP.objects.values_list("ip", flat=True)))()
        if not ips:
            await message.answer("Bloklangan IP yo'q.")
            return
        rows = [[InlineKeyboardButton(text=f"♻️ {ip} ni ochish", callback_data=f"sec:ub:{ip}")] for ip in ips[:30]]
        await message.answer("Bloklangan IP'lar:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    @dp.message(TgCommand("lockdown"))
    async def lockdown(message: Message, command: CommandObject):
        if not allowed(message):
            return
        arg = (command.args or "").strip().lower()
        if arg not in ("on", "off"):
            await message.answer("Foydalanish: /lockdown on yoki /lockdown off")
            return
        _, text = await sync_to_async(security.set_lockdown)(arg == "on")
        await message.answer(text)

    @dp.callback_query(F.data.startswith("sec:"))
    async def sec(cb: CallbackQuery):
        if cb.from_user.id not in admins:
            await cb.answer("Ruxsat yo'q", show_alert=True)
            return
        _, action, arg = cb.data.split(":", 2)
        ok, text = await sync_to_async(security.handle_action)(action, arg)
        await cb.answer(text[:190])
        if not cb.message:
            return
        rows = []
        for row in (cb.message.reply_markup.inline_keyboard if cb.message.reply_markup else []):
            kept = [b for b in row if not (ok and b.callback_data == cb.data)]
            if kept:
                rows.append(kept)
        if ok and action == "ldon":
            rows.append([InlineKeyboardButton(text="🔓 Lockdown'ni o'chirish", callback_data="sec:ldoff:0")])
        try:
            await cb.message.edit_text(
                f"{cb.message.text or ''}\n\n{text}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None,
            )
        except Exception:
            pass

    return dp


class Command(BaseCommand):
    help = "Telegram admin botni ishga tushiradi (TELEGRAM_BOT_TOKEN va TELEGRAM_ADMIN_IDS kerak)"

    def handle(self, *args, **opts):
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError("TELEGRAM_BOT_TOKEN topilmadi. .env faylida TELEGRAM_BOT_TOKEN=... deb yozing.")
        if not settings.TELEGRAM_ADMIN_IDS:
            self.stdout.write("Eslatma: TELEGRAM_ADMIN_IDS bo'sh. Bot faqat /start da ID'ingizni ko'rsatadi.")
        try:
            asyncio.run(self.main())
        except KeyboardInterrupt:
            self.stdout.write("Bot to'xtatildi")

    async def main(self):
        bot = Bot(settings.TELEGRAM_BOT_TOKEN)
        dp = build_dispatcher(set(settings.TELEGRAM_ADMIN_IDS))
        self.stdout.write("Bot ishga tushdi")
        while True:
            try:
                await dp.start_polling(bot)
                return
            except TelegramRetryAfter as exc:  # juda ko'p qayta ishga tushirilganda: kutib, o'zi davom etadi
                wait = exc.retry_after + 1
                self.stdout.write(f"Telegram cheklovi: {wait} soniya kutilmoqda...")
                await asyncio.sleep(wait)
            except TelegramUnauthorizedError:
                raise CommandError("Token noto'g'ri yoki bekor qilingan. @BotFather dan yangi token oling.")
