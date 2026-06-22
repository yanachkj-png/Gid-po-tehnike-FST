import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Message, CallbackQuery, User, Chat, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import Bot, Dispatcher

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import (
    send_step_message,
    clear_and_go,
    build_main_menu,
    build_section_menu,
    build_nav_keyboard,
    build_simple_menu,
    Navigation,
    dp,
    bot as bot_instance,
    kit_steps,
    radio_use_steps,
    radio_complete_steps,
    camera_complete_steps,
    camera_battery_steps,
    camera_tripod_steps,
    sd_step,
    radio_where_step
)

# ========== Тесты для функций построения клавиатур ==========

def test_build_main_menu():
    kb = build_main_menu()
    assert isinstance(kb, InlineKeyboardMarkup)
    assert len(kb.inline_keyboard) == 3
    assert kb.inline_keyboard[0][0].text == "Съёмочный комплект ФСТмедиа"
    assert kb.inline_keyboard[0][0].callback_data == "section:kit"
    assert kb.inline_keyboard[1][0].callback_data == "section:radio"
    assert kb.inline_keyboard[2][0].callback_data == "section:camera"

def test_build_section_menu():
    items = [("Пункт 1", "cb1"), ("Пункт 2", "cb2")]
    kb = build_section_menu(items, back_callback="nav:back")
    assert len(kb.inline_keyboard) == 3  # 2 пункта + кнопка "Назад"
    assert kb.inline_keyboard[0][0].text == "Пункт 1"
    assert kb.inline_keyboard[0][0].callback_data == "cb1"
    assert kb.inline_keyboard[2][0].text == "🔙 Назад"
    assert kb.inline_keyboard[2][0].callback_data == "nav:back"

def test_build_nav_keyboard():
    kb = build_nav_keyboard(has_back=True, has_next=True, extra_buttons=[("Доп", "extra")], menu_callback="menu:cb")
    # Проверяем, что кнопки есть
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    texts = [btn.text for btn in buttons]
    assert "⬅️ Назад" in texts
    assert "Далее ➡️" in texts
    assert "Доп" in texts
    assert "В меню раздела" in texts
    assert "🔙 К разделам" in texts

def test_build_simple_menu():
    buttons = [("Кнопка 1", "cb1"), ("Кнопка 2", "cb2")]
    kb = build_simple_menu(buttons)
    assert len(kb.inline_keyboard) == 1
    assert kb.inline_keyboard[0][0].text == "Кнопка 1"
    assert kb.inline_keyboard[0][0].callback_data == "cb1"
    assert kb.inline_keyboard[0][1].text == "Кнопка 2"

# ========== Тесты для send_step_message ==========

@pytest.mark.asyncio
async def test_send_step_message_no_photo():
    target = AsyncMock()
    target.answer = AsyncMock(return_value=MagicMock(message_id=123))
    text = "Test text"
    file_ids = []
    kb = MagicMock()
    result = await send_step_message(target, text, file_ids, kb)
    target.answer.assert_called_once_with(text, reply_markup=kb, parse_mode="Markdown")
    assert result == [123]

@pytest.mark.asyncio
async def test_send_step_message_one_photo():
    target = AsyncMock()
    target.answer_photo = AsyncMock(return_value=MagicMock(message_id=456))
    text = "Test text"
    file_ids = ["photo_id"]
    kb = MagicMock()
    result = await send_step_message(target, text, file_ids, kb)
    target.answer_photo.assert_called_once_with(photo="photo_id", caption=text, reply_markup=kb, parse_mode="Markdown")
    assert result == [456]

@pytest.mark.asyncio
async def test_send_step_message_multiple_photos():
    target = AsyncMock()
    target.answer = AsyncMock(return_value=MagicMock(message_id=789))
    target.answer_media_group = AsyncMock(return_value=[MagicMock(message_id=111), MagicMock(message_id=222)])
    text = "Test text"
    file_ids = ["id1", "id2"]
    kb = MagicMock()
    result = await send_step_message(target, text, file_ids, kb)
    target.answer.assert_called_once_with(text, reply_markup=kb, parse_mode="Markdown")
    target.answer_media_group.assert_called_once()
    assert result == [789, 111, 222]

# ========== Тесты для clear_and_go ==========

@pytest.mark.asyncio
async def test_clear_and_go():
    state = AsyncMock(spec=FSMContext)
    state.get_data = AsyncMock(return_value={"message_ids": [1, 2, 3]})
    bot_mock = AsyncMock()
    with patch("bot.bot", bot_mock):
        await clear_and_go(state, 123, extra_id=4)
        # Проверяем, что удалены все 4 ID
        assert bot_mock.delete_message.call_count == 4
        # Проверяем, что в extra_id добавлен
        args_list = [args[1] for args, _ in bot_mock.delete_message.call_args_list]
        assert 4 in args_list
        assert 1 in args_list
        assert 2 in args_list
        assert 3 in args_list
        state.update_data.assert_called_once_with(message_ids=[])

@pytest.mark.asyncio
async def test_clear_and_go_no_extra():
    state = AsyncMock(spec=FSMContext)
    state.get_data = AsyncMock(return_value={"message_ids": [5, 6]})
    bot_mock = AsyncMock()
    with patch("bot.bot", bot_mock):
        await clear_and_go(state, 123)
        assert bot_mock.delete_message.call_count == 2
        state.update_data.assert_called_once_with(message_ids=[])

@pytest.mark.asyncio
async def test_clear_and_go_exception_handling():
    state = AsyncMock(spec=FSMContext)
    state.get_data = AsyncMock(return_value={"message_ids": [1]})
    bot_mock = AsyncMock()
    bot_mock.delete_message.side_effect = Exception("Test error")
    with patch("bot.bot", bot_mock):
        # Должен перехватить исключение и продолжить
        await clear_and_go(state, 123)
        bot_mock.delete_message.assert_called_once_with(123, 1)
        state.update_data.assert_called_once_with(message_ids=[])

# ========== Интеграционные тесты с FSM ==========

@pytest.fixture
def storage():
    return MemoryStorage()

@pytest.fixture
def bot():
    return AsyncMock(spec=Bot)

@pytest.fixture
def message():
    msg = AsyncMock(spec=Message)
    msg.message_id = 1
    msg.chat = MagicMock(id=123)
    msg.from_user = MagicMock(id=456)
    return msg

@pytest.fixture
def callback_query(message):
    cb = AsyncMock(spec=CallbackQuery)
    cb.message = message
    cb.data = ""
    cb.from_user = MagicMock(id=456)
    return cb

@pytest.mark.asyncio
async def test_cmd_start(bot, message, storage):
    from bot import cmd_start
    state = FSMContext(storage=storage, key="test")
    # Подменяем bot в функции через декоратор? В реальном тесте проще вызвать функцию с переданным ботом.
    # Мы сделаем через monkeypatch.
    with patch("bot.bot", bot):
        await cmd_start(message, state)
        # Проверяем, что ответ отправлен
        message.answer.assert_called_once()
        # Проверяем состояние
        current_state = await state.get_state()
        assert current_state == Navigation.main

@pytest.mark.asyncio
async def test_nav_main_menu(callback_query, storage):
    from bot import nav_callback
    state = FSMContext(storage=storage, key="test")
    callback_query.data = "nav:main_menu"
    with patch("bot.bot", AsyncMock()):
        await nav_callback(callback_query, state)
        callback_query.message.answer.assert_called()
        callback_query.answer.assert_called_once()
        current_state = await state.get_state()
        assert current_state == Navigation.main

@pytest.mark.asyncio
async def test_nav_back_radio(callback_query, storage):
    from bot import nav_callback
    state = FSMContext(storage=storage, key="test")
    await state.set_state(Navigation.radio_complete)
    await state.update_data(step=1, steps=radio_complete_steps, menu_callback="nav:back_to_radio_menu")
    callback_query.data = "nav:back"
    with patch("bot.bot", AsyncMock()) as bot_mock:
        await nav_callback(callback_query, state)
        callback_query.answer.assert_called_once()
        # Проверяем, что шаг уменьшился
        data = await state.get_data()
        assert data["step"] == 0

@pytest.mark.asyncio
async def test_section_callback_kit(callback_query, storage):
    from bot import section_callback
    state = FSMContext(storage=storage, key="test")
    callback_query.data = "section:kit"
    with patch("bot.bot", AsyncMock()):
        await section_callback(callback_query, state)
        callback_query.message.answer.assert_called_once()
        callback_query.answer.assert_called_once()
        current_state = await state.get_state()
        assert current_state == Navigation.kit

@pytest.mark.asyncio
async def test_section_callback_radio(callback_query, storage):
    from bot import section_callback
    state = FSMContext(storage=storage, key="test")
    callback_query.data = "section:radio"
    with patch("bot.bot", AsyncMock()):
        await section_callback(callback_query, state)
        callback_query.message.answer.assert_called_once()
        callback_query.answer.assert_called_once()
        current_state = await state.get_state()
        assert current_state == Navigation.radio_menu

@pytest.mark.asyncio
async def test_section_callback_camera(callback_query, storage):
    from bot import section_callback
    state = FSMContext(storage=storage, key="test")
    callback_query.data = "section:camera"
    with patch("bot.bot", AsyncMock()):
        await section_callback(callback_query, state)
        callback_query.message.answer.assert_called_once()
        callback_query.answer.assert_called_once()
        current_state = await state.get_state()
        assert current_state == Navigation.camera_menu

@pytest.mark.asyncio
async def test_action_radio_use_prompt(callback_query, storage):
    from bot import action_callback
    state = FSMContext(storage=storage, key="test")
    callback_query.data = "action:radio_use_prompt"
    with patch("bot.bot", AsyncMock()):
        await action_callback(callback_query, state)
        callback_query.message.answer.assert_called_once()
        callback_query.answer.assert_called_once()
        current_state = await state.get_state()
        assert current_state == Navigation.radio_use_prompt

@pytest.mark.asyncio
async def test_action_camera_sd(callback_query, storage):
    from bot import action_callback
    state = FSMContext(storage=storage, key="test")
    callback_query.data = "action:camera_sd"
    with patch("bot.bot", AsyncMock()):
        await action_callback(callback_query, state)
        callback_query.message.answer.assert_called_once()
        callback_query.answer.assert_called_once()
        current_state = await state.get_state()
        assert current_state == Navigation.camera_sd

@pytest.mark.asyncio
async def test_goto_radio_complete(callback_query, storage):
    from bot import goto_callback
    state = FSMContext(storage=storage, key="test")
    callback_query.data = "goto:radio_complete"
    with patch("bot.bot", AsyncMock()):
        await goto_callback(callback_query, state)
        callback_query.message.answer.assert_called_once()
        callback_query.answer.assert_called_once()
        current_state = await state.get_state()
        assert current_state == Navigation.radio_complete

@pytest.mark.asyncio
async def test_goto_camera_tripod(callback_query, storage):
    from bot import goto_callback
    state = FSMContext(storage=storage, key="test")
    callback_query.data = "goto:camera_tripod"
    with patch("bot.bot", AsyncMock()):
        await goto_callback(callback_query, state)
        callback_query.message.answer.assert_called_once()
        callback_query.answer.assert_called_once()
        current_state = await state.get_state()
        assert current_state == Navigation.camera_tripod

# ========== Тесты навигации в цепочках ==========

@pytest.mark.asyncio
async def test_nav_next_in_kit(callback_query, storage):
    from bot import nav_callback
    state = FSMContext(storage=storage, key="test")
    await state.set_state(Navigation.kit)
    await state.update_data(step=0, steps=kit_steps)
    callback_query.data = "nav:next"
    with patch("bot.bot", AsyncMock()):
        await nav_callback(callback_query, state)
        data = await state.get_data()
        assert data["step"] == 1
        callback_query.answer.assert_called_once()

@pytest.mark.asyncio
async def test_nav_back_in_radio_complete(callback_query, storage):
    from bot import nav_callback
    state = FSMContext(storage=storage, key="test")
    await state.set_state(Navigation.radio_complete)
    await state.update_data(step=2, steps=radio_complete_steps)
    callback_query.data = "nav:back"
    with patch("bot.bot", AsyncMock()):
        await nav_callback(callback_query, state)
        data = await state.get_data()
        assert data["step"] == 1
        callback_query.answer.assert_called_once()

@pytest.mark.asyncio
async def test_nav_next_last_step(callback_query, storage):
    from bot import nav_callback
    state = FSMContext(storage=storage, key="test")
    steps = camera_battery_steps
    await state.set_state(Navigation.camera_battery)
    await state.update_data(step=len(steps)-1, steps=steps)
    callback_query.data = "nav:next"
    with patch("bot.bot", AsyncMock()):
        await nav_callback(callback_query, state)
        callback_query.answer.assert_called_with("Это последний шаг")

# ========== Тесты для текстового хендлера ==========

@pytest.mark.asyncio
async def test_handle_text_normal(message, storage):
    from bot import handle_text
    state = FSMContext(storage=storage, key="test")
    message.text = "some text"
    with patch("bot.bot", AsyncMock()):
        await handle_text(message, state)
        message.answer.assert_called_once()
        # Проверяем, что состояние установлено в main
        current_state = await state.get_state()
        assert current_state == Navigation.main

@pytest.mark.asyncio
async def test_handle_text_spam(message, storage):
    from bot import handle_text, user_last_msg
    state = FSMContext(storage=storage, key="test")
    message.text = "spam"
    user_id = message.from_user.id
    # Имитируем спам – устанавливаем время
    import time
    user_last_msg[user_id] = time.time() - 0.5  # менее интервала
    with patch("bot.bot", AsyncMock()):
        await handle_text(message, state)
        message.answer.assert_called_once()
        # Должен быть ответ о спаме
        assert "не отправляйте сообщения так часто" in message.answer.call_args[0][0]

# ========== Тесты для построителя клавиатур с extra_buttons ==========

def test_build_nav_keyboard_with_extra():
    extra = [("Кнопка A", "cbA"), ("Кнопка B", "cbB")]
    kb = build_nav_keyboard(has_back=True, has_next=False, extra_buttons=extra, menu_callback="menu")
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    texts = [btn.text for btn in buttons]
    assert "Кнопка A" in texts
    assert "Кнопка B" in texts
    assert "⬅️ Назад" in texts
    assert "Далее ➡️" not in texts
    assert "В меню раздела" in texts
    assert "🔙 К разделам" in texts