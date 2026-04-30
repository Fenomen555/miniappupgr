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
  initialTraderId = "",
  showRetry = false,
  transitioning = false,
}) {
  const [traderId, setTraderId] = useState(cleanTraderId(initialTraderId));
  const [localError, setLocalError] = useState("");
  const [dirty, setDirty] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);

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

  useEffect(() => {
    if (!infoOpen) return undefined;
    const onKeyDown = (e) => {
      if (e.key === "Escape") setInfoOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [infoOpen]);

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
  const hasTraderId = Boolean(traderId.trim());
  const actionLabel = transitioning
    ? t.registration.opening
    : checking
      ? t.checking
      : hasTraderId
        ? t.registration.submit
        : t.registration.submitEmpty;

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
        <GateMascotLottie src="/lottie/registered.json" className="reg-register-lottie" />

        <div className="reg-access-copy">
          <h1>{t.registration.title}</h1>
          <p className="reg-system-text">{t.registration.systemText}</p>
          <p className="reg-access-subtitle">{t.registration.subtitle}</p>
        </div>

        <div className="reg-flow-group reg-flow-primary">
          <form id="reg-access-form" className="reg-access-card reg-access-form" onSubmit={submit}>
            <button
              className="reg-info-trigger"
              type="button"
              aria-label={t.registration.infoLabel}
              onClick={() => setInfoOpen(true)}
            >
              <img src="/icons/info.png" alt="" aria-hidden="true" />
            </button>
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

            <label className="reg-id-field" htmlFor="reg-trader-id">
              <span className="reg-id-field-icon" aria-hidden="true">
                <img src="/icons/search.png" alt="" />
              </span>
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
            </label>
            <div className="reg-access-note">
              <span>{t.registration.securityNote}</span>
            </div>
            {inlineError && <div className="reg-access-inline-error">{inlineError}</div>}
          </form>
          <button
            className={`reg-access-submit ${checking ? "is-busy" : ""} ${transitioning ? "is-success" : ""}`}
            type="submit"
            form="reg-access-form"
            disabled={!hasTraderId || checking}
          >
            <span className={`reg-btn-spinner ${checking ? "is-visible" : ""}`} aria-hidden="true" />
            <img className="reg-btn-icon reg-btn-icon-search" src="/icons/search.png" alt="" aria-hidden="true" />
            <span>{actionLabel}</span>
          </button>
        </div>

        <div className="reg-flow-group reg-flow-register">
          <section className="reg-register-panel">
            <div>
              <h3>{t.registration.registerTitle}</h3>
              <p>{t.registration.registerText}</p>
            </div>
          </section>
          <a href={registrationLink} target="_blank" rel="noopener noreferrer" className="reg-access-create-btn">
            <img className="reg-btn-icon reg-btn-icon-bolt" src="/icons/bolt.png" alt="" aria-hidden="true" />
            <span>{t.registration.createButton}</span>
          </a>
        </div>
      </div>

      <footer className="reg-access-footer">
        <LangPicker value={lang} onChange={setLang} label={t.langLabel} />
      </footer>

      {infoOpen && (
        <div className="reg-info-modal" role="dialog" aria-modal="true" aria-labelledby="reg-info-title">
          <button className="reg-info-backdrop" type="button" aria-label={t.registration.infoClose} onClick={() => setInfoOpen(false)} />
          <section className="reg-info-panel">
            <button className="reg-info-close" type="button" aria-label={t.registration.infoClose} onClick={() => setInfoOpen(false)}>
              x
            </button>
            <div className="reg-info-title-row">
              <img src="/icons/info.png" alt="" aria-hidden="true" />
              <h2 id="reg-info-title">{t.registration.infoTitle}</h2>
            </div>
            <p>{t.registration.infoText}</p>
            <figure className="reg-info-image">
              <img src="/images/id-copy-guide.svg" alt={t.registration.infoImageCaption} />
              <figcaption>{t.registration.infoImageCaption}</figcaption>
            </figure>
            <button className="reg-info-done" type="button" onClick={() => setInfoOpen(false)}>
              {t.registration.infoClose}
            </button>
          </section>
        </div>
      )}
    </section>
  );
}
