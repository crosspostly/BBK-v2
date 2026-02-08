import logging
import asyncio
import os
from typing import Optional
from datetime import datetime
import pytz

from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties


import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- Configuration ---
TOKEN = "8483555978:AAF9o3xiRpi-Q7y77-6dVmHfSsVgMPgR-wo"




# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)


# --- Google Sheets Setup ---
def get_sheet():
    logger.info("Attempting to get Google Sheet.")
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open("Панда Ролс").worksheet("Расписание")
        logger.info("Successfully connected to Google Sheet.")
        return sheet
    except gspread.exceptions.GSpreadException as e:
        logger.error(f"Google Sheets error: {e}", exc_info=True)
        return None


# --- FSM States ---
class BookingStates(StatesGroup):
    choosing_date = State()


# --- Handlers ---
router = Router()

@router.message(Command("start"))
async def command_start_handler(message: Message, state: FSMContext) -> None:
    logger.info(f"Received /start command from user: {message.from_user.id}")
    await state.clear() # Clear any previous state

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Показать свободные даты", callback_data="show_available_dates")]
        ]
    )
    await message.answer(
        "Добро пожаловать! Нажмите кнопку, чтобы найти свободные даты.",
        reply_markup=keyboard,
    )

@router.callback_query(lambda query: query.data == "show_available_dates")
async def show_available_dates_callback(callback_query: CallbackQuery, state: FSMContext) -> None:
    logger.info(f"Received 'show_available_dates' callback from user: {callback_query.from_user.id}")
    await callback_query.answer() # Always answer callback queries, even if no notification is needed
    await callback_query.message.edit_text("Пожалуйста, подождите, ищу свободные даты...") # Show immediate feedback

    await get_and_send_available_dates(callback_query.message, state)

@router.message(Command("available_dates"))
async def command_available_dates_handler(message: Message, state: FSMContext) -> None:
    logger.info(f"Received /available_dates command from user: {message.from_user.id}")
    await get_and_send_available_dates(message, state)


async def get_and_send_available_dates(message: Message, state: FSMContext) -> None:
    """Fetches and sends available dates to the user."""
    logger.info("Executing get_and_send_available_dates.")
    
    sheet = get_sheet()
    if not sheet:
        await message.edit_text( # Use edit_text if it's a callback, answer if it's a message
            "Ошибка: Не удалось подключиться к таблице. Проверьте ключ доступа и права доступа к таблице."
        )
        await state.clear()
        return

    try:
        data = sheet.get_all_values()
        available = []
        MOSCOW_TZ = pytz.timezone('Europe/Moscow')
        now = datetime.now(MOSCOW_TZ)
        today = now.date()
        found_future_date = False

        # Skip header (row 1 is index 0 in data)
        for i, row in enumerate(data[1:], start=2): # `start=2` means 1-based row index in sheet
            if len(row) > 0:  # Ensure there's at least a date in column A
                date = row[0]
                if not date: continue

                try:
                    row_date_dt = datetime.strptime(f"{date}.{now.year}", "%d.%m.%Y")
                    row_date = row_date_dt.date()
                    if not found_future_date:
                        if row_date >= today:
                            found_future_date = True
                        else:
                            continue
                except ValueError:
                    continue

                # Pad the row with empty strings if it's shorter than 5 elements (up to E)
                padded_row = row + [''] * max(0, 5 - len(row))
                blogger_slots = padded_row[1:5]  # Get columns B, C, D, E
                if any(slot == "" for slot in blogger_slots):
                    available.append(date)

        if available:
            await state.update_data(available_dates=available)
            await state.set_state(BookingStates.choosing_date)
            
            keyboard_buttons = [[InlineKeyboardButton(text=date, callback_data=date)] for date in available]
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
            await message.edit_text(
                "Пожалуйста, выберите дату из списка ниже:",
                reply_markup=keyboard
            )
        else:
            await message.edit_text("Свободных дат нет.")
            await state.clear() # No dates, so end conversation

    except gspread.exceptions.WorksheetNotFound:
        logger.error("Worksheet 'Расписание' not found.", exc_info=True)
        await message.edit_text(
            "Ошибка: Лист 'Расписание' не найден. Пожалуйста, проверьте название листа."
        )
        await state.clear()
    except Exception as e:
        logger.error(f"An error occurred in get_and_send_available_dates: {e}", exc_info=True)
        await message.edit_text("Произошла ошибка при получении данных.")
        await state.clear()

@router.callback_query(BookingStates.choosing_date)
async def choose_date_handler(callback_query: CallbackQuery, state: FSMContext) -> None:
    logger.info(f"Received chosen date '{callback_query.data}' from user: {callback_query.from_user.id}")
    await callback_query.answer() # Acknowledge the callback
    chosen_date = callback_query.data
    user_data = await state.get_data()
    available_dates = user_data.get("available_dates", [])

    if chosen_date not in available_dates:
        await callback_query.message.answer("Неверная дата. Пожалуйста, выберите дату из предложенного списка.")
        return

    sheet = get_sheet()
    if not sheet:
        await callback_query.message.answer("Ошибка: Не удалось подключиться к таблице.")
        await state.clear()
        return
        
    try:
        data = sheet.get_all_values()
        # Find the row for the chosen date
        for i, row in enumerate(data[1:], start=2): # `start=2` for 1-based sheet row
            if row and row[0] == chosen_date:
                # Pad the row with empty strings if it's shorter than 5 elements (up to E)
                padded_row = row + [''] * max(0, 5 - len(row))
                # Find the first empty slot in columns B, C, D, E
                for j in range(1, 5): # Column indices 1-4 correspond to B-E
                    if padded_row[j] == "":
                        cell_to_update = f"{chr(ord('A') + j)}{i}"
                        user_info = ""
                        if callback_query.from_user.username:
                            user_info = f"https://t.me/{callback_query.from_user.username}"
                        else:
                            user_info = f"ID: {callback_query.from_user.id}"
                        sheet.update_acell(cell_to_update, user_info)
                        await callback_query.message.answer(
                            f"Вы успешно записаны на {chosen_date}!"
                        )
                        await state.clear() # End conversation
                        return
                        
        await callback_query.message.answer("Извините, в этой дате уже не осталось мест.")
        await state.clear() # End conversation
        return

    except Exception as e:
        logger.error(f"An error occurred in choose_date_handler: {e}", exc_info=True)
        await callback_query.message.answer("Произошла ошибка при записи данных.")
        await state.clear()

@router.message(Command("cancel"))
async def command_cancel_handler(message: Message, state: FSMContext) -> None:
    logger.info(f"Received /cancel command from user: {message.from_user.id}")
    await state.clear() # Clear any previous state
    await message.answer("Действие отменено.")





def main():
    dp = Dispatcher()
    dp.include_router(router)
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    # Start long polling
    asyncio.run(dp.start_polling(bot))


if __name__ == '__main__':
    main()
