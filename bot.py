import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

TOKEN = "8172794803:AAEueavNtGKaNEf8QcraIYd0yPqOGCzREEg"

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer("Привет! Я бот-помощник по технике ФСТмедиа.")

async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())