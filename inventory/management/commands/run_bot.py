import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from inventory import reports, security
from inventory.models import BlockedIP


class Command(BaseCommand):
    help = "Telegram admin botni ishga tushiradi (TELEGRAM_BOT_TOKEN va TELEGRAM_ADMIN_IDS kerak)"

    def handle(self, *args, **opts):
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError("TELEGRAM_BOT_TOKEN o'rnatilmagan")
        asyncio.run(self.main())

    async def main(self):
        bot = Bot(settings.TELEGRAM_BOT_TOKEN)
        dp = Dispatcher()
        admins = set(settings.TELEGRAM_ADMIN_IDS)

        def allowed(message: Message) -> bool:
            return bool(message.from_user and message.from_user.id in admins)

        @dp.message(Command("start"))
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

        @dp.message(Command("kim"))
        async def kim(message: Message):
            if allowed(message):
                await message.answer(await sync_to_async(reports.who_has_what)())

        @dp.message(Command("stat"))
        async def stat(message: Message, command: CommandObject):
            if allowed(message):
                period = (command.args or "oy").strip().lower()
                await message.answer(await sync_to_async(reports.stats)(period))

        @dp.message(Command("xavf"))
        async def xavf(message: Message):
            if allowed(message):
                await message.answer(await sync_to_async(security.recent_events_text)())

        @dp.message(Command("bloklar"))
        async def bloklar(message: Message):
            if not allowed(message):
                return
            ips = await sync_to_async(lambda: list(BlockedIP.objects.values_list("ip", flat=True)))()
            if not ips:
                await message.answer("Bloklangan IP yo'q.")
                return
            rows = [[InlineKeyboardButton(text=f"♻️ {ip} ni ochish", callback_data=f"sec:ub:{ip}")] for ip in ips[:30]]
            await message.answer("Bloklangan IP'lar:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

        @dp.message(Command("lockdown"))
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

        self.stdout.write("Bot ishga tushdi")
        await dp.start_polling(bot)
