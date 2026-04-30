import React, { useEffect, useRef, useState } from "react";
import "./LangPicker.css";

export default function LangPicker({ value, onChange, label }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const onDocPointerDown = (e) => {
      if (!ref.current) return;
      if (!ref.current.contains(e.target)) setOpen(false);
    };
    const onEsc = (e) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onDocPointerDown, true);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("pointerdown", onDocPointerDown, true);
      document.removeEventListener("keydown", onEsc);
    };
  }, []);

  const opts = [{ v: "ru", t: "RU" }, { v: "en", t: "EN" }, { v: "in", t: "IN" }];
  const current = String(value || "ru").toLowerCase();
  const menuId = "lang-menu";

  const selectLang = (next) => {
    if (next !== current) onChange(next);
    setOpen(false);
  };

  return (
    <div className={`lang-picker ${open ? "is-open" : ""}`} ref={ref}>
      <span className="lang-label">{label}</span>
      <button
        className="lang-btn"
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
      >
        {current.toUpperCase()} <span className={`chev ${open ? "up" : ""}`}></span>
      </button>
      {open && (
        <div id={menuId} className="lang-menu" role="listbox" aria-activedescendant={`lang-opt-${current}`}>
          {opts.map((o) => (
            <button
              type="button"
              key={o.v}
              id={`lang-opt-${o.v}`}
              role="option"
              aria-selected={current === o.v}
              className={`lang-item ${current === o.v ? "active" : ""}`}
              onClick={(e) => {
                e.stopPropagation();
                selectLang(o.v);
              }}
            >
              {o.t}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
