// /home/ckdnovosib/bbk/bbk_miniapps/frontend/types/api.d.ts

export interface Slot {
    id: number;
    label: string;
    status: "available" | "booked";
    booked_by?: string;
    establishment_id: string;
    establishment_name: string;
    establishment_category?: string;
}

export interface Establishment {
    id: string;
    name: string;
    schedule_sheet_id: string;
    schedule_worksheet_name: string;
    category?: string;
}

export interface ScheduleResponse {
    schedule: Slot[];
}

export interface BookingRequest {
    telegram_user_id: string;
    telegram_username?: string;
    date: string;
    slot_id: number;
    establishment_id: string;
}

export interface BookingRecord {
    date: string;
    slot_label: string;
    user_info: string;
    establishment_id: string;
    establishment_name: string;
}

export interface MyBookingsResponse {
    bookings: BookingRecord[];
}
