import asyncio
import html
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramAPIError, TelegramBadRequest, TelegramRetryAfter, TelegramUnauthorizedError,
)
from aiogram.filters import Command as TgCommand, CommandObject, CommandStart  # "Command" nomi Django buyrug'i sinfi bilan to'qnashadi
from aiogram.types import (
    BotCommand, BotCommandScopeChat, BotCommandScopeDefault, CallbackQuery, ErrorEvent,
    InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonCommands, Message,
)
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from inventory import bot_data, security

log = logging.getLogger(__name__)

ADMIN_COMMANDS = [
    BotCommand(command="menu", description="📋 Asosiy menyu"),
    BotCommand(command="kim", description="📦 Tadbirda kimda nima"),
    BotCommand(command="stat", description="📊 Statistika"),
    BotCommand(command="find", description="🔎 Texnika yoki odam qidirish"),
    BotCommand(command="xavf", description="🛡 Xavfsizlik"),
    BotCommand(command="bloklar", description="🚫 Bloklangan IP'lar"),
    BotCommand(command="lockdown", description="🛑 Favqulodda yopish (on/off)"),
    BotCommand(command="help", description="❓ Yordam"),
]


def db(fn, *args):
    return sync_to_async(fn)(*args)


def markup(rows):
    keyboard = []
    for row in rows:
        buttons = []
        for label, data in row:
            if data.startswith("http"):
                buttons.append(InlineKeyboardButton(text=label, url=data))
            else:
                buttons.append(InlineKeyboardButton(text=label, callback_data=data))
        keyboard.append(buttons)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def show(event, screen, toast=None):
    """Ekranni ko'rsatadi: tugma bosilsa xabar o'z joyida yangilanadi, buyruq bo'lsa yangi xabar yuboriladi."""
    text, rows = screen
    kb = markup(rows)
    if isinstance(event, CallbackQuery):
        msg = event.message
        if isinstance(msg, Message):
            try:
                await msg.edit_text(text, reply_markup=kb)
            except TelegramBadRequest as exc:
                if "message is not modified" in str(exc).lower():
                    toast = toast or "Yangilandi ✅"
                else:  # xabar juda eski yoki tahrirlab bo'lmaydi: yangisini yuboramiz
                    await event.bot.send_message(event.from_user.id, text, reply_markup=kb)
            await event.answer(toast[:190] if toast else None)
            return
        await event.answer(toast[:190] if toast else None)
        await event.bot.send_message(event.from_user.id, text, reply_markup=kb)
    else:
        await event.answer(text, reply_markup=kb)


def build_dispatcher(admins):
    admins = set(admins)
    dp = Dispatcher()
    admin, guest = Router(name="admin"), Router(name="guest")
    admin.message.filter(F.from_user.id.in_(admins))
    admin.callback_query.filter(F.from_user.id.in_(admins))

    # ---------- buyruqlar ----------

    @admin.message(CommandStart())
    async def start(message: Message):
        try:  # adminning shaxsiy chatida "Menu" tugmasi va buyruqlar ro'yxatini o'rnatadi
            await message.bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=message.chat.id))
            await message.bot.set_chat_menu_button(chat_id=message.chat.id, menu_button=MenuButtonCommands())
        except TelegramAPIError:
            log.warning("Buyruqlar menyusini o'rnatib bo'lmadi", exc_info=True)
        await show(message, await db(bot_data.home_screen))

    @admin.message(TgCommand("menu"))
    async def menu(message: Message):
        await show(message, await db(bot_data.home_screen))

    @admin.message(TgCommand("help"))
    async def help_(message: Message):
        await show(message, bot_data.help_screen())

    @admin.message(TgCommand("kim"))
    async def kim(message: Message):
        await show(message, await db(bot_data.out_screen, 0))

    @admin.message(TgCommand("stat"))
    async def stat(message: Message, command: CommandObject):
        await show(message, await db(bot_data.stats_screen, (command.args or "oy").strip().lower()))

    @admin.message(TgCommand("find"))
    async def find(message: Message, command: CommandObject):
        await show(message, await db(bot_data.search_screen, command.args or ""))

    @admin.message(TgCommand("xavf"))
    async def xavf(message: Message):
        await show(message, await db(bot_data.security_screen))

    @admin.message(TgCommand("bloklar"))
    async def bloklar(message: Message):
        await show(message, await db(bot_data.blocked_screen))

    @admin.message(TgCommand("lockdown"))
    async def lockdown(message: Message, command: CommandObject):
        arg = (command.args or "").strip().lower()
        if arg not in ("on", "off"):
            await message.answer("Foydalanish: /lockdown on yoki /lockdown off")
            return
        _, text = await db(bot_data.set_lockdown, arg == "on")
        await message.answer(html.escape(text))
        await show(message, await db(bot_data.security_screen))

    @admin.message(F.text & ~F.text.startswith("/"))
    async def free_text(message: Message):
        """Oddiy xabar — qidiruv: texnika kodi, nomi yoki odam ismi."""
        await show(message, await db(bot_data.search_screen, message.text))

    @admin.message(F.text.startswith("/"))
    async def unknown(message: Message):
        await message.answer("Bunday buyruq yo'q. /menu ni bosing.")

    # ---------- tugmalar ----------

    @admin.callback_query(F.data.startswith("m:"))
    async def on_menu(cb: CallbackQuery):
        _, action, *rest = cb.data.split(":", 2)
        arg = rest[0] if rest else ""
        toast = None
        if action == "noop":
            await cb.answer()
            return
        if action == "home":
            screen = await db(bot_data.home_screen)
        elif action == "out":
            screen = await db(bot_data.out_screen, int(arg) if arg.isdigit() else 0)
        elif action == "st":
            screen = await db(bot_data.stats_screen, arg or "oy")
        elif action == "wh":
            screen = await db(bot_data.warehouses_screen)
        elif action == "find":
            screen = bot_data.find_prompt()
        elif action == "sec":
            screen = await db(bot_data.security_screen)
        elif action == "bl":
            screen = await db(bot_data.blocked_screen)
        elif action == "ld" and arg == "ask":
            screen = bot_data.lockdown_confirm_screen()
        elif action == "ld" and arg in ("on", "off"):
            _, toast = await db(bot_data.set_lockdown, arg == "on")
            screen = await db(bot_data.security_screen)
        elif action == "ub" and arg:
            _, toast = await db(bot_data.unblock, arg)
            screen = await db(bot_data.blocked_screen)
        else:
            await cb.answer("Noma'lum amal")
            return
        await show(cb, screen, toast)

    @admin.callback_query(F.data.startswith("e:"))
    async def on_equipment(cb: CallbackQuery):
        pk = cb.data[2:]
        await show(cb, await db(bot_data.equipment_card, int(pk) if pk.isdigit() else 0))

    @admin.callback_query(F.data == "n:out")
    async def on_notification_out(cb: CallbackQuery):
        """Saytdan kelgan xabar ostidagi tugma: xabarni o'chirib yubormaslik uchun yangi xabar yuboradi."""
        await cb.answer()
        text, rows = await db(bot_data.out_screen, 0)
        await cb.bot.send_message(cb.from_user.id, text, reply_markup=markup(rows))

    @admin.callback_query(F.data.startswith("sec:"))
    async def on_security_alert(cb: CallbackQuery):
        """Xavfsizlik ogohlantirishi ostidagi tugmalar (IP bloklash, akkaunt qulflash, lockdown...)."""
        _, action, arg = cb.data.split(":", 2)
        ok, text = await db(security.handle_action, action, arg)
        await cb.answer(text[:190])
        if not isinstance(cb.message, Message):
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
                f"{html.escape(cb.message.text or '')}\n\n{html.escape(text)}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None,
            )
        except TelegramBadRequest:
            pass

    # ---------- ruxsati yo'qlar ----------

    @guest.message()
    async def deny(message: Message):
        if message.from_user:
            await message.answer(
                f"Ruxsat yo'q. Sizning ID: <code>{message.from_user.id}</code>\n"
                "Admin shu ID'ni TELEGRAM_ADMIN_IDS ga qo'shishi kerak."
            )

    @guest.callback_query()
    async def deny_cb(cb: CallbackQuery):
        await cb.answer("Ruxsat yo'q", show_alert=True)

    # ---------- xatolar ----------

    @dp.errors()
    async def on_error(event: ErrorEvent):
        log.exception("Bot xatosi", exc_info=event.exception)
        update = event.update
        try:
            if update.callback_query:
                await update.callback_query.answer("Xatolik yuz berdi. Qayta urinib ko'ring.", show_alert=True)
            elif update.message:
                await update.message.answer("⚠️ Xatolik yuz berdi. Qayta urinib ko'ring yoki /menu ni bosing.")
        except TelegramAPIError:
            pass
        return True

    dp.include_router(admin)
    dp.include_router(guest)
    return dp


async def setup_bot(bot, admins):
    """Telegramdagi "Menu" tugmasi, buyruqlar ro'yxati va bot tavsifini o'rnatadi."""
    try:
        await bot.set_my_commands([BotCommand(command="start", description="Boshlash")], scope=BotCommandScopeDefault())
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        await bot.set_my_short_description("SmartStock — ombor texnikasi nazorati")
        await bot.set_my_description(
            "SmartStock admin boti: tadbirdagi texnikalar, statistika, qidiruv va xavfsizlik ogohlantirishlari."
        )
    except TelegramAPIError:
        log.warning("Bot menyusini o'rnatib bo'lmadi", exc_info=True)
    for admin_id in admins:
        try:
            await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id))
        except TelegramAPIError:  # admin botga hali /start yozmagan bo'lsa; /start da o'rnatiladi
            log.info("Admin %s uchun buyruqlar keyin o'rnatiladi (/start dan so'ng)", admin_id)


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
        bot = Bot(
            settings.TELEGRAM_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
        )
        admins = set(settings.TELEGRAM_ADMIN_IDS)
        dp = build_dispatcher(admins)
        try:
            try:
                await bot.delete_webhook(drop_pending_updates=False)  # webhook qolib ketgan bo'lsa polling ishlamaydi
                await setup_bot(bot, admins)
            except TelegramUnauthorizedError:
                raise CommandError("Token noto'g'ri yoki bekor qilingan. @BotFather dan yangi token oling.")
            except TelegramAPIError as exc:
                self.stdout.write(f"Ogohlantirish: boshlang'ich sozlash bajarilmadi ({exc}). Bot ishlashda davom etadi.")
            self.stdout.write("Bot ishga tushdi")
            while True:
                try:
                    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
                    return
                except TelegramRetryAfter as exc:  # juda ko'p qayta ishga tushirilganda: kutib, o'zi davom etadi
                    wait = exc.retry_after + 1
                    self.stdout.write(f"Telegram cheklovi: {wait} soniya kutilmoqda...")
                    await asyncio.sleep(wait)
                except TelegramUnauthorizedError:
                    raise CommandError("Token noto'g'ri yoki bekor qilingan. @BotFather dan yangi token oling.")
        finally:
            await bot.session.close()
