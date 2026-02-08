"use client";

import { useEffect, useState } from "react";
import { useTelegramWebApp } from "../components/telegram-webapp-provider";
import { fetchSchedule, bookSlot, fetchMyBookings } from "../lib/api";
import { Slot, ScheduleResponse, BookingRequest, MyBookingsResponse } from "../types/api";

export default function Home() {
  const { initData, initDataUnsafe, isReady, WebApp } = useTelegramWebApp();
  const [schedule, setSchedule] = useState<Slot[]>([]);
  const [myBookings, setMyBookings] = useState<BookingRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"schedule" | "my_bookings">("schedule");
  const telegramUserId = initDataUnsafe?.user?.id?.toString();

  useEffect(() => {
    if (isReady && WebApp) {
      WebApp.ready();
      WebApp.expand();
    }
  }, [isReady, WebApp]);

  useEffect(() => {
    if (!isReady || !telegramUserId) {
        setLoading(false);
        if (isReady && !telegramUserId) {
            setError("Telegram User ID not available. Please open this app within Telegram.");
        }
        return;
    }

    const loadData = async () => {
      setLoading(true);
      setError(null);
      try {
        const scheduleData: ScheduleResponse = await fetchSchedule();
        setSchedule(scheduleData.schedule);
        
        const bookingsData: MyBookingsResponse = await fetchMyBookings(telegramUserId);
        setMyBookings(bookingsData.bookings);
      } catch (err: any) {
        setError(err.message || "Ошибка загрузки данных");
        console.error("Ошибка:", err);
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [isReady, telegramUserId]);

  const handleBookSlot = async (slot: Slot) => {
    if (!telegramUserId) {
      alert("Не удалось получить ID пользователя Telegram.");
      return;
    }

    if (!confirm(`Вы уверены, что хотите записаться в "${slot.establishment_name}" на ${slot.date} (${slot.label})?`)) {
        return;
    }

    try {
      const bookingRequest: BookingRequest = {
        telegram_user_id: telegramUserId,
        telegram_username: initDataUnsafe?.user?.username,
        date: slot.date,
        slot_id: slot.id,
        establishment_id: slot.establishment_id,
      };
      await bookSlot(bookingRequest);
      alert("Запись успешно создана!");
      // Reload data after successful booking
      const scheduleData: ScheduleResponse = await fetchSchedule();
      setSchedule(scheduleData.schedule);
      const bookingsData: MyBookingsResponse = await fetchMyBookings(telegramUserId);
      setMyBookings(bookingsData.bookings);
    } catch (err: any) {
      alert(`Ошибка при записи: ${err.message}`);
      console.error("Ошибка бронирования:", err);
    }
  };

  if (!isReady) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-100 dark:bg-gray-900 text-gray-800 dark:text-gray-200">
        <p>Загрузка Telegram WebApp SDK...</p>
      </div>
    );
  }

  if (!WebApp) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-gray-100 dark:bg-gray-900 p-4 text-gray-800 dark:text-gray-200 text-center">
        <h1 className="text-2xl font-bold mb-4">Приложение не запущено в Telegram WebApp</h1>
        <p className="mb-2">Это приложение предназначено для запуска внутри Telegram Mini App.</p>
        <p className="text-sm break-all">Init Data: {initData || "N/A"}</p>
        <p className="text-sm break-all">Init Data Unsafe: {JSON.stringify(initDataUnsafe) || "N/A"}</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-100 dark:bg-gray-900 text-gray-800 dark:text-gray-200">
        <p>Загрузка данных...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-gray-100 dark:bg-gray-900 p-4 text-red-600">
        <p className="text-lg font-semibold">Ошибка:</p>
        <p className="text-sm text-center">{error}</p>
        <p className="mt-4 text-gray-700">Пожалуйста, убедитесь, что бэкенд запущен и Google Таблицы настроены правильно.</p>
      </div>
    );
  }

  // Group slots by establishment and then by date for easier display
  const groupedSchedule = schedule.reduce((acc, slot) => {
    if (!acc[slot.establishment_name]) {
      acc[slot.establishment_name] = {};
    }
    if (!acc[slot.establishment_name][slot.date]) {
      acc[slot.establishment_name][slot.date] = [];
    }
    acc[slot.establishment_name][slot.date].push(slot);
    return acc;
  }, {} as Record<string, Record<string, Slot[]>>);

  const sortedDates = (dates: string[]) => dates.sort((a, b) => new Date(a).getTime() - new Date(b).getTime());

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900 text-gray-800 dark:text-gray-200">
      <header className="bg-blue-600 p-4 text-white shadow-md">
        <h1 className="text-xl font-bold text-center">Запись на Встречи</h1>
      </header>

      <div className="flex justify-center bg-gray-200 dark:bg-gray-800 p-2">
        <button
          onClick={() => setActiveTab("schedule")}
          className={`px-4 py-2 mx-1 rounded-md transition-colors ${
            activeTab === "schedule" ? "bg-blue-600 text-white" : "bg-gray-300 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-400 dark:hover:bg-gray-600"
          }`}
        >
          Расписание
        </button>
        <button
          onClick={() => setActiveTab("my_bookings")}
          className={`px-4 py-2 mx-1 rounded-md transition-colors ${
            activeTab === "my_bookings" ? "bg-blue-600 text-white" : "bg-gray-300 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-400 dark:hover:bg-gray-600"
          }`}
        >
          Мои Записи
        </button>
      </div>

      <main className="p-4">
        {activeTab === "schedule" && (
          <section className="mb-8">
            <h2 className="text-lg font-semibold mb-4">Доступные Слоты</h2>
            {Object.keys(groupedSchedule).length === 0 ? (
                <p className="text-center text-gray-600 dark:text-gray-400">Нет доступных слотов или заведений.</p>
            ) : (
                Object.entries(groupedSchedule).map(([estName, dates]) => (
                    <div key={estName} className="bg-white dark:bg-gray-800 shadow-md rounded-lg p-4 mb-6">
                        <h3 className="text-xl font-bold text-blue-700 dark:text-blue-300 mb-4">{estName}</h3>
                        {sortedDates(Object.keys(dates)).map(date => (
                            <div key={date} className="mb-4 border-b border-gray-200 dark:border-gray-700 pb-2 last:border-b-0">
                                <h4 className="text-md font-semibold mb-2">{date}</h4>
                                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
                                    {dates[date].map(slot => (
                                        <button
                                            key={`${slot.establishment_id}-${slot.date}-${slot.id}`}
                                            onClick={() => handleBookSlot(slot)}
                                            disabled={slot.status === "booked"}
                                            className={`p-3 rounded-lg text-sm font-medium transition-colors ${
                                                slot.status === "available"
                                                    ? "bg-green-500 hover:bg-green-600 text-white"
                                                    : "bg-red-400 text-white cursor-not-allowed opacity-70"
                                            }`}
                                        >
                                            {slot.label} {slot.status === "booked" && "(Занято)"}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                ))
            )}
          </section>
        )}

        {activeTab === "my_bookings" && (
          <section>
            <h2 className="text-lg font-semibold mb-4">Мои Записи</h2>
            {myBookings.length === 0 ? (
              <p className="text-center text-gray-600 dark:text-gray-400">У вас пока нет записей.</p>
            ) : (
              <div className="space-y-4">
                {myBookings.map((booking, index) => (
                  <div key={index} className="bg-white dark:bg-gray-800 shadow-md rounded-lg p-4">
                    <p className="font-semibold text-blue-700 dark:text-blue-300">{booking.establishment_name}</p>
                    <p>Дата: <span className="font-medium">{booking.date}</span></p>
                    <p>Время: <span className="font-medium">{booking.slot_label}</span></p>
                    {/* <p className="text-sm text-gray-500 dark:text-gray-400">Записан: {booking.user_info}</p> */}
                  </div>
                ))}
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
