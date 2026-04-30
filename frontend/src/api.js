import { authHeaders } from "./lib/tgAuth";

async function fetchWithAuth(url, opts = {}) {
  const baseHeaders = opts.headers || {};
  const headers = { ...baseHeaders, ...authHeaders() };
  return await fetch(url, { ...opts, headers });
}

async function readError(res, fallback) {
  let payload = "";
  try {
    payload = await res.text();
  } catch {
    payload = "";
  }
  if (payload) {
    let parsed = null;
    try {
      parsed = JSON.parse(payload);
    } catch {
      parsed = null;
    }
    if (parsed?.detail) throw new Error(String(parsed.detail));
    if (parsed?.message) throw new Error(String(parsed.message));
  }
  throw new Error(payload || fallback);
}

export async function apiGetMe() {
  const res = await fetchWithAuth("/api/me");
  if (!res.ok) await readError(res, `Me HTTP ${res.status}`);
  return await res.json();
}

export async function apiCheckAccess(traderId) {
  const res = await fetchWithAuth("/api/access/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ trader_id: traderId }),
  });
  if (!res.ok) await readError(res, `Access check HTTP ${res.status}`);
  return await res.json();
}

export async function apiGetPublicSettings() {
  const res = await fetchWithAuth("/api/settings/public");
  if (!res.ok) await readError(res, `Settings HTTP ${res.status}`);
  return await res.json();
}

export async function apiAdminMe() {
  const res = await fetchWithAuth("/api/admin/me");
  if (!res.ok) await readError(res, `Admin me HTTP ${res.status}`);
  return await res.json();
}

export async function apiAdminSettings() {
  const res = await fetchWithAuth("/api/admin/settings");
  if (!res.ok) await readError(res, `Admin settings HTTP ${res.status}`);
  return await res.json();
}

export async function apiAdminSetSetting(key, value) {
  const res = await fetchWithAuth("/api/admin/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  });
  if (!res.ok) await readError(res, `Admin set setting HTTP ${res.status}`);
  return await res.json();
}

export async function apiAdminStatuses() {
  const res = await fetchWithAuth("/api/admin/statuses");
  if (!res.ok) await readError(res, `Admin statuses HTTP ${res.status}`);
  return await res.json();
}

export async function apiAdminUpsertStatus(payload) {
  const res = await fetchWithAuth("/api/admin/statuses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) await readError(res, `Admin upsert status HTTP ${res.status}`);
  return await res.json();
}

export async function apiAdminList() {
  const res = await fetchWithAuth("/api/admin/list");
  if (!res.ok) await readError(res, `Admin list HTTP ${res.status}`);
  return await res.json();
}

export async function apiAdminUpsertUser(payload) {
  const res = await fetchWithAuth("/api/admin/users/upsert", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) await readError(res, `Admin upsert user HTTP ${res.status}`);
  return await res.json();
}

export async function apiAdminBroadcastDraft(payload) {
  const res = await fetchWithAuth("/api/admin/broadcast/draft", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) await readError(res, `Admin broadcast draft HTTP ${res.status}`);
  return await res.json();
}
