declare module "*.css";

interface Window {
  Telegram?: {
    WebApp: {
      initData: string;
      initDataUnsafe: { start_param?: string; user?: { id: number; username?: string } };
      ready: () => void;
      expand: () => void;
      close: () => void;
      openTelegramLink: (url: string) => void;
      openLink: (url: string) => void;
      HapticFeedback?: { notificationOccurred: (t: string) => void };
      colorScheme?: string;
    };
  };
}
