import React, { useEffect, useState } from "react";
import "./App.css";
import GatePage from "./pages/GatePage";
import LangPicker from "./components/LangPicker";
import { apiCheckAccess, apiGetMe, apiGetPublicSettings } from "./api";

const READY_TEXT = {
  ru: {
    langLabel: "\u042f\u0437\u044b\u043a",
    title: "\u0414\u043e\u0441\u0442\u0443\u043f \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d",
    body: "\u0412\u0442\u043e\u0440\u0430\u044f \u0432\u0435\u0440\u0441\u0438\u044f \u0441\u0435\u0439\u0447\u0430\u0441 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 \u0432 \u0443\u043f\u0440\u043e\u0449\u0435\u043d\u043d\u043e\u043c \u0440\u0435\u0436\u0438\u043c\u0435: \u0442\u043e\u043b\u044c\u043a\u043e Telegram-\u0430\u0432\u0442\u043e\u0440\u0438\u0437\u0430\u0446\u0438\u044f \u0438 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 \u0434\u043e\u0441\u0442\u0443\u043f\u0430.",
    status: "\u0421\u0442\u0430\u0442\u0443\u0441",
  },
  en: {
    langLabel: "Language",
    title: "Access confirmed",
    body: "Version two now runs in minimal mode: Telegram authorization and access validation only.",
    status: "Status",
  },
  in: {
    langLabel: "Language",
    title: "Access confirmed",
    body: "Version two now runs in minimal mode: Telegram authorization and access validation only.",
    status: "Status",
  },
};

function detectInitialLang() {
  try {
    const saved = localStorage.getItem("miniapp_lang");
    if (saved && READY_TEXT[saved]) return saved;
  } catch {
    // ignore
  }
  const code = String(
    window.Telegram?.WebApp?.initDataUnsafe?.user?.language_code || navigator.language || "ru"
  ).toLowerCase();
  if (code.startsWith("ru")) return "ru";
  if (code.startsWith("en")) return "en";
  return "in";
}

function SplashScreen({ projectName = "Signals" }) {
  return (
    <div className="splash-screen">
      <div className="splash-glow splash-glow-a" />
      <div className="splash-glow splash-glow-b" />
      <section className="splash-center">
        <div className="splash-badge">Mini App</div>
        <h1>{projectName}</h1>
        <p>Checking access...</p>
        <div className="splash-loader" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
      </section>
    </div>
  );
}

function AccessReadyPage({ lang, setLang, projectName, me }) {
  const t = READY_TEXT[lang] || READY_TEXT.ru;
  const statusName = me?.status?.[`name_${lang}`] || me?.status?.name_ru || me?.status?.code || "TRADER";

  return (
    <section className="ready-page">
      <header className="ready-top">
        <div className="ready-brand">{projectName}</div>
        <LangPicker value={lang} onChange={setLang} label={t.langLabel} />
      </header>
      <div className="ready-card">
        <h1>{t.title}</h1>
        <p>{t.body}</p>
        <div className="ready-status">
          <span>{t.status}</span>
          <strong>{statusName}</strong>
        </div>
      </div>
    </section>
  );
}

export default function App() {
  const [lang, setLang] = useState(() => detectInitialLang());
  const [me, setMe] = useState(null);
  const [settings, setSettings] = useState(null);
  const [booting, setBooting] = useState(true);
  const [gate, setGate] = useState("loading");
  const [gateError, setGateError] = useState("");
  const [checking, setChecking] = useState(false);
  const [transitioning, setTransitioning] = useState(false);
  const [testMode, setTestMode] = useState(false);

  const loadMe = async () => {
    const [meRes, settingsRes] = await Promise.all([apiGetMe(), apiGetPublicSettings()]);
    setMe(meRes);
    setSettings(settingsRes);
    setGate(meRes?.gate || "registration_required");
  };

  useEffect(() => {
    try {
      localStorage.setItem("miniapp_lang", lang);
    } catch {
      // ignore
    }
  }, [lang]);

  useEffect(() => {
    let alive = true;
    const startedAt = Date.now();
    (async () => {
      try {
        await loadMe();
      } catch (e) {
        setGate("registration_required");
        setGateError(String(e?.message || e));
      } finally {
        const wait = Math.max(0, 700 - (Date.now() - startedAt));
        setTimeout(() => {
          if (alive) setBooting(false);
        }, wait);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const onAccessCheck = async (traderId) => {
    setGateError("");
    setChecking(true);
    setTransitioning(false);
    setTestMode(false);
    try {
      const res = await apiCheckAccess(traderId);
      const nextGate = String(res?.gate || "").toLowerCase();
      if (nextGate && nextGate !== "registration_required") {
        setTransitioning(true);
        await new Promise((resolve) => setTimeout(resolve, 260));
      }
      await loadMe();
    } catch (e) {
      setGateError(String(e?.message || e));
    } finally {
      setChecking(false);
      setTransitioning(false);
    }
  };

  if (booting || gate === "loading") {
    return <SplashScreen projectName={settings?.project_name || "Signals"} />;
  }

  if (gate !== "allowed") {
    if (testMode) {
      return (
        <AccessReadyPage
          lang={lang}
          setLang={setLang}
          projectName={settings?.project_name || "Signals"}
          me={me}
        />
      );
    }
    return (
      <GatePage
        gate={gate}
        settings={settings}
        me={me}
        checking={checking}
        onCheck={onAccessCheck}
        error={gateError}
        lang={lang}
        setLang={setLang}
        transitioning={transitioning}
        onTestMode={() => setTestMode(true)}
      />
    );
  }

  return <AccessReadyPage lang={lang} setLang={setLang} projectName={settings?.project_name || "Signals"} me={me} />;
}
