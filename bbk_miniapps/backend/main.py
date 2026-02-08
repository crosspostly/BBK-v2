import logging
import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from schemas import (
    ScheduleResponse,
    BookingRequest,
    MyBookingsResponse,
    Slot,
    BookingRecord,
)


# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")
GOOGLE_WORKSHEET_NAME = os.getenv("GOOGLE_WORKSHEET_NAME")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID") # New: Using Sheet ID directly
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_WEBAPP_URL = os.getenv("TELEGRAM_WEBAPP_URL")

ADMIN_TELEGRAM_IDS = [int(id.strip()) for id in os.getenv("ADMIN_TELEGRAM_IDS", "").split(',') if id.strip()]

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

# --- FastAPI App Setup ---
app = FastAPI()

# Add CORS middleware to allow requests from the Telegram Mini App frontend
origins = [
    "*", # Temporarily allow all origins for development
    # TELEGRAM_WEBAPP_URL, # Uncomment and configure in production
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Telegram Bot Client ---
telegram_bot = None
if TELEGRAM_BOT_TOKEN:
    telegram_bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
else:
    logger.warning("TELEGRAM_BOT_TOKEN not found in .env. Telegram notifications will be disabled.")

# --- Google Sheets Setup ---
def get_sheet_client():
    logger.info("Attempting to get Google Sheet client.")
    try:
        full_credentials_path = os.path.join(os.path.dirname(__file__), GOOGLE_CREDENTIALS_PATH)
        if not os.path.exists(full_credentials_path):
            logger.error(f"Credentials file not found at: {full_credentials_path}")
            raise FileNotFoundError(f"credentials.json not found at {full_credentials_path}")

        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(full_credentials_path, scope)
        client = gspread.authorize(creds)
        logger.info("Successfully connected to Google Sheet client.")
        return client
    except Exception as e:
        logger.error(f"Google Sheets client error: {e}", exc_info=True)
        return None

# Reverted to single sheet operations
def get_worksheet():
    client = get_sheet_client()
    if not client:
        return None
    try:
        spreadsheet = client.open_by_key(GOOGLE_SHEET_ID) # Open by ID
        worksheet = spreadsheet.worksheet(GOOGLE_WORKSHEET_NAME)
        logger.info(f"Successfully opened worksheet '{GOOGLE_WORKSHEET_NAME}' in spreadsheet ID '{GOOGLE_SHEET_ID}'.")
        return worksheet
    except gspread.exceptions.SpreadsheetNotFound:
        logger.error(f"Spreadsheet ID '{GOOGLE_SHEET_ID}' not found.", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Spreadsheet ID '{GOOGLE_SHEET_ID}' not found.")
    except gspread.exceptions.WorksheetNotFound:
        logger.error(f"Worksheet '{GOOGLE_WORKSHEET_NAME}' not found in spreadsheet ID '{GOOGLE_SHEET_ID}'.", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Worksheet '{GOOGLE_WORKSHEET_NAME}' not found in spreadsheet ID '{GOOGLE_SHEET_ID}'.")
    except Exception as e:
        logger.error(f"Error getting worksheet: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error connecting to Google Sheet.")


@app.get("/")
async def read_root():
    return {"message": "Telegram Mini App Backend is running!"}

@app.get("/api/schedule", response_model=ScheduleResponse)
async def get_schedule():
    worksheet = get_worksheet()
    if not worksheet:
        raise HTTPException(status_code=500, detail="Could not connect to Google Sheet.")
    
    all_slots: List[Slot] = []

    try:
        data = worksheet.get_all_values()
        # Assuming the first row is headers and column A is Date
        # Columns B, C, D, E are slots
        for i, row in enumerate(data[1:], start=2): # `start=2` means 1-based row index in sheet
            if len(row) > 0:
                date_str = row[0]
                try:
                    datetime.strptime(date_str, '%Y-%m-%d') # Assuming YYYY-MM-DD format
                except ValueError:
                    logger.warning(f"Skipping row {i} in schedule: Invalid date format '{date_str}'")
                    continue

                padded_row = row + [''] * max(0, 5 - len(row))
                
                for j in range(1, 5): # Column indices 1-4 correspond to B-E
                    slot_label = f"Время {j}" # Placeholder, ideally from sheet headers or config
                    slot_status = "available" if padded_row[j] == "" else "booked"
                    
                    all_slots.append(Slot(
                        id=j,
                        label=slot_label,
                        status=slot_status,
                        booked_by=padded_row[j] if slot_status == "booked" else None,
                    ))
        
        return ScheduleResponse(schedule=all_slots)
    except Exception as e:
        logger.error(f"Error fetching schedule: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error fetching schedule from Google Sheet.")


@app.post("/api/book")
async def book_slot(booking_data: BookingRequest):
    worksheet = get_worksheet()
    if not worksheet:
        raise HTTPException(status_code=500, detail="Could not connect to Google Sheet for booking.")
    
    try:
        data = worksheet.get_all_values()
        user_info = f"ID:{booking_data.telegram_user_id}"
        if booking_data.telegram_username:
            user_info = f"@{booking_data.telegram_username} (ID:{booking_data.telegram_user_id})"

        # Find the row for the chosen date
        for i, row in enumerate(data[1:], start=2): # `start=2` for 1-based sheet row
            if row and row[0] == booking_data.date:
                column_index = booking_data.slot_id 
                if not (1 <= column_index <= 4):
                    raise HTTPException(status_code=400, detail="Invalid slot ID.")

                current_slot_value = (row + [''] * max(0, 5 - len(row)))[column_index]
                if current_slot_value != "":
                    raise HTTPException(status_code=409, detail="Slot is already booked.")
                
                cell_to_update = f"{chr(ord('A') + column_index)}{i}"
                worksheet.update_acell(cell_to_update, user_info)
                
                # Send Telegram notification
                if telegram_bot:
                    try:
                        slot_label = f"Время {booking_data.slot_id}" # Improve this with actual labels later
                        message_text = (
                            f"✅ Вы успешно записаны на {booking_data.date} на {slot_label}!\n"
                            f"Ваша запись: {user_info}"
                        )
                        await telegram_bot.send_message(chat_id=booking_data.telegram_user_id, text=message_text)
                    except Exception as e:
                        logger.error(f"Failed to send Telegram notification to user {booking_data.telegram_user_id}: {e}")

                return {"message": f"Successfully booked slot {booking_data.slot_id} on {booking_data.date}"}
                        
        raise HTTPException(status_code=404, detail=f"Date '{booking_data.date}' not found or no available slots on this date.")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"An error occurred during booking: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error processing booking.")

@app.get("/api/my-bookings", response_model=MyBookingsResponse)
async def get_my_bookings(telegram_user_id: str):
    worksheet = get_worksheet()
    if not worksheet:
        raise HTTPException(status_code=500, detail="Could not connect to Google Sheet.")
    
    user_bookings: List[BookingRecord] = []
    user_id_search_string = f"ID:{telegram_user_id}"

    try:
        data = worksheet.get_all_values()
        for i, row in enumerate(data[1:], start=2):
            if len(row) > 0:
                date_str = row[0]
                padded_row = row + [''] * max(0, 5 - len(row))
                
                for j in range(1, 5): # Columns B-E
                    booked_by_info = padded_row[j]
                    if user_id_search_string in booked_by_info:
                        slot_label = f"Время {j}"
                        user_bookings.append(BookingRecord(
                            date=date_str,
                            slot_label=slot_label,
                            user_info=booked_by_info,
                        ))
        
        return MyBookingsResponse(bookings=user_bookings)

    except Exception as e:
        logger.error(f"Error fetching user bookings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error fetching user bookings.")
