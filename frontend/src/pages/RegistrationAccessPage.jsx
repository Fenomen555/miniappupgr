import React, { useEffect, useState } from "react";
import LangPicker from "../components/LangPicker";
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
        <div className="reg-brand-widget">
          <span>{projectName}</span>
        </div>
      </header>

      <div className="reg-access-content">
        <div className="reg-access-copy">
          <h1>{t.registration.title}</h1>
          <p>{t.registration.subtitle}</p>
        </div>

        <form className="reg-access-card reg-access-form" onSubmit={submit}>
          <div className="reg-card-head">
            <h3>{t.registration.traderTitle}</h3>
            <p>{t.registration.traderText}</p>
          </div>

          {showRetry && (
            <div className="reg-access-retry">
              <h4>{t.registration.retryTitle}</h4>
              <p>{t.registration.retryText}</p>
            </div>
          )}

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

        <section className="reg-register-panel">
          <div>
            <h3>{t.registration.registerTitle}</h3>
            <p>{t.registration.registerText}</p>
          </div>
          <a href={registrationLink} target="_blank" rel="noopener noreferrer" className="reg-access-create-btn">
            {t.registration.createButton}
          </a>
        </section>
      </div>

      <footer className="reg-access-footer">
        <LangPicker value={lang} onChange={setLang} label={t.langLabel} />
      </footer>
    </section>
  );
}
