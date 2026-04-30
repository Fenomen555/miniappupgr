import React, { useEffect, useState } from "react";
import LangPicker from "../components/LangPicker";
import GateMascotLottie from "../components/GateMascotLottie";
import "./RegistrationAccessPage.css";

const TRADER_ID_RE = /^[A-Za-z0-9._-]{3,64}$/;

function cleanTraderId(value) {
  return String(value || "").replace(/\s+/g, "");
}

export default function RegistrationAccessPage({
  t,
  checking,
  onSubmit,
  error,
  lang,
  setLang,
  projectName,
  registrationLink,
  supportLink = "",
  onTestMode = () => {},
  initialTraderId = "",
  showRetry = false,
  transitioning = false,
}) {
  const [traderId, setTraderId] = useState(cleanTraderId(initialTraderId));
  const [localError, setLocalError] = useState("");
  const [dirty, setDirty] = useState(false);

  const validateTraderId = (value, required = false) => {
    const cleaned = cleanTraderId(value);
    if (!cleaned) return required ? t.registration.validationRequired : "";
    if (!TRADER_ID_RE.test(cleaned)) return t.registration.validationFormat;
    return "";
  };

  useEffect(() => {
    setTraderId(cleanTraderId(initialTraderId || ""));
    setDirty(false);
    setLocalError("");
  }, [initialTraderId]);

  useEffect(() => {
    if (!error) return;
    setLocalError(String(error));
  }, [error]);

  const submit = (e) => {
    e.preventDefault();
    const trimmed = cleanTraderId(traderId);
    const validationError = validateTraderId(trimmed, true);
    setDirty(true);
    if (validationError || checking) {
      setLocalError(validationError);
      return;
    }
    setLocalError("");
    onSubmit(trimmed);
  };

  const notifySupportUnavailable = () => {
    const tg = window.Telegram?.WebApp;
    const msg = t.registration.supportUnavailable || "Support is unavailable.";
    if (typeof tg?.showAlert === "function") {
      tg.showAlert(msg);
      return;
    }
    window.alert(msg);
  };

  const openSupport = () => {
    const tg = window.Telegram?.WebApp;
    const configuredLink = String(supportLink || "").trim();
    const botUsername = String(
      tg?.initDataUnsafe?.receiver?.username || tg?.initDataUnsafe?.chat?.username || ""
    ).trim();
    const fallbackBotLink = botUsername ? `https://t.me/${botUsername}` : "";
    const target = configuredLink || fallbackBotLink;

    if (!target) {
      notifySupportUnavailable();
      return;
    }

    if (/^https:\/\/t\.me\//i.test(target) && typeof tg?.openTelegramLink === "function") {
      tg.openTelegramLink(target);
      return;
    }

    if (/^https?:\/\//i.test(target)) {
      window.open(target, "_blank", "noopener,noreferrer");
      return;
    }

    notifySupportUnavailable();
  };

  const inlineError = localError || "";
  const actionLabel = transitioning
    ? t.registration.opening
    : checking
      ? t.checking
      : t.registration.submit;

  return (
    <section className={`reg-access-page ${transitioning ? "is-leaving" : ""}`}>
      <div className="reg-access-backdrop reg-access-backdrop-a" />
      <div className="reg-access-backdrop reg-access-backdrop-b" />

      <header className="reg-access-top">
        <div className="reg-brand-wrap">
          <span className="reg-brand-spark" aria-hidden="true" />
          <div className="reg-access-brand">{projectName}</div>
        </div>
        <div className="reg-top-actions">
          <button className="reg-support-btn" type="button" onClick={openSupport} aria-label={t.registration.support}>
            <span className="reg-support-icon" aria-hidden="true">
              ?
            </span>
          </button>
          <div className="reg-lang-wrap">
            <LangPicker value={lang} onChange={setLang} label={t.langLabel} />
          </div>
        </div>
      </header>

      <div className="reg-access-content">
        <div className="reg-access-copy">
          <h1>{t.registration.title}</h1>
          <p>{t.registration.subtitle}</p>
        </div>

        <div className="reg-access-mascot-wrap" aria-hidden="true">
          <div className="reg-logo-orb">
            <span className="reg-orbit reg-orbit-a" />
            <span className="reg-orbit reg-orbit-b" />
            <div className="reg-mascot-core">
              <GateMascotLottie className="reg-access-mascot" />
            </div>
          </div>
        </div>

        <div className="reg-steps">
          <section className="reg-step reg-step-primary">
            <div className="reg-step-head">
              <span className="reg-step-num">1</span>
              <h3>{t.registration.step1Title}</h3>
            </div>
            <p className="reg-step-text">{t.registration.step1Text}</p>
            <a href={registrationLink} target="_blank" rel="noopener noreferrer" className="reg-access-create-btn">
              {t.registration.createButton}
            </a>
          </section>

          <section className="reg-step reg-step-secondary">
            <div className="reg-step-head">
              <span className="reg-step-num">2</span>
              <h3>{t.registration.step2Title}</h3>
            </div>
            <p className="reg-step-text">{t.registration.step2Text}</p>
            {showRetry && (
              <div className="reg-access-retry">
                <h4>{t.registration.retryTitle}</h4>
                <p>{t.registration.retryText}</p>
              </div>
            )}

            <form className="reg-access-form" onSubmit={submit}>
              <input
                id="reg-trader-id"
                value={traderId}
                onChange={(e) => {
                  const cleaned = cleanTraderId(e.target.value);
                  setTraderId(cleaned);
                  setDirty(true);
                  setLocalError(validateTraderId(cleaned, false));
                }}
                onBlur={() => {
                  if (!dirty) return;
                  setLocalError(validateTraderId(traderId, false));
                }}
                placeholder={t.registration.traderPlaceholder}
                autoComplete="off"
                inputMode="text"
              />
              <p className="reg-access-note">{t.registration.securityNote}</p>
              {inlineError && <div className="reg-access-inline-error">{inlineError}</div>}
              <button
                className={`reg-access-submit ${checking ? "is-busy" : ""} ${transitioning ? "is-success" : ""}`}
                type="submit"
                disabled={!traderId.trim() || checking}
              >
                <span className={`reg-btn-spinner ${checking ? "is-visible" : ""}`} aria-hidden="true" />
                <span>{actionLabel}</span>
              </button>
            </form>
          </section>
        </div>

        <button className="reg-demo-btn" type="button" onClick={onTestMode} disabled={checking || transitioning}>
          {t.registration.demoButton}
        </button>
      </div>
    </section>
  );
}
