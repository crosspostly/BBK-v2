import logging
import asyncio
import os
from typing import Optional, List, Dict
import urllib.parse

from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode, ChatAction
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import pytz
import re

# --- Configuration ---
TOKEN = "8483555978:AAF9o3xiRpi-Q7y77-6dVmHfSsVgMPgR-wo"
PAGE_SIZE = 6  # Reduced for testing pagination
SPREADSHEET_ID = "1EodD0Q-831_vQlVA4Rla8fta1sOZiKLslPIxJLcnWb0" 

# Moscow timezone for reminders
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "bot.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Helper Functions for Formatting ---
def format_date_russian(date_str: str) -> str:
    month_names = {
        "01": "января", "02": "февраля", "03": "марта", "04": "апреля",
        "05": "мая", "06": "июня", "07": "июля", "08": "августа",
        "09": "сентября", "10": "октября", "11": "ноября", "12": "декабря",
    }
    try:
        day, month = date_str.split('.')
        return f"{int(day)} {month_names.get(month, '')}"
    except Exception:
        return date_str

def format_slots_russian(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return f"{count} место"
    elif 2 <= count % 10 <= 4 and (count % 100 < 10 or count % 100 >= 20):
        return f"{count} места"
    else:
        return f"{count} мест"

def parse_location_info(location_raw: Optional[str]) -> tuple[str, str, str]:
    if not location_raw:
        return "Адрес не указан", "", ""
    
    lines = [line.strip() for line in location_raw.strip().split('\n') if line.strip()]
    
    address = lines[0] if lines else "Адрес не указан"
    
    yandex_url = ""
    if len(lines) > 1:
        match = re.search(r'(https?://\S+)', lines[1])
        yandex_url = match.group(1) if match else lines[1]

    twogis_url = ""
    if len(lines) > 2:
        match = re.search(r'(https?://\S+)', lines[2])
        twogis_url = match.group(1) if match else lines[2]
        
    return address, yandex_url, twogis_url

# --- APScheduler Setup ---
scheduler = AsyncIOScheduler()

async def send_reminder_message(user_id: int, bot: Bot, reminder_text: str):
    try:
        await bot.send_message(user_id, reminder_text)
        logger.info(f"Reminder sent to user {user_id}: {reminder_text}")
    except Exception as e:
        logger.error(f"Failed to send reminder to user {user_id}: {e}", exc_info=True)

async def schedule_reminders(user_id: int, chosen_date_str: str, bot: Bot):
    current_year = datetime.now(MOSCOW_TZ).year
    
    try:
        event_date = datetime.strptime(f"{chosen_date_str}.{current_year}", "%d.%m.%Y").replace(tzinfo=MOSCOW_TZ)
        if event_date < datetime.now(MOSCOW_TZ) - timedelta(days=1):
            event_date = event_date.replace(year=current_year + 1)
    except ValueError:
        try:
            event_date = datetime.strptime(f"{chosen_date_str}.{current_year + 1}", "%d.%m.%Y").replace(tzinfo=MOSCOW_TZ)
        except ValueError:
            logger.error(f"Could not parse date {chosen_date_str}")
            return

    # Reminder 1: 1 day before, 12:00 MSK
    reminder_day_before = event_date - timedelta(days=1)
    reminder_day_before = reminder_day_before.replace(hour=12, minute=0, second=0, microsecond=0)

    # Reminder 2: On the day of the event, 08:00 MSK
    reminder_on_day = event_date.replace(hour=8, minute=0, second=0, microsecond=0)

    now_moscow = datetime.now(MOSCOW_TZ)

    if reminder_day_before > now_moscow:
        scheduler.add_job(
            send_reminder_message,
            "date",
            run_date=reminder_day_before,
            args=[user_id, bot, f"Напоминание: Завтра, <b>{format_date_russian(chosen_date_str)}</b>, у вас запланировано мероприятие!"],
            id=f"reminder_day_before_{user_id}_{chosen_date_str}",
            replace_existing=True,
            misfire_grace_time=600 
        )
        logger.info(f"Scheduled 'day before' reminder for user {user_id} on {chosen_date_str} at {reminder_day_before}")

    if reminder_on_day > now_moscow:
        scheduler.add_job(
            send_reminder_message,
            "date",
            run_date=reminder_on_day,
            args=[user_id, bot, f"Напоминание: Сегодня, <b>{format_date_russian(chosen_date_str)}</b>, у вас запланировано мероприятие! Ждем вас!"],
            id=f"reminder_on_day_{user_id}_{chosen_date_str}",
            replace_existing=True,
            misfire_grace_time=600 
        )
        logger.info(f"Scheduled 'on day' reminder for user {user_id} on {chosen_date_str} at {reminder_on_day}")

async def restore_reminders_from_sheet(bot: Bot):
    logger.info("Starting restoration of reminders from Google Sheet...")
    sheet = get_sheet()
    if not sheet:
        logger.error("Restoration failed: could not get sheet.")
        return
    
    try:
        data = sheet.get_all_values()
        for i, row in enumerate(data[1:], start=2):
            if not row or len(row) < 1:
                continue
            
            date_str = row[0]
            # Simple check for date format DD.MM
            if not re.match(r'\d{1,2}\.\d{1,2}', date_str):
                continue
            
            padded_row = row + [''] * max(0, 5 - len(row))
            for c_idx in range(1, 5):
                cell_content = padded_row[c_idx]
                if not cell_content:
                    continue
                
                # Match ID: 12345 or (ID: 12345)
                match = re.search(r'ID: (\d+)', cell_content)
                if match:
                    user_id = int(match.group(1))
                    await schedule_reminders(user_id, date_str, bot)
                    
        logger.info("Finished restoring reminders from sheet.")
    except Exception as e:
        logger.error(f"Error during reminders restoration: {e}", exc_info=True)

# --- Google Sheets Setup ---
def get_sheet():
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        client = gspread.authorize(creds)
        
        # Open spreadsheet by ID, but worksheet by Name (standard behavior)
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Расписание")
        return sheet
    except Exception as e:
        logger.error(f"Google Sheets connection error: {e}")
        return None

# --- FSM States ---
class BookingStates(StatesGroup):
    choosing_date = State()

# --- Handlers ---
router = Router()

def render_dates_keyboard(available_slots: dict, page: int = 0) -> InlineKeyboardMarkup:
    dates = list(available_slots.items())
    total_pages = (len(dates) + PAGE_SIZE - 1) // PAGE_SIZE
    
    start_idx = page * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    current_page_dates = dates[start_idx:end_idx]
    
    keyboard_buttons = []
    row_buttons = []
    for date, (count, _) in current_page_dates:
        formatted_date = format_date_russian(date)
        formatted_slots = format_slots_russian(count)
        button_text = f"{formatted_date} ({formatted_slots})"
        row_buttons.append(InlineKeyboardButton(text=button_text, callback_data=date))
        if len(row_buttons) == 2:
            keyboard_buttons.append(row_buttons)
            row_buttons = []
    if row_buttons:
        keyboard_buttons.append(row_buttons)

    # Navigation buttons
    nav_buttons = []
    # Previous button
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"nav_prev:{page-1}"))
    
    # Page indicator (always show if pages > 1)
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    
    # Next button
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"nav_next:{page+1}"))
    
    if nav_buttons:
        keyboard_buttons.append(nav_buttons)

    keyboard_buttons.append([InlineKeyboardButton(text="🗓️ Мои события", callback_data="my_events")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

async def find_user_bookings(user_id: int, username: Optional[str]) -> List[Dict]:
    sheet = get_sheet()
    if not sheet: return []
    bookings = []
    try:
        data = sheet.get_all_values()
        user_marker_id = f"ID: {user_id}"
        user_marker_link = f"https://t.me/{username}" if username else None
        
        for r_idx, row in enumerate(data[1:], start=2):
            if row and len(row) > 0:
                date = row[0]
                padded_row = row + [''] * max(0, 5 - len(row))
                for c_idx in range(1, 5):
                    cell = padded_row[c_idx]
                    # Check for ID (new format) OR Link (old format)
                    if (user_marker_id in cell) or (user_marker_link and user_marker_link in cell):
                        bookings.append({
                            "date": date,
                            "row_index": r_idx,
                            "col_index": c_idx,
                            "sheet_name": sheet.title
                        })
    except Exception as e:
        logger.error(f"Error finding bookings: {e}")
    return bookings

@router.message(Command("start"))
async def command_start_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    
    # Dynamic button name from spreadsheet title
    sheet = get_sheet()
    button_text = "Показать свободные даты" # Fallback
    if sheet:
        try:
            button_text = sheet.spreadsheet.title
        except:
            pass

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=button_text, callback_data="show_available_dates")]
    ])
    await message.answer("Добро пожаловать! Нажмите кнопку, чтобы найти свободные даты.", reply_markup=keyboard)

@router.callback_query(lambda query: query.data == "show_available_dates")
async def show_available_dates_callback(callback_query: CallbackQuery, state: FSMContext) -> None:
    await callback_query.answer()
    await callback_query.message.edit_text("Пожалуйста, подождите, ищу свободные даты...")
    await get_and_send_available_dates(callback_query.message, state)

@router.callback_query(lambda c: c.data.startswith("nav_"))
async def navigation_handler(callback_query: CallbackQuery, state: FSMContext):
    try:
        _, page_str = callback_query.data.split(":") # Handle nav_prev:0 or nav_next:1
        page = int(page_str)
        user_data = await state.get_data()
        available_slots = user_data.get("available_slots")
        if not available_slots:
            await callback_query.answer("Данные устарели, обновите список.", show_alert=True)
            return
        
        keyboard = render_dates_keyboard(available_slots, page)
        
        # Only edit if markup changed
        if callback_query.message.reply_markup != keyboard:
            await callback_query.message.edit_reply_markup(reply_markup=keyboard)
        await callback_query.answer()
    except Exception as e:
        logger.error(f"Nav error: {e}")
        await callback_query.answer("Ошибка навигации")

@router.callback_query(lambda c: c.data == "noop")
async def noop_handler(callback_query: CallbackQuery):
    await callback_query.answer()

async def get_and_send_available_dates(message: Message, state: FSMContext) -> None:
    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    sheet = get_sheet()
    if not sheet:
        await message.edit_text("Ошибка подключения к таблице.")
        return
    try:
        sheet_title = sheet.spreadsheet.title # Get spreadsheet name
        data = sheet.get_all_values()
        available_slots = {}
        
        logger.info(f"Scanning sheet '{sheet_title}' for available slots...")
        
        now = datetime.now(MOSCOW_TZ)
        today = now.date()
        found_future_date = False

        for i, row in enumerate(data[1:], start=2):
            if len(row) > 0:
                date = row[0]
                if not date: continue

                # Filter passed dates
                try:
                    # Parse date with current year
                    row_date_dt = datetime.strptime(f"{date}.{now.year}", "%d.%m.%Y")
                    row_date = row_date_dt.date()

                    if not found_future_date:
                        if row_date >= today:
                            found_future_date = True
                        else:
                            # Skip past dates
                            continue
                except ValueError:
                    continue

                padded_row = row + [''] * max(0, 5 - len(row))
                free_slots_count = padded_row[1:5].count("")
                if free_slots_count > 0:
                    available_slots[date] = (free_slots_count, i)
        
        logger.info(f"Found {len(available_slots)} available dates.")

        # Get extra info from G2 (Column G is index 6, Row 2 is index 1)
        extra_info = ""
        if len(data) > 1 and len(data[1]) > 6:
            extra_info = data[1][6].strip()

        # Check if we have slots
        if available_slots:
            await state.update_data(available_slots=available_slots)
            await state.set_state(BookingStates.choosing_date)
            # Render page 0
            keyboard = render_dates_keyboard(available_slots, 0)
            
            # If extra_info (G2) exists, use it in italics. Otherwise use default prompt.
            if extra_info:
                prompt = f"<i>{extra_info}</i>"
            else:
                prompt = "Пожалуйста, выберите дату:"
                
            message_text = f"<b>{sheet_title}</b>\n{prompt}"
                
            await message.edit_text(
                message_text, 
                reply_markup=keyboard
            )
        else:
            await message.edit_text(f"<b>{sheet_title}</b>\nСвободных дат нет.")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await message.edit_text("Произошла ошибка.")

@router.message(Command("my_events"))
@router.callback_query(lambda query: query.data == "my_events")
async def my_events_handler(update: Message | CallbackQuery, state: FSMContext) -> None:
    user = update.from_user
    msg = update if isinstance(update, Message) else update.message
    if isinstance(update, CallbackQuery): await update.answer()
    
    bookings = await find_user_bookings(user.id, user.username)
    if bookings:
        resp = "Ваши активные записи:\nДля отмены нажмите на кнопку с датой."
        kb_rows = []
        for b in bookings:
            date_label = format_date_russian(b['date'])
            kb_rows.append([InlineKeyboardButton(text=f"❌ Отменить {date_label}", callback_data=f"cancel:{b['date']}")])
        
        kb_rows.append([InlineKeyboardButton(text="🗓️ Показать свободные даты", callback_data="show_available_dates")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=kb_rows)
        await msg.answer(resp, reply_markup=keyboard)
    else:
        await msg.answer("У вас нет активных записей.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗓️ Показать свободные даты", callback_data="show_available_dates")]
        ]))

# Redirect change_date to my_events to show cancel list
@router.callback_query(lambda query: query.data == "change_date")
async def change_date_button_handler(callback_query: CallbackQuery, state: FSMContext) -> None:
    await my_events_handler(callback_query, state)

@router.callback_query(lambda c: c.data.startswith("cancel:"))
async def cancel_specific_booking_handler(callback_query: CallbackQuery, state: FSMContext) -> None:
    await callback_query.answer("Отменяю...")
    _, date_to_cancel = callback_query.data.split(":")
    user_id = callback_query.from_user.id
    username = callback_query.from_user.username
    
    sheet = get_sheet()
    if not sheet: return

    try:
        data = sheet.get_all_values()
        user_marker_id = f"ID: {user_id}"
        user_marker_link = f"https://t.me/{username}" if username else None
        updated = False
        
        for r_idx, row in enumerate(data[1:], start=2):
            if row[0] == date_to_cancel:
                padded_row = row + [''] * max(0, 5 - len(row))
                for c_idx in range(1, 5):
                    cell = padded_row[c_idx]
                    # Match by ID or Link (for old bookings)
                    if (user_marker_id in cell) or (user_marker_link and user_marker_link in cell):
                        sheet.update_acell(f"{chr(ord('A') + c_idx)}{r_idx}", "")
                        updated = True
                        break
            if updated: break
        
        if updated:
            try:
                scheduler.remove_job(f"reminder_day_before_{user_id}_{date_to_cancel}")
                scheduler.remove_job(f"reminder_on_day_{user_id}_{date_to_cancel}")
            except: pass
            
            await callback_query.message.answer(f"Запись на <b>{format_date_russian(date_to_cancel)}</b> успешно отменена. ✅")
            await get_and_send_available_dates(callback_query.message, state)
        else:
            await callback_query.message.answer("Не удалось найти эту запись для отмены.")
            await get_and_send_available_dates(callback_query.message, state)
    except Exception as e:
        logger.error(f"Cancel error: {e}")

# STRICT FILTER: Only handle DD.MM patterns in this handler to avoid eating "my_events"
@router.callback_query(BookingStates.choosing_date, F.data.regexp(r"^\d{2}\.\d{2}$"))
async def choose_date_handler(callback_query: CallbackQuery, state: FSMContext) -> None:
    chosen_date = callback_query.data
    user_id = callback_query.from_user.id
    username = callback_query.from_user.username
    
    user_data = await state.get_data()
    available_slots = user_data.get("available_slots", {})
    
    if chosen_date not in available_slots:
        await callback_query.answer("Дата недоступна.", show_alert=True)
        return

    await callback_query.answer()
    await callback_query.message.bot.send_chat_action(chat_id=callback_query.message.chat.id, action=ChatAction.TYPING)
    _, row_index = available_slots[chosen_date]
    sheet = get_sheet()
    if not sheet: return

    try:
        data = sheet.get_all_values()
        row_from_sheet = data[row_index - 1]
        padded_row = row_from_sheet + [''] * max(0, 5 - len(row_from_sheet))
        
        user_marker_id = f"ID: {user_id}"
        user_marker_link = f"https://t.me/{username}" if username else None
        
        for j in range(1, 5):
            cell_content = padded_row[j]
            if (user_marker_id in cell_content) or (user_marker_link and user_marker_link in cell_content):
                await callback_query.message.answer(f"Вы уже записаны на <b>{format_date_russian(chosen_date)}</b>! ✅")
                await my_events_handler(callback_query, state)
                return

        for j in range(1, 5):
            if padded_row[j] == "":
                cell_to_update = f"{chr(ord('A') + j)}{row_index}"
                user_link = f"https://t.me/{username}" if username else "Без ника"
                user_info_to_save = f"{user_link}\n(ID: {user_id})"
                
                sheet.update_acell(cell_to_update, user_info_to_save)
                
                location_raw = sheet.acell('F2').value
                displayed_location, yandex_maps_link, two_gis_link = parse_location_info(location_raw)

                combined_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🗺️ Yandex Maps", url=yandex_maps_link)],
                    [InlineKeyboardButton(text="📍 2GIS", url=two_gis_link)],
                    [InlineKeyboardButton(text="🗓️ Мои события", callback_data="my_events")]
                ])

                await callback_query.message.answer(
                    f"Отлично! Вы записаны на <b>{format_date_russian(chosen_date)}</b>! ✅\n\nАдрес: <b>{displayed_location}</b>",
                    reply_markup=combined_keyboard
                )
                await schedule_reminders(user_id, chosen_date, callback_query.bot)
                return
        await callback_query.message.answer("Извините, места уже заняли.")
    except Exception as e:
        logger.error(f"Error booking: {e}")

async def main() -> None:
    dp = Dispatcher()
    dp.include_router(router)
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    scheduler.start()
    asyncio.create_task(restore_reminders_from_sheet(bot))
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
