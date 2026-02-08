from pydantic import BaseModel
from typing import Optional, List

class Slot(BaseModel):
    id: int
    label: str
    status: str # "available" or "booked"
    booked_by: Optional[str] = None # User info if booked
    # Removed establishment information fields
    # For now, we assume a single establishment context, so these are not needed in Slot directly.
    # If a specific slot needs to convey its establishment, it would be added here.

class ScheduleResponse(BaseModel):
    # Schedule will now be a list of slots for a single establishment
    schedule: List[Slot]

class BookingRequest(BaseModel):
    telegram_user_id: str
    telegram_username: Optional[str] = None
    date: str
    slot_id: int
    # Removed establishment_id

class BookingRecord(BaseModel):
    date: str
    slot_label: str
    user_info: str
    # Removed establishment_id and establishment_name for single establishment context

class MyBookingsResponse(BaseModel):
    bookings: List[BookingRecord]