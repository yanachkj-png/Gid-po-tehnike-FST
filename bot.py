import asyncio
import os
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Переменная BOT_TOKEN не установлена!")

bot = Bot(token=TOKEN)
dp = Dispatcher()

user_last_msg = {}
spam_lock = asyncio.Lock()
SPAM_INTERVAL = 2.0

class Navigation(StatesGroup):
    main = State()
    kit = State()
    radio_menu = State()
    radio_use_prompt = State()
    radio_use = State()
    radio_where = State()
    radio_complete = State()
    camera_menu = State()
    camera_complete = State()
    camera_sd = State()
    camera_sd_tip = State()
    camera_battery = State()
    camera_tripod = State()

def main_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="Съёмочный комплект ФСТмедиа", callback_data="kit")
    builder.button(text="Радиосистемы", callback_data="radio")
    builder.button(text="Камеры", callback_data="camera")
    builder.adjust(1)
    return builder.as_markup()

def back_to_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

def nav_kb(has_back, has_next, extra_buttons=None, menu_callback=None):
    builder = InlineKeyboardBuilder()
    row = []
    if has_back:
        row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="nav_back"))
    if has_next:
        row.append(InlineKeyboardButton(text="Далее ➡️", callback_data="nav_next"))
    if row:
        builder.row(*row)
    if extra_buttons:
        for text, cb in extra_buttons:
            builder.button(text=text, callback_data=cb)
    if menu_callback:
        builder.button(text="В меню раздела", callback_data=menu_callback)
    builder.button(text="🔙 К разделам", callback_data="main_menu")
    builder.adjust(2, 1, 1, 1)
    return builder.as_markup()

async def send_step_message(target, text, file_ids, kb):
    if not file_ids:
        msg = await target.answer(text, reply_markup=kb, parse_mode="Markdown")
        return [msg.message_id]
    elif len(file_ids) == 1:
        msg = await target.answer_photo(photo=file_ids[0], caption=text, reply_markup=kb, parse_mode="Markdown")
        return [msg.message_id]
    else:
        text_msg = await target.answer(text, reply_markup=kb, parse_mode="Markdown")
        media = [InputMediaPhoto(media=fid) for fid in file_ids]
        album_msgs = await target.answer_media_group(media=media)
        ids = [text_msg.message_id] + [m.message_id for m in album_msgs]
        return ids

async def clear_and_go(state: FSMContext, chat_id: int, extra_id: int = None):
    data = await state.get_data()
    mids = data.get("message_ids", [])
    if extra_id and extra_id not in mids:
        mids.append(extra_id)
    for mid in mids:
        try:
            await bot.delete_message(chat_id, mid)
        except Exception:
            pass
    await state.update_data(message_ids=[])
    await asyncio.sleep(0.2)

kit_steps = [
    ("Как должен выглядеть комплект для репортажной съемки (с рук):",
     ["AgACAgIAAxkBAAFNC5FqOAf8G99I3fNypT_nGjcn6kI6OgACtR1rG0hTwUmmwcwTW-xgnQEAAwIAA3kAAzwE"]),
    ("Переносится в разобранном виде, собирается в исключительно спокойном душевном состоянии за 15-30 минут до съемки",
     ["AgACAgIAAxkBAAFNC5dqOAh_EGlMO1aGpWIlUIMJzo6YQAACuB1rG0hTwUmnEk_mwzgOEgEAAwIAA3gAAzwE"])
]

radio_use_steps = [
    ("При использовании репортажного микрофона вставь и закрути по часовой стрелке передатчик Sennheiser G4 в микрофон. Должно получиться так:",
     ["AgACAgIAAxkBAAFNDKRqOBCqhJAUkOogJXvGiD_GvoxfggAC6h1rG0hTwUkOsfJcvaNrOAEAAwIAA3kAAzwE"]),
    ("Не забудь вставить в передатчик аккумуляторные батарейки. Минус на батарейках стороной к пружинке радиосистемы.",
     ["AgACAgIAAxkBAAFNDGdqOA6Eo8UX5NLxYWPhbEx6_BM4fQAC3x1rG0hTwUk4i_Ky4xclZgEAAwIAA3MAAzwE"]),
    ("Вставь батарейки в приемник, который мы будем подключать к камере. Не забывай, минус на батарейке вставляем стороной к пружинке!",
     ["AgACAgIAAxkBAAFNDDpqOA2J1kjaH1mcXIxrZqiG0aX6zQAC1h1rG0hTwUlRrLFn5PFxEgEAAwIAA3MAAzwE"]),
    ("Подключи провод minijack-minijack к приёмнику в разъём \"AF OUT\". Гайка на проводе закручивается по часовой стрелке для фиксации радиосистемы. Приёмник крепится на верхнее крепление камеры («башмак»)",
     ["AgACAgIAAxkBAAFNDftqOB2uaSyxkNvNYbhIWwmVtI_9wQACMh5rG0hTwUnOzhgpn2Mo0AEAAwIAA20AAzwE"]),
    ("Включи радиосистему в следующем порядке:\nСначала включи передатчик (микрофон). Для этого переведи переключатель питания на передатчике Sennheiser G4 в положение ON.\nЗатем включите приёмник Sennheiser G4, нажав кнопку On/Off. После включения убедись, что экраны передатчика и приемника загорелись.",
     ["AgACAgIAAxkBAAFNDrJqOCNwQ5vw4H3CTDnSAAHXns-jslkAAmweaxtIU8FJPO9JzFezs7ABAAMCAAN5AAM8BA"]),
    ("После использования убери радиосистему на место (см. раздел «Где она находится?»), а аккумуляторные батарейки поставь на зарядку. При установке батареек в зарядное устройство следи, чтобы они были вставлены правильно: плоский конец батарейки («минус») должен упираться в пружинку, а конец с небольшим выступом («плюс») должен быть направлен в сторону лампочек. Если батарейка не встаёт на место, не дави на неё — просто переверни её и попробуй снова.",
     ["AgACAgIAAxkBAAFNDu1qOCVGRnv5BAlgEvhAOU_jBvJEqgACcx5rG0hTwUltmR6yo2HmEwEAAwIAA3kAAzwE",
      "AgACAgIAAxkBAAFNDu9qOCVMHSX4I1S1IeV6cZ1BcM9rOwACdR5rG0hTwUl9Zj13ba0qYAEAAwIAA3MAAzwE"])
]

radio_complete_steps = [
    ("**Передатчик Sennheiser G4**\nИмеет XLR вход для микрофона\nРаботает от двух аккумуляторных батареек типа АА",
     ["AgACAgIAAxkBAAFNDBxqOAyWX8RWm61-kpMlt9Hi3HYp7QAC0B1rG0hTwUn0kLw7okjHlQEAAwIAA20AAzwE",
      "AgACAgIAAxkBAAFNDGdqOA6Eo8UX5NLxYWPhbEx6_BM4fQAC3x1rG0hTwUk4i_Ky4xclZgEAAwIAA3gAAzwE"]),
    ("**Микрофон Sennheiser**\nИмеет XLR выход и тумблер включения. Обычно используется вместе с передатчиком Sennheiser",
     ["AgACAgIAAxkBAAFNDCdqOA0FU4S_vZAN9BWrRqL4n0QzOAAC0R1rG0hTwUka1YUTxwc3RAEAAwIAA3kAAzwE"]),
    ("**Приёмник Sennheiser G4**\nИмеет Mini jack выход, промаркированный надписью \"AF OUT\". Используется вместе с радиосистемой, прикрепляется на башмак камеры и передаёт сигнал через провод minijack-minijack. Работает от двух аккумуляторных батареек типа АА",
     ["AgACAgIAAxkBAAFNDDpqOA2J1kjaH1mcXIxrZqiG0aX6zQAC1h1rG0hTwUlRrLFn5PFxEgEAAwIAA3gAAzwE"]),
    ("**Батарейка AA (аккумуляторная)**\nИспользуется вместе с радиосистемой",
     ["AgACAgIAAxkBAAFNDF9qOA5UxDSxyhVvctw8bOLPRaL4CQAC3B1rG0hTwUlhPJ5lk-2sfwEAAwIAA3kAAzwE"]),
    ("**Провод minijack-minijack**\nИспользуется для передачи аудиосигнала из Приёмника Sennheiser в камеру",
     ["AgACAgIAAxkBAAFNDHxqOA8bd9COydykj5X1uMkuhm_jzgAC4x1rG0hTwUmeQzFZhbXcWgEAAwIAA3gAAzwE"])
]

camera_complete_steps = [
    ("**Sony FDR-AX53**\nКамкордер для репортажной съемки на выезде. Идеально подходит для оперативной съемки с рук",
     ["AgACAgIAAxkBAAFNHZZqOSGMKkps_ar1fW6F72JbxVVx2AACsBtrG0hTyUlmJaxO_dMGDgEAAwIAA3kAAzwE",
      "AgACAgIAAxkBAAFNHZhqOSGVXCdL0RtfMV5RC0ZKq6rsjAACsRtrG0hTyUlE5hSf-mvixAEAAwIAA3kAAzwE"]),
    ("**Аккумуляторы для Sony FDR-AX53**\nРазличаются по ёмкости энергоячеек",
     ["AgACAgIAAxkBAAFNE2JqOFHwmY8WV0-WjzaHJGbWHAwtsgACKB9rG0hTwUn3wVgwfu9MHQEAAwIAA3gAAzwE"]),
    ("**SD карта Kingston 256gb**\nИспользуется для всех камер и съёмок. Хранится в кейсе",
     ["AgACAgIAAxkBAAFNE3BqOFJ_EFbR5xuXM_uQhhA7BEv7SgACLh9rG0hTwUmdY4t_Czn_bwEAAwIAA3gAAzwE",
      "AgACAgIAAxkBAAFNE3ZqOFKgnGm21-SXFRPYHTNsk-04PQACLR9rG0hTwUmmM3hiTlGflgEAAwIAA3kAAzwE"]),
    ("**Площадки**\nНеобходимы для соединения камеры со штативом. Площадка закручивается в резьбу в днище камеры с помощью отвертки или 10-рублевой монетки (в целом, подойдет любая)",
     ["AgACAgIAAxkBAAFNE45qOFRLs4kYfSEJmAbGhiEF5fvhaQACMR9rG0hTwUmoqZPhTYX0wQEAAwIAA3kAAzwE",
      "AgACAgIAAxkBAAFNE5FqOFRmu0wQ78JV3bi3SZ6msIB4-wACMh9rG0hTwUl9Gvwc8f9gSwEAAwIAA3gAAzwE"]),
    ("**Штативы**\nИногда используются на выездных съёмках",
     ["AgACAgIAAxkBAAFNE5tqOFUPxkQOiPO5z-gj0N7dvuvTWgACNR9rG0hTwUmLBfSL-7Zf2wEAAwIAA3gAAzwE",
      "AgACAgIAAxkBAAFNE5xqOFUPDo71hwzkcM18gmNaMdtMpQACNh9rG0hTwUmRCSFOcwo1fAEAAwIAA20AAzwE"])
]

camera_battery_steps = [
    ("Аккумулятор вставляется в заднюю часть камеры. Приложи его к месту крепления сзади и сдвинь по направляющим до щелчка. Если аккумулятор не двигается легко, не дави на него — скорее всего, он повернут неправильно. Траектория указана красными стрелками.",
     ["AgACAgIAAxkBAAFNE8NqOFmPldtwp8qcqvHB1xMkLIOuPgACRh9rG0hTwUmGcBMltsrhRgEAAwIAA3kAAzwE",
      "AgACAgIAAxkBAAFNE8xqOFtKKnZpoyevTiQ7CIMVsIiA4wACZh9rG0hTwUkQ5-_BhFvn2gEAAwIAA3gAAzwE"]),
    ("Аккумуляторы различаются по ёмкости энергоячеек. Чем больше – тем дольше будет работать",
     ["AgACAgIAAxkBAAFNE2JqOFHwmY8WV0-WjzaHJGbWHAwtsgACKB9rG0hTwUn3wVgwfu9MHQEAAwIAA3MAAzwE"])
]

camera_tripod_steps = [
    ("**Как разложить штатив:**\n1. Достань штатив из чехла.\n2. Возьми его одной рукой за верхнюю часть, а другой рукой аккуратно разведи три ножки в стороны.\n3. Раскрой ножки до упора, чтобы штатив устойчиво стоял на земле.\n4. Открой защёлки на ножках и выдвинь секции вниз.\n5. После выдвижения каждой секции закрой защёлку обратно, чтобы ножка зафиксировалась.\n6. При необходимости подними центральную колонну, вращая фиксирующее кольцо, и затяни его после регулировки.",
     ["AgACAgIAAxkBAAFNE-RqOFxkLXMlqEtCRasorPsBgEOL6AACZx9rG0hTwUnM3XtmubAougEAAwIAA3gAAzwE",
      "AgACAgIAAxkBAAFNE5xqOFUPDo71hwzkcM18gmNaMdtMpQACNh9rG0hTwUmRCSFOcwo1fAEAAwIAA3gAAzwE",
      "AgACAgIAAxkBAAFNE5tqOFUPxkQOiPO5z-gj0N7dvuvTWgACNR9rG0hTwUmLBfSL-7Zf2wEAAwIAA3gAAzwE"]),
    ("Вставь площадку для штатива в камеру. Площадка закручивается в резьбу в днище камеры с помощью отвертки или 10-рублевой монетки (в целом, подойдет любая)",
     ["AgACAgIAAxkBAAFNE45qOFRLs4kYfSEJmAbGhiEF5fvhaQACMR9rG0hTwUmoqZPhTYX0wQEAAwIAA3gAAzwE",
      "AgACAgIAAxkBAAFNFBpqOF9GF_kw6gkJpfhvPZVyz2zK4AACax9rG0hTwUnWlPgo9atMcwEAAwIAA3kAAzwE"]),
    ("Закрепи камеру на штативе. Затяни зажим, который удерживает площадку. \nПеред съёмкой слегка покачай камеру рукой. Если она не двигается и не люфтит, значит всё закреплено правильно.\n\n**Важно!**\n- Не тяни ножки силой. Если что-то не двигается, проверь, не закрыта ли защёлка.\n- Перед установкой камеры убедись, что все защёлки закрыты и ножки надёжно зафиксированы.\n- Не поднимай штатив за камеру, когда она установлена на площадке.",
     []),
    ("**Как сложить штатив:**\n1. Сними камеру со штатива.\n2. Опусти центральную колонну до конца и затяни фиксатор.\n3. Открой защёлки на ножках и задвинь все секции обратно.\n4. Закрой защёлки после того, как секции полностью задвинуты.\n5. Сведи три ножки вместе.\n6. Убери штатив в чехол.",
     ["AgACAgIAAxkBAAFNE5tqOFUPxkQOiPO5z-gj0N7dvuvTWgACNR9rG0hTwUmLBfSL-7Zf2wEAAwIAA3gAAzwE",
      "AgACAgIAAxkBAAFNE5xqOFUPDo71hwzkcM18gmNaMdtMpQACNh9rG0hTwUmRCSFOcwo1fAEAAwIAA3gAAzwE",
      "AgACAgIAAxkBAAFNE-RqOFxkLXMlqEtCRasorPsBgEOL6AACZx9rG0hTwUnM3XtmubAougEAAwIAA3gAAzwE"])
]

sd_step = [
    ("Убедись, что камера выключена. SD-карта вставляется в выключенную камеру. Слот для карты памяти находится внутри. Открой откидной экран камеры влево — под ним, на боковой стороне корпуса, увидишь небольшую крышку с обозначением \"Memory Card\". Открой её и вставь SD-карту контактами вперёд до легкого щелчка.",
     ["AgACAgIAAxkBAAFNE6xqOFaejzFalVZ2Bw4TMIXYY_sqzQACPh9rG0hTwUlRlaAT7hVsPAEAAwIAA3gAAzwE",
      "AgACAgIAAxkBAAFNE65qOFa6P70hKklAL_UHUFxoUoJFGAACPx9rG0hTwUnKjLpZQwjsvwEAAwIAA3kAAzwE",
      "AgACAgIAAxkBAAFNE7BqOFbJMgm9e0RkL_IDTPVtR0ThVwACQB9rG0hTwUl0mFDYNocNFQEAAwIAA3kAAzwE"])
]

radio_where_step = ("Радиосистема находится в 309 кабинете в правом от входа шкафу для техники, на полке с надписью **Звук**",
                    ["AgACAgIAAxkBAAFNC9pqOAqW1-obT6qEZWq4-mf2UZYemQAC1BxrG2TPwElqLWeTD_AJ1gEAAwIAA3gAAzwE"])

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.set_state(Navigation.main)
    await state.update_data(message_ids=[])
    msg = await message.answer(
        "Привет! Я бот-помощник по технике ФСТмедиа.\nО чем хочешь узнать?",
        reply_markup=main_menu_kb()
    )
    await state.update_data(message_ids=[msg.message_id])

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 Доступные команды:\n"
        "/start - Главное меню\n"
        "/help - Эта справка\n\n"
        "Используйте кнопки для навигации по разделам."
    )

@dp.message()
async def handle_text(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    current_time = time.time()
    async with spam_lock:
        last_time = user_last_msg.get(user_id, 0)
        if current_time - last_time < SPAM_INTERVAL:
            await message.answer(
                "⏳ Пожалуйста, не отправляйте сообщения так часто. Подождите немного и попробуйте снова.\n"
                "Используйте кнопки для навигации."
            )
            return
        user_last_msg[user_id] = current_time

    await message.answer(
        "⚠️ Пожалуйста, используйте кнопки для навигации.\n"
        "Если вы потерялись, нажмите /start для возврата в главное меню.",
        reply_markup=back_to_main_kb()
    )
    await state.set_state(Navigation.main)

@dp.callback_query(lambda c: c.data in ["kit", "radio", "camera", "main_menu"])
async def main_menu_callback(callback: types.CallbackQuery, state: FSMContext):
    await clear_and_go(state, callback.message.chat.id, callback.message.message_id)
    data = callback.data
    if data == "main_menu":
        await state.set_state(Navigation.main)
        msg = await callback.message.answer(
            "О чем хочешь узнать?",
            reply_markup=main_menu_kb()
        )
        await state.update_data(message_ids=[msg.message_id])
        await callback.answer()
        return
    if data == "kit":
        await state.set_state(Navigation.kit)
        await state.update_data(step=0)
        step_data = kit_steps[0]
        kb = nav_kb(has_back=False, has_next=True)
        ids = await send_step_message(callback.message, step_data[0], step_data[1], kb)
        await state.update_data(message_ids=ids)
        await callback.answer()
        return
    if data == "radio":
        await state.set_state(Navigation.radio_menu)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Как её использовать?", callback_data="radio_use_prompt")],
            [InlineKeyboardButton(text="Где она находится?", callback_data="radio_where")],
            [InlineKeyboardButton(text="Что у нее в комплекте?", callback_data="radio_complete")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
        ])
        msg = await callback.message.answer(
            "**Выбран раздел Радиосистема**. Выбери что хочешь узнать",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        await state.update_data(message_ids=[msg.message_id])
        await callback.answer()
        return
    if data == "camera":
        await state.set_state(Navigation.camera_menu)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Что в комплекте с камерой?", callback_data="camera_complete")],
            [InlineKeyboardButton(text="Как использовать карту памяти?", callback_data="camera_sd")],
            [InlineKeyboardButton(text="Об аккумуляторе камеры", callback_data="camera_battery")],
            [InlineKeyboardButton(text="Как использовать штатив", callback_data="camera_tripod")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
        ])
        msg = await callback.message.answer(
            "**Выбран раздел Камеры**. Выбери что хочешь узнать",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        await state.update_data(message_ids=[msg.message_id])
        await callback.answer()
        return

@dp.callback_query(lambda c: c.data in ["nav_next", "nav_back"], StateFilter(Navigation.kit))
async def kit_navigation(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data
    step = (await state.get_data()).get("step", 0)
    if data == "nav_next":
        step += 1
    elif data == "nav_back":
        step -= 1
    if step < 0 or step >= len(kit_steps):
        await callback.answer("Нет больше сообщений")
        return
    await state.update_data(step=step)
    step_data = kit_steps[step]
    has_back = step > 0
    has_next = step < len(kit_steps) - 1
    kb = nav_kb(has_back, has_next)
    await clear_and_go(state, callback.message.chat.id, callback.message.message_id)
    ids = await send_step_message(callback.message, step_data[0], step_data[1], kb)
    await state.update_data(message_ids=ids)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "radio_use_prompt", StateFilter(Navigation.radio_menu))
async def radio_use_prompt(callback: types.CallbackQuery, state: FSMContext):
    await clear_and_go(state, callback.message.chat.id, callback.message.message_id)
    await state.set_state(Navigation.radio_use_prompt)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Прочитать «Что в комплекте с радиосистемой?»", callback_data="goto_radio_complete")],
        [InlineKeyboardButton(text="Я прочитал(а)", callback_data="goto_radio_use")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    msg = await callback.message.answer(
        "Рекомендуем прочитать раздел «Что в комплекте с радиосистемой?»",
        reply_markup=kb
    )
    await state.update_data(message_ids=[msg.message_id])
    await callback.answer()

@dp.callback_query(lambda c: c.data in ["goto_radio_complete", "goto_radio_use"])
async def radio_goto_handlers(callback: types.CallbackQuery, state: FSMContext):
    await clear_and_go(state, callback.message.chat.id, callback.message.message_id)
    if callback.data == "goto_radio_complete":
        await state.set_state(Navigation.radio_complete)
        await state.update_data(step=0)
        step_data = radio_complete_steps[0]
        kb = nav_kb(has_back=False, has_next=True, menu_callback="back_to_radio_menu")
    else:
        await state.set_state(Navigation.radio_use)
        await state.update_data(step=0)
        step_data = radio_use_steps[0]
        kb = nav_kb(has_back=False, has_next=True, menu_callback="back_to_radio_menu")
    ids = await send_step_message(callback.message, step_data[0], step_data[1], kb)
    await state.update_data(message_ids=ids)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "radio_where")
async def radio_where_handler(callback: types.CallbackQuery, state: FSMContext):
    await clear_and_go(state, callback.message.chat.id, callback.message.message_id)
    await state.set_state(Navigation.radio_where)
    text, file_ids = radio_where_step
    kb = back_to_main_kb()
    ids = await send_step_message(callback.message, text, file_ids, kb)
    await state.update_data(message_ids=ids)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "radio_complete", StateFilter(Navigation.radio_menu))
async def radio_complete_start(callback: types.CallbackQuery, state: FSMContext):
    await clear_and_go(state, callback.message.chat.id, callback.message.message_id)
    await state.set_state(Navigation.radio_complete)
    await state.update_data(step=0)
    step_data = radio_complete_steps[0]
    kb = nav_kb(has_back=False, has_next=True, menu_callback="back_to_radio_menu")
    ids = await send_step_message(callback.message, step_data[0], step_data[1], kb)
    await state.update_data(message_ids=ids)
    await callback.answer()

@dp.callback_query(lambda c: c.data in ["nav_next", "nav_back"], StateFilter(Navigation.radio_complete))
async def radio_complete_nav(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data
    step = (await state.get_data()).get("step", 0)
    if data == "nav_next":
        step += 1
    elif data == "nav_back":
        step -= 1
    if step < 0 or step >= len(radio_complete_steps):
        await callback.answer("Нет больше сообщений")
        return
    await state.update_data(step=step)
    step_data = radio_complete_steps[step]
    has_back = step > 0
    has_next = step < len(radio_complete_steps) - 1
    kb = nav_kb(has_back, has_next, menu_callback="back_to_radio_menu")
    await clear_and_go(state, callback.message.chat.id, callback.message.message_id)
    ids = await send_step_message(callback.message, step_data[0], step_data[1], kb)
    await state.update_data(message_ids=ids)
    await callback.answer()

@dp.callback_query(lambda c: c.data in ["nav_next", "nav_back"], StateFilter(Navigation.radio_use))
async def radio_use_nav(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data
    step = (await state.get_data()).get("step", 0)
    if data == "nav_next":
        step += 1
    elif data == "nav_back":
        step -= 1
    if step < 0 or step >= len(radio_use_steps):
        await callback.answer("Нет больше сообщений")
        return
    await state.update_data(step=step)
    step_data = radio_use_steps[step]
    has_back = step > 0
    has_next = step < len(radio_use_steps) - 1
    extra = []
    if step == len(radio_use_steps) - 1:
        extra = [("📌 Где она находится?", "radio_where")]
    kb = nav_kb(has_back, has_next, extra_buttons=extra, menu_callback="back_to_radio_menu")
    await clear_and_go(state, callback.message.chat.id, callback.message.message_id)
    ids = await send_step_message(callback.message, step_data[0], step_data[1], kb)
    await state.update_data(message_ids=ids)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_radio_menu")
async def back_to_radio_menu(callback: types.CallbackQuery, state: FSMContext):
    await clear_and_go(state, callback.message.chat.id, callback.message.message_id)
    await state.set_state(Navigation.radio_menu)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Как её использовать?", callback_data="radio_use_prompt")],
        [InlineKeyboardButton(text="Где она находится?", callback_data="radio_where")],
        [InlineKeyboardButton(text="Что у нее в комплекте?", callback_data="radio_complete")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    msg = await callback.message.answer(
        "**Выбран раздел Радиосистема**. Выбери что хочешь узнать",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await state.update_data(message_ids=[msg.message_id])
    await callback.answer()

@dp.callback_query(lambda c: c.data == "camera_complete", StateFilter(Navigation.camera_menu))
async def camera_complete_start(callback: types.CallbackQuery, state: FSMContext):
    await clear_and_go(state, callback.message.chat.id, callback.message.message_id)
    await state.set_state(Navigation.camera_complete)
    await state.update_data(step=0)
    step_data = camera_complete_steps[0]
    kb = nav_kb(has_back=False, has_next=True, menu_callback="back_to_camera_menu")
    ids = await send_step_message(callback.message, step_data[0], step_data[1], kb)
    await state.update_data(message_ids=ids)
    await callback.answer()

@dp.callback_query(lambda c: c.data in ["nav_next", "nav_back"], StateFilter(Navigation.camera_complete))
async def camera_complete_nav(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data
    step = (await state.get_data()).get("step", 0)
    if data == "nav_next":
        step += 1
    elif data == "nav_back":
        step -= 1
    if step < 0 or step >= len(camera_complete_steps):
        await callback.answer("Нет больше сообщений")
        return
    await state.update_data(step=step)
    step_data = camera_complete_steps[step]
    has_back = step > 0
    has_next = step < len(camera_complete_steps) - 1
    extra = []
    if step == 1:
        extra = [("**Как вставлять аккумулятор**", "goto_camera_battery")]
    elif step == 2:
        extra = [("**Как вставлять SD-карту**", "goto_camera_sd")]
    elif step == 3 or step == 4:
        extra = [("**Как использовать штатив**", "goto_camera_tripod")]
    kb = nav_kb(has_back, has_next, extra_buttons=extra, menu_callback="back_to_camera_menu")
    await clear_and_go(state, callback.message.chat.id, callback.message.message_id)
    ids = await send_step_message(callback.message, step_data[0], step_data[1], kb)
    await state.update_data(message_ids=ids)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "camera_sd", StateFilter(Navigation.camera_menu))
async def camera_sd_start(callback: types.CallbackQuery, state: FSMContext):
    await clear_and_go(state, callback.message.chat.id, callback.message.message_id)
    await state.set_state(Navigation.camera_sd)
    await state.update_data(step=0)
    step_data = sd_step[0]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="nav_back")],
        [InlineKeyboardButton(text="Совет", callback_data="camera_sd_tip")],
        [InlineKeyboardButton(text="В меню раздела", callback_data="back_to_camera_menu")],
        [InlineKeyboardButton(text="🔙 К разделам", callback_data="main_menu")]
    ])
    ids = await send_step_message(callback.message, step_data[0], step_data[1], kb)
    await state.update_data(message_ids=ids)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "camera_battery", StateFilter(Navigation.camera_menu))
async def camera_battery_start(callback: types.CallbackQuery, state: FSMContext):
    await clear_and_go(state, callback.message.chat.id, callback.message.message_id)
    await state.set_state(Navigation.camera_battery)
    await state.update_data(step=0)
    step_data = camera_battery_steps[0]
    kb = nav_kb(has_back=False, has_next=True, menu_callback="back_to_camera_menu")
    ids = await send_step_message(callback.message, step_data[0], step_data[1], kb)
    await state.update_data(message_ids=ids)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "camera_tripod", StateFilter(Navigation.camera_menu))
async def camera_tripod_start(callback: types.CallbackQuery, state: FSMContext):
    await clear_and_go(state, callback.message.chat.id, callback.message.message_id)
    await state.set_state(Navigation.camera_tripod)
    await state.update_data(step=0)
    step_data = camera_tripod_steps[0]
    kb = nav_kb(has_back=False, has_next=True, menu_callback="back_to_camera_menu")
    ids = await send_step_message(callback.message, step_data[0], step_data[1], kb)
    await state.update_data(message_ids=ids)
    await callback.answer()

@dp.callback_query(lambda c: c.data in ["goto_camera_battery", "goto_camera_sd", "goto_camera_tripod"])
async def camera_goto_handlers(callback: types.CallbackQuery, state: FSMContext):
    await clear_and_go(state, callback.message.chat.id, callback.message.message_id)
    target = callback.data
    if target == "goto_camera_battery":
        await state.set_state(Navigation.camera_battery)
        await state.update_data(step=0)
        step_data = camera_battery_steps[0]
        kb = nav_kb(has_back=False, has_next=True, menu_callback="back_to_camera_menu")
    elif target == "goto_camera_sd":
        await state.set_state(Navigation.camera_sd)
        await state.update_data(step=0)
        step_data = sd_step[0]
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="nav_back")],
            [InlineKeyboardButton(text="Совет", callback_data="camera_sd_tip")],
            [InlineKeyboardButton(text="В меню раздела", callback_data="back_to_camera_menu")],
            [InlineKeyboardButton(text="🔙 К разделам", callback_data="main_menu")]
        ])
    else:
        await state.set_state(Navigation.camera_tripod)
        await state.update_data(step=0)
        step_data = camera_tripod_steps[0]
        kb = nav_kb(has_back=False, has_next=True, menu_callback="back_to_camera_menu")
    ids = await send_step_message(callback.message, step_data[0], step_data[1], kb)
    await state.update_data(message_ids=ids)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "nav_back", StateFilter(Navigation.camera_sd))
async def camera_sd_back(callback: types.CallbackQuery, state: FSMContext):
    await clear_and_go(state, callback.message.chat.id, callback.message.message_id)
    await state.set_state(Navigation.camera_menu)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Что в комплекте с камерой?", callback_data="camera_complete")],
        [InlineKeyboardButton(text="Как использовать карту памяти?", callback_data="camera_sd")],
        [InlineKeyboardButton(text="Об аккумуляторе камеры", callback_data="camera_battery")],
        [InlineKeyboardButton(text="Как использовать штатив", callback_data="camera_tripod")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    msg = await callback.message.answer(
        "**Выбран раздел Камеры**. Выбери что хочешь узнать",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await state.update_data(message_ids=[msg.message_id])
    await callback.answer()

@dp.callback_query(lambda c: c.data == "camera_sd_tip", StateFilter(Navigation.camera_sd))
async def camera_sd_tip(callback: types.CallbackQuery, state: FSMContext):
    await clear_and_go(state, callback.message.chat.id, callback.message.message_id)
    await state.set_state(Navigation.camera_sd_tip)
    tip_text = (
        "Совет: Перед съемкой отформатируй карту памяти. Включи камеру и нажми кнопку MENU. Затем открой раздел Настройка (Setup) → Форматировать (Format) → выбери карту памяти и подтверди форматирование. После завершения карта будет полностью очищена и готова к записи. Ту же операцию проделай после съемки, когда выгрузишь все файлы. Это очищает карту и подготавливает её к следующей съемке.\n\n"
        "_⚠️ Перед форматированием убедись, что все нужные фото и видео сохранены в другом месте. Форматирование удалит все данные с карты памяти без возможности восстановления через камеру._"
    )
    kb = back_to_main_kb()
    msg = await callback.message.answer(tip_text, reply_markup=kb, parse_mode="Markdown")
    await state.update_data(message_ids=[msg.message_id])
    await callback.answer()

@dp.callback_query(lambda c: c.data in ["nav_next", "nav_back"], StateFilter(Navigation.camera_battery))
async def camera_battery_nav(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data
    step = (await state.get_data()).get("step", 0)
    if data == "nav_next":
        step += 1
    elif data == "nav_back":
        step -= 1
    if step < 0 or step >= len(camera_battery_steps):
        await callback.answer("Нет больше сообщений")
        return
    await state.update_data(step=step)
    step_data = camera_battery_steps[step]
    has_back = step > 0
    has_next = step < len(camera_battery_steps) - 1
    kb = nav_kb(has_back, has_next, menu_callback="back_to_camera_menu")
    await clear_and_go(state, callback.message.chat.id, callback.message.message_id)
    ids = await send_step_message(callback.message, step_data[0], step_data[1], kb)
    await state.update_data(message_ids=ids)
    await callback.answer()

@dp.callback_query(lambda c: c.data in ["nav_next", "nav_back"], StateFilter(Navigation.camera_tripod))
async def camera_tripod_nav(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data
    step = (await state.get_data()).get("step", 0)
    if data == "nav_next":
        step += 1
    elif data == "nav_back":
        step -= 1
    if step < 0 or step >= len(camera_tripod_steps):
        await callback.answer("Нет больше сообщений")
        return
    await state.update_data(step=step)
    step_data = camera_tripod_steps[step]
    has_back = step > 0
    has_next = step < len(camera_tripod_steps) - 1
    kb = nav_kb(has_back, has_next, menu_callback="back_to_camera_menu")
    await clear_and_go(state, callback.message.chat.id, callback.message.message_id)
    ids = await send_step_message(callback.message, step_data[0], step_data[1], kb)
    await state.update_data(message_ids=ids)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_camera_menu")
async def back_to_camera_menu(callback: types.CallbackQuery, state: FSMContext):
    await clear_and_go(state, callback.message.chat.id, callback.message.message_id)
    await state.set_state(Navigation.camera_menu)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Что в комплекте с камерой?", callback_data="camera_complete")],
        [InlineKeyboardButton(text="Как использовать карту памяти?", callback_data="camera_sd")],
        [InlineKeyboardButton(text="Об аккумуляторе камеры", callback_data="camera_battery")],
        [InlineKeyboardButton(text="Как использовать штатив", callback_data="camera_tripod")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    msg = await callback.message.answer(
        "**Выбран раздел Камеры**. Выбери что хочешь узнать",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await state.update_data(message_ids=[msg.message_id])
    await callback.answer()

async def handle(request):
    return web.Response(text="I'm alive!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, host='0.0.0.0', port=port)
    await site.start()
    print(f"Веб-сервер запущен на порту {port}")
    await asyncio.Event().wait()

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот запущен!")
    await asyncio.gather(
        dp.start_polling(bot),
        start_web_server()
    )

if __name__ == "__main__":
    asyncio.run(main())
