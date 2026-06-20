import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# Берём токен из переменной окружения BOT_TOKEN
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Переменная BOT_TOKEN не установлена!")

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer("Привет! Я бот-помощник по технике ФСТмедиа.")

async def main():
    # Удаляем вебхук (на случай, если был установлен)
    await bot.delete_webhook()
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
