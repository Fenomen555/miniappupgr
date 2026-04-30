import React from "react";
import { GATE_TEXTS } from "../i18n/gateTexts";
import RegistrationAccessPage from "./RegistrationAccessPage";
import DepositAccessPage from "./DepositAccessPage";

export default function GatePage({
  gate,
  settings,
  me,
  checking,
  onCheck,
  onTestMode = () => {},
  error,
  lang = "ru",
  setLang = () => {},
  transitioning = false,
}) {
  const t = GATE_TEXTS[lang] || GATE_TEXTS.ru;
  const projectName = settings?.project_name || "Signals";
  const registrationLink = settings?.registration_link || "#";
  const accessThreshold = Number(settings?.access_deposit_threshold || 0);
  const depositTotal = Number(me?.deposit_total || 0);
  const missingDeposit = Math.max(0, accessThreshold - depositTotal);
  const savedTraderId = String(me?.trader_id || "").trim();

  const submit = (traderId) => {
    const trimmed = String(traderId || "").trim();
    if (!trimmed || checking) return;
    onCheck(trimmed);
  };

  if (gate === "deposit_required") {
    return (
      <DepositAccessPage
        t={t}
        checking={checking}
        onSubmit={submit}
        error={error}
        lang={lang}
        setLang={setLang}
        projectName={projectName}
        accessThreshold={accessThreshold}
        missingDeposit={missingDeposit}
        savedTraderId={savedTraderId}
      />
    );
  }

  return (
    <RegistrationAccessPage
      t={t}
      checking={checking}
      onSubmit={submit}
      error={error}
      lang={lang}
      setLang={setLang}
      projectName={projectName}
      registrationLink={registrationLink}
      supportLink={settings?.support_link || ""}
      initialTraderId={savedTraderId}
      showRetry={Boolean(savedTraderId)}
      transitioning={transitioning}
      onTestMode={onTestMode}
    />
  );
}
