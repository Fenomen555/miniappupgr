let _tgInitData = null;

export function setInitData(v) {
  _tgInitData = typeof v === "string" ? v : null;
}

export function getInitData() {
  if (_tgInitData) return _tgInitData;
  const tg = typeof window !== "undefined" ? window.Telegram?.WebApp : undefined;
  return tg?.initData || null;
}

export function authHeaders() {
  const initData = getInitData();
  return initData ? { "X-TG-Init-Data": initData } : {};
}
