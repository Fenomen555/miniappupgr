import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import AdminApp from "./admin/AdminApp.jsx";
import "./index.css";
import { setInitData } from "./lib/tgAuth";

function OpenInTelegram() {
  return (
    <div className="support-page" style={{ display: "grid", placeItems: "center", minHeight: "100vh" }}>
      <section className="support-card" style={{ textAlign: "center" }}>
        <h2>Open this app from Telegram</h2>
        <p className="muted">Access is available only from Telegram WebApp.</p>
      </section>
    </div>
  );
}

function mount(el, node) {
  createRoot(el).render(node);
}

function isAdminPath(pathname) {
  const path = (pathname || "/").replace(/\/+$/, "") || "/";
  return path !== "/" && path !== "/index.html";
}

function isMobileTelegram(tg) {
  const p = String(tg?.platform || "").toLowerCase();
  if (p === "android" || p === "ios") return true;
  if (p) return false;
  return /android|iphone|ipad|ipod|mobile/i.test(navigator.userAgent || "");
}

function applyDeviceClasses(tg) {
  const root = document.documentElement;
  const platform = String(tg?.platform || "").toLowerCase();
  const ua = navigator.userAgent || "";
  const uaMobile = /android|iphone|ipad|ipod|mobile/i.test(ua);
  const touch = (navigator.maxTouchPoints || 0) > 0;
  const smallViewport = window.matchMedia("(max-width: 920px)").matches;
  const tgMobile = platform === "android" || platform === "ios";
  const mobile = tgMobile || (!platform && (uaMobile || (smallViewport && touch)));

  root.classList.remove(
    "device-mobile",
    "device-desktop",
    "tg-platform-android",
    "tg-platform-ios",
    "tg-platform-desktop",
    "tg-platform-web",
    "tg-platform-unknown"
  );

  root.classList.add(mobile ? "device-mobile" : "device-desktop");
  root.classList.add(`tg-platform-${platform || "unknown"}`);
}

function applySafeAreaVars(tg) {
  const root = document.documentElement;
  const safe = tg?.safeAreaInset || {};
  const content = tg?.contentSafeAreaInset || {};
  const css = getComputedStyle(root);

  const cssSafeTop = parseFloat(css.getPropertyValue("--tg-safe-area-inset-top")) || 0;
  const cssSafeRight = parseFloat(css.getPropertyValue("--tg-safe-area-inset-right")) || 0;
  const cssSafeBottom = parseFloat(css.getPropertyValue("--tg-safe-area-inset-bottom")) || 0;
  const cssSafeLeft = parseFloat(css.getPropertyValue("--tg-safe-area-inset-left")) || 0;

  const cssContentTop = parseFloat(css.getPropertyValue("--tg-content-safe-area-inset-top")) || 0;
  const cssContentRight = parseFloat(css.getPropertyValue("--tg-content-safe-area-inset-right")) || 0;
  const cssContentBottom = parseFloat(css.getPropertyValue("--tg-content-safe-area-inset-bottom")) || 0;
  const cssContentLeft = parseFloat(css.getPropertyValue("--tg-content-safe-area-inset-left")) || 0;

  const safeTop = Math.max(Number(safe.top) || 0, cssSafeTop);
  const safeRight = Math.max(Number(safe.right) || 0, cssSafeRight);
  const safeBottom = Math.max(Number(safe.bottom) || 0, cssSafeBottom);
  const safeLeft = Math.max(Number(safe.left) || 0, cssSafeLeft);

  const contentTop = Math.max(Number(content.top) || 0, cssContentTop);
  const contentRight = Math.max(Number(content.right) || 0, cssContentRight);
  const contentBottom = Math.max(Number(content.bottom) || 0, cssContentBottom);
  const contentLeft = Math.max(Number(content.left) || 0, cssContentLeft);

  root.style.setProperty("--tg-safe-top", `${safeTop}px`);
  root.style.setProperty("--tg-safe-right", `${safeRight}px`);
  root.style.setProperty("--tg-safe-bottom", `${safeBottom}px`);
  root.style.setProperty("--tg-safe-left", `${safeLeft}px`);

  root.style.setProperty("--tg-content-safe-top", `${contentTop}px`);
  root.style.setProperty("--tg-content-safe-right", `${contentRight}px`);
  root.style.setProperty("--tg-content-safe-bottom", `${contentBottom}px`);
  root.style.setProperty("--tg-content-safe-left", `${contentLeft}px`);
}

function setupTelegramFullscreen(tg) {
  if (!tg || !isMobileTelegram(tg)) return;

  try {
    tg.expand?.();
  } catch {
    // ignore
  }
  try {
    tg.setHeaderColor?.("#051327");
  } catch {
    // ignore
  }

  const canRequestFullscreen =
    typeof tg.requestFullscreen === "function" &&
    (typeof tg.isVersionAtLeast !== "function" || tg.isVersionAtLeast("8.0"));

  if (canRequestFullscreen && !tg.isFullscreen) {
    try {
      tg.requestFullscreen();
    } catch (e) {
      console.warn("[TG fullscreen] request failed", e);
    }
  }

  try {
    tg.requestSafeArea?.();
  } catch {
    // ignore
  }
  try {
    tg.requestContentSafeArea?.();
  } catch {
    // ignore
  }

  applySafeAreaVars(tg);
  if (typeof tg.onEvent === "function") {
    tg.onEvent("safeAreaChanged", () => applySafeAreaVars(tg));
    tg.onEvent("contentSafeAreaChanged", () => applySafeAreaVars(tg));
    tg.onEvent("fullscreenChanged", () => applySafeAreaVars(tg));
    tg.onEvent("fullscreenFailed", (payload) => {
      console.warn("[TG fullscreen] failed", payload?.error || payload);
    });
  }
}

async function boot() {
  const el = document.getElementById("root");
  if (!el) return;

  if (document.readyState === "loading") {
    await new Promise((resolve) => document.addEventListener("DOMContentLoaded", resolve, { once: true }));
  }

  const tg = window.Telegram?.WebApp;
  if (!tg) {
    mount(el, <OpenInTelegram />);
    return;
  }

  try {
    tg.ready();
  } catch {
    // ignore
  }
  applyDeviceClasses(tg);
  window.addEventListener("resize", () => applyDeviceClasses(tg));
  setupTelegramFullscreen(tg);

  const initData = tg.initData || "";
  if (initData) setInitData(initData);

  if (!initData) {
    const dev = import.meta?.env?.DEV;
    if (!dev) {
      mount(el, <OpenInTelegram />);
      return;
    }
  }

  const adminMode = isAdminPath(window.location.pathname);

  try {
    if (initData) {
      const res = await fetch("/api/tg/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ initData }),
        credentials: "include",
      });
      if (!res.ok) throw new Error(`verify failed ${res.status}`);
      const payload = await res.json();
      if (!payload?.ok) throw new Error("bad signature");
    }

    mount(el, adminMode ? <AdminApp /> : <App />);
  } catch (e) {
    console.warn("Telegram verify error:", e);
    mount(el, <OpenInTelegram />);
  }
}

boot();
