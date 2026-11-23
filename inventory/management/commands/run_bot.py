import asyncio

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from inventory import reports


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
            return message.from_user and message.from_user.id in admins

        @dp.message(Command("start"))
        async def start(message: Message):
            if not allowed(message):
                await message.answer(f"Ruxsat yo'q. Sizning ID: {message.from_user.id}")
                return
            await message.answer("SmartStock admin bot.\n/kim — kim nima olgan\n/stat [hafta|oy|chorak|yarim|yil]")

        @dp.message(Command("kim"))
        async def kim(message: Message):
            if allowed(message):
                await message.answer(await sync_to_async(reports.who_has_what)())

        @dp.message(Command("stat"))
        async def stat(message: Message, command: CommandObject):
            if allowed(message):
                period = (command.args or "oy").strip().lower()
                await message.answer(await sync_to_async(reports.stats)(period))

        self.stdout.write("Bot ishga tushdi")
        await dp.start_polling(bot)
