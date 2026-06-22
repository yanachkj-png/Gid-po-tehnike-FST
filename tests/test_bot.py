import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import (
    send_step_message,
    clear_and_go,
    build_main_menu,
    build_section_menu,
    build_nav_keyboard,
    build_simple_menu,
    Navigation
)

def test_build_main_menu():
    kb = build_main_menu()
    assert kb.inline_keyboard is not None
    assert len(kb.inline_keyboard) == 3
    assert kb.inline_keyboard[0][0].text == "Съёмочный комплект ФСТмедиа"
    assert kb.inline_keyboard[0][0].callback_data == "section:kit"
    assert kb.inline_keyboard[1][0].callback_data == "section:radio"
    assert kb.inline_keyboard[2][0].callback_data == "section:camera"

def test_build_section_menu():
    items = [("Пункт 1", "cb1"), ("Пункт 2", "cb2")]
    kb = build_section_menu(items, back_callback="nav:back")
    assert len(kb.inline_keyboard) == 3
    assert kb.inline_keyboard[0][0].text == "Пункт 1"
    assert kb.inline_keyboard[1][0].text == "Пункт 2"
    assert kb.inline_keyboard[2][0].text == "🔙 Назад"
    assert kb.inline_keyboard[2][0].callback_data == "nav:back"

def test_build_nav_keyboard():
    kb = build_nav_keyboard(
        has_back=True,
        has_next=True,
        extra_buttons=[("Доп", "extra")],
        menu_callback="menu:cb"
    )
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
    assert kb.inline_keyboard[0][1].text == "Кнопка 2"

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
    target.answer_photo.assert_called_once_with(
        photo="photo_id",
        caption=text,
        reply_markup=kb,
        parse_mode="Markdown"
    )
    assert result == [456]

@pytest.mark.asyncio
async def test_send_step_message_multiple_photos():
    target = AsyncMock()
    target.answer = AsyncMock(return_value=MagicMock(message_id=789))
    target.answer_media_group = AsyncMock(return_value=[
        MagicMock(message_id=111),
        MagicMock(message_id=222)
    ])
    text = "Test text"
    file_ids = ["id1", "id2"]
    kb = MagicMock()
    result = await send_step_message(target, text, file_ids, kb)
    target.answer.assert_called_once_with(text, reply_markup=kb, parse_mode="Markdown")
    target.answer_media_group.assert_called_once()
    assert result == [789, 111, 222]

@pytest.mark.asyncio
async def test_clear_and_go():
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"message_ids": [1, 2, 3]})
    bot_mock = AsyncMock()
    with patch("bot.bot", bot_mock):
        await clear_and_go(state, 123, extra_id=4)
        assert bot_mock.delete_message.call_count == 4
        args_list = [args[1] for args, _ in bot_mock.delete_message.call_args_list]
        assert 1 in args_list
        assert 2 in args_list
        assert 3 in args_list
        assert 4 in args_list
        state.update_data.assert_called_once_with(message_ids=[])

@pytest.mark.asyncio
async def test_clear_and_go_no_extra():
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"message_ids": [5, 6]})
    bot_mock = AsyncMock()
    with patch("bot.bot", bot_mock):
        await clear_and_go(state, 123)
        assert bot_mock.delete_message.call_count == 2
        state.update_data.assert_called_once_with(message_ids=[])

@pytest.mark.asyncio
async def test_clear_and_go_exception_handling():
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"message_ids": [1]})
    bot_mock = AsyncMock()
    bot_mock.delete_message.side_effect = Exception("Test error")
    with patch("bot.bot", bot_mock):
        await clear_and_go(state, 123)
        bot_mock.delete_message.assert_called_once_with(123, 1)
        state.update_data.assert_called_once_with(message_ids=[])

def test_navigation_states():
    assert hasattr(Navigation, 'main')
    assert hasattr(Navigation, 'kit')
    assert hasattr(Navigation, 'radio_menu')
    assert hasattr(Navigation, 'radio_use_prompt')
    assert hasattr(Navigation, 'radio_use')
    assert hasattr(Navigation, 'radio_where')
    assert hasattr(Navigation, 'radio_complete')
    assert hasattr(Navigation, 'camera_menu')
    assert hasattr(Navigation, 'camera_complete')
    assert hasattr(Navigation, 'camera_sd')
    assert hasattr(Navigation, 'camera_sd_tip')
    assert hasattr(Navigation, 'camera_battery')
    assert hasattr(Navigation, 'camera_tripod')
