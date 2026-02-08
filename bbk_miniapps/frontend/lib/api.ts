// /home/ckdnovosib/bbk/bbk_miniapps/frontend/lib/api.ts

import { ScheduleResponse, BookingRequest, MyBookingsResponse } from '../types/api'; // Assuming types are defined here soon

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

if (!BACKEND_URL) {
    console.error("NEXT_PUBLIC_BACKEND_URL is not defined!");
}

export const fetchSchedule = async (): Promise<ScheduleResponse> => {
    const response = await fetch(`${BACKEND_URL}/api/schedule`);
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to fetch schedule");
    }
    return response.json();
};

export const bookSlot = async (bookingData: BookingRequest): Promise<{ message: string }> => {
    const response = await fetch(`${BACKEND_URL}/api/book`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(bookingData),
    });
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to book slot");
    }
    return response.json();
};

export const fetchMyBookings = async (telegramUserId: string): Promise<MyBookingsResponse> => {
    const response = await fetch(`${BACKEND_URL}/api/my-bookings?telegram_user_id=${telegramUserId}`);
    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to fetch my bookings");
    }
    return response.json();
};
