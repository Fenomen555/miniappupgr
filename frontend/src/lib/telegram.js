export function getUid({ allowQueryInDev = false } = {}) {
  const tg = window.Telegram?.WebApp;
  const id = tg?.initDataUnsafe?.user?.id;
  if (id) return id;

  // Разрешить ручной uid только локально при отладке:
  if (allowQueryInDev && import.meta?.env?.DEV) {
    const url = new URL(window.location.href);
    const uid = url.searchParams.get("uid");
    if (uid) return Number(uid);
  }

  // В проде — строго ошибка, чтобы не продолжать без Telegram-контекста
  throw new Error("No Telegram context: user id is not available.");
}