"use client";

import React, { createContext, useContext, useEffect, useState, ReactNode } from "react";

// Extend the Window interface to include Telegram.WebApp
declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        initData: string;
        initDataUnsafe: any; // More specific type can be added later
        onEvent: (eventType: string, callback: (...args: any[]) => void) => void;
        offEvent: (eventType: string, callback: (...args: any[]) => void) => void;
        ready: () => void;
        expand: () => void;
        close: () => void;
        isExpanded: boolean;
        viewportHeight: number;
        viewportStableHeight: number;
        headerColor: string;
        backgroundColor: string;
        themeParams: any; // ThemeParams type
        BackButton: any; // BackButton type
        MainButton: any; // MainButton type
        HapticFeedback: any; // HapticFeedback type
        isVersionAtLeast: (version: string) => boolean;
        colorScheme: 'light' | 'dark';
        openLink: (url: string) => void;
        openTelegramLink: (url: string) => void;
        openInvoice: (url: string, callback: (status: string) => void) => void;
        showPopup: (params: any, callback?: (id?: string) => void) => void;
        showAlert: (message: string, callback?: () => void) => void;
        showConfirm: (message: string, callback?: (confirmed: boolean) => void) => void;
        requestWriteAccess: (callback: (allowed: boolean) => void) => void;
        requestContact: (callback: (allowed: boolean) => void) => void;
        [key: string]: any; // Allow other properties
      };
    };
  }
}

interface TelegramWebAppInitData {
  initData: string | null;
  initDataUnsafe: any | null;
  isReady: boolean;
  WebApp: typeof window.Telegram.WebApp | null;
}

const TelegramWebApp = createContext<TelegramWebAppInitData>({
  initData: null,
  initDataUnsafe: null,
  isReady: false,
  WebApp: null,
});

export const useTelegramWebApp = () => useContext(TelegramWebApp);

interface TelegramWebAppProviderProps {
  children: ReactNode;
}

export const TelegramWebAppProvider: React.FC<TelegramWebAppProviderProps> = ({ children }) => {
  const [initData, setInitData] = useState<string | null>(null);
  const [initDataUnsafe, setInitDataUnsafe] = useState<any | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [webApp, setWebApp] = useState<typeof window.Telegram.WebApp | null>(null);

  useEffect(() => {
    // Check if the Telegram WebApp script is already loaded
    if (window.Telegram && window.Telegram.WebApp) {
      console.log("Telegram WebApp script already loaded.");
      setInitData(window.Telegram.WebApp.initData);
      setInitDataUnsafe(window.Telegram.WebApp.initDataUnsafe);
      setWebApp(window.Telegram.WebApp);
      window.Telegram.WebApp.ready();
      setIsReady(true);
      return;
    }

    // Dynamically load the Telegram WebApp script
    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-web-app.js";
    script.async = true;
    script.onload = () => {
      if (window.Telegram && window.Telegram.WebApp) {
        console.log("Telegram WebApp script loaded successfully.");
        setInitData(window.Telegram.WebApp.initData);
        setInitDataUnsafe(window.Telegram.WebApp.initDataUnsafe);
        setWebApp(window.Telegram.WebApp);
        window.Telegram.WebApp.ready();
        setIsReady(true);
      } else {
        console.warn("Telegram WebApp object not found after script load.");
      }
    };
    script.onerror = (error) => {
      console.error("Failed to load Telegram WebApp script:", error);
      setIsReady(true); // Still set ready to true to unblock UI, even if WebApp failed to load
    };
    document.head.appendChild(script);

    return () => {
      // Clean up the script if the component unmounts
      if (document.head.contains(script)) {
        document.head.removeChild(script);
      }
    };
  }, []);

  return (
    <TelegramWebApp.Provider value={{ initData, initDataUnsafe, isReady, WebApp: webApp }}>
      {children}
    </TelegramWebApp.Provider>
  );
};
