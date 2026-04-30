import React, { useEffect, useMemo, useState } from "react";
import LangPicker from "../components/LangPicker";
import GateMascotLottie from "../components/GateMascotLottie";
import "./DepositAccessPage.css";

export default function DepositAccessPage({
  t,
  checking,
  onSubmit,
  error,
  lang,
  setLang,
  projectName,
  accessThreshold,
  missingDeposit,
  savedTraderId = "",
}) {
  const [traderId, setTraderId] = useState(savedTraderId);
  const showInput = !savedTraderId;

  useEffect(() => {
    setTraderId(savedTraderId || "");
  }, [savedTraderId]);

  const moneyFmt = useMemo(
    () => (value) => {
      const n = Number(value || 0);
      if (!Number.isFinite(n)) return "0";
      return Number.isInteger(n) ? String(n) : n.toFixed(2);
    },
    []
  );

  const effectiveTraderId = traderId.trim() || savedTraderId;

  const submit = (e) => {
    e.preventDefault();
    if (!effectiveTraderId || checking) return;
    onSubmit(effectiveTraderId);
  };

  return (
    <section className="dep-access-page">
      <div className="dep-access-light dep-access-light-a" />
      <div className="dep-access-light dep-access-light-b" />

      <header className="dep-access-top">
        <div className="dep-access-brand">{projectName}</div>
        <LangPicker value={lang} onChange={setLang} label={t.langLabel} />
      </header>

      <div className="dep-access-hero">
        <GateMascotLottie className="dep-access-mascot" />

        <div className="dep-access-speech">
          <div className="dep-access-quote-mark">"</div>
          <div className="dep-access-copy">
          <h1>{t.deposit.title}</h1>
          <p>{t.deposit.subtitle(moneyFmt(accessThreshold))}</p>
          <strong>{t.deposit.missing(moneyFmt(missingDeposit))}</strong>
          </div>
        </div>
      </div>

      <form className="dep-access-form" onSubmit={submit}>
        {showInput ? (
          <>
            <input
              id="dep-trader-id"
              value={traderId}
              onChange={(e) => setTraderId(e.target.value)}
              placeholder={t.deposit.traderPlaceholder}
              autoComplete="off"
            />
          </>
        ) : (
          <div className="dep-access-saved-id">{t.deposit.savedTraderId(savedTraderId)}</div>
        )}

        <button className="dep-access-submit" type="submit" disabled={!effectiveTraderId || checking}>
          {checking ? t.checking : t.deposit.submit}
        </button>
      </form>

      {error && <div className="dep-access-error">{error}</div>}
    </section>
  );
}
