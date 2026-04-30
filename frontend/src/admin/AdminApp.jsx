import React, { useEffect, useMemo, useState } from "react";
import {
  apiAdminBroadcastDraft,
  apiAdminList,
  apiAdminMe,
  apiAdminSetSetting,
  apiAdminSettings,
  apiAdminStatuses,
  apiAdminUpsertStatus,
  apiAdminUpsertUser,
} from "../api";
import "./AdminApp.css";

const SETTINGS_SCHEMA = [
  { key: "PROJECT_NAME", label: "Название проекта", type: "text" },
  { key: "REGISTRATION_LINK", label: "Ссылка регистрации", type: "url" },
  { key: "ACCESS_DEPOSIT_THRESHOLD", label: "Порог доступа ($)", type: "number" },
  { key: "VIP_DEPOSIT_THRESHOLD", label: "Порог Premium ($)", type: "number" },
  { key: "MINIAPP_URL", label: "Ссылка MiniApp", type: "url" },
  { key: "ADMIN_WEBAPP_URL", label: "Ссылка Admin Center", type: "url" },
];

const DEFAULT_NEW_STATUS = {
  code: "",
  name_ru: "",
  name_en: "",
  name_in: "",
  min_deposit: 0,
  sort_order: 100,
  is_active: true,
};

const DEFAULT_DRAFT = {
  title: "",
  body: "",
  lang: "all",
};

const DEFAULT_ADMIN_FORM = {
  tg_id: "",
  role: "editor",
  is_active: true,
  permissions: [],
};

function rowsToMap(rows) {
  const out = {};
  for (const r of rows || []) out[r.skey] = r.svalue;
  return out;
}

export default function AdminApp() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [me, setMe] = useState(null);
  const [active, setActive] = useState("settings");

  const [settings, setSettings] = useState({});
  const [statuses, setStatuses] = useState([]);
  const [admins, setAdmins] = useState([]);

  const [newStatus, setNewStatus] = useState(DEFAULT_NEW_STATUS);
  const [draft, setDraft] = useState(DEFAULT_DRAFT);
  const [adminForm, setAdminForm] = useState(DEFAULT_ADMIN_FORM);
  const [info, setInfo] = useState("");

  const permissions = me?.permissions || [];
  const sections = useMemo(() => {
    const v = [];
    if (permissions.includes("settings")) v.push({ id: "settings", label: "Настройки" });
    if (permissions.includes("statuses")) v.push({ id: "statuses", label: "Статусы" });
    if (permissions.includes("mailing")) v.push({ id: "mailing", label: "Рассылка" });
    if (permissions.includes("admins")) v.push({ id: "admins", label: "Админы" });
    return v;
  }, [permissions]);

  const loadAll = async () => {
    setLoading(true);
    setError("");
    try {
      const meResp = await apiAdminMe();
      setMe(meResp);

      const loadedPermissions = meResp?.permissions || [];
      const tasks = [];

      if (loadedPermissions.includes("settings")) tasks.push(apiAdminSettings());
      else tasks.push(Promise.resolve([]));

      if (loadedPermissions.includes("statuses")) tasks.push(apiAdminStatuses());
      else tasks.push(Promise.resolve([]));

      if (loadedPermissions.includes("admins")) tasks.push(apiAdminList());
      else tasks.push(Promise.resolve([]));

      const [settingsRows, statusesRows, adminsRows] = await Promise.all(tasks);
      setSettings(rowsToMap(settingsRows));
      setStatuses(statusesRows || []);
      setAdmins(adminsRows || []);
    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  useEffect(() => {
    if (!sections.find((s) => s.id === active) && sections.length) {
      setActive(sections[0].id);
    }
  }, [sections, active]);

  const showInfo = (text) => {
    setInfo(text);
    window.setTimeout(() => setInfo(""), 2500);
  };

  const saveSettings = async () => {
    setBusy(true);
    setError("");
    try {
      for (const field of SETTINGS_SCHEMA) {
        const value = String(settings[field.key] ?? "").trim();
        await apiAdminSetSetting(field.key, value);
      }
      showInfo("Настройки сохранены");
    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setBusy(false);
    }
  };

  const saveStatus = async (row) => {
    setBusy(true);
    setError("");
    try {
      await apiAdminUpsertStatus({
        ...row,
        min_deposit: Number(row.min_deposit || 0),
        sort_order: Number(row.sort_order || 100),
      });
      showInfo(`Статус ${row.code} сохранен`);
      const fresh = await apiAdminStatuses();
      setStatuses(fresh || []);
    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setBusy(false);
    }
  };

  const addStatus = async () => {
    if (!newStatus.code.trim()) return;
    setBusy(true);
    setError("");
    try {
      await apiAdminUpsertStatus({
        ...newStatus,
        code: newStatus.code.trim().toUpperCase(),
        min_deposit: Number(newStatus.min_deposit || 0),
        sort_order: Number(newStatus.sort_order || 100),
      });
      setNewStatus(DEFAULT_NEW_STATUS);
      const fresh = await apiAdminStatuses();
      setStatuses(fresh || []);
      showInfo("Новый статус добавлен");
    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setBusy(false);
    }
  };

  const saveDraft = async () => {
    if (!draft.title.trim() || !draft.body.trim()) return;
    setBusy(true);
    setError("");
    try {
      await apiAdminBroadcastDraft({
        title: draft.title.trim(),
        body: draft.body.trim(),
        lang: draft.lang,
      });
      showInfo("Черновик рассылки создан (заглушка)");
    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setBusy(false);
    }
  };

  const saveAdmin = async () => {
    if (!adminForm.tg_id.trim()) return;
    setBusy(true);
    setError("");
    try {
      await apiAdminUpsertUser({
        tg_id: Number(adminForm.tg_id),
        role: adminForm.role,
        is_active: Boolean(adminForm.is_active),
        permissions: adminForm.permissions.length ? adminForm.permissions : null,
      });
      setAdminForm(DEFAULT_ADMIN_FORM);
      const fresh = await apiAdminList();
      setAdmins(fresh || []);
      showInfo("Админ обновлен");
    } catch (e) {
      setError(String(e?.message || e));
    } finally {
      setBusy(false);
    }
  };

  const togglePerm = (perm) => {
    const set = new Set(adminForm.permissions);
    if (set.has(perm)) set.delete(perm);
    else set.add(perm);
    setAdminForm((prev) => ({ ...prev, permissions: [...set] }));
  };

  if (loading) {
    return (
      <div className="admin-page">
        <section className="admin-card">
          <h1>Загрузка админцентра...</h1>
        </section>
      </div>
    );
  }

  if (error && !me) {
    return (
      <div className="admin-page">
        <section className="admin-card">
          <h1>Доступ закрыт</h1>
          <p className="admin-muted">Сервер не подтвердил admin-права.</p>
          <pre className="admin-error">{error}</pre>
        </section>
      </div>
    );
  }

  if (!sections.length) {
    return (
      <div className="admin-page">
        <section className="admin-card">
          <h1>Admin Center</h1>
          <p className="admin-muted">Для этого аккаунта нет доступных разделов.</p>
        </section>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <section className="admin-card admin-shell">
        <header className="admin-head">
          <div>
            <h1>Admin Center</h1>
            <p className="admin-muted">
              Проверка сервером: Telegram initData + tg_id в таблице + права.
            </p>
          </div>
          <div className="admin-role">
            <span>{String(me?.role || "editor").toUpperCase()}</span>
          </div>
        </header>

        <div className="admin-tabs">
          {sections.map((s) => (
            <button
              key={s.id}
              className={`admin-tab ${active === s.id ? "active" : ""}`}
              onClick={() => setActive(s.id)}
            >
              {s.label}
            </button>
          ))}
        </div>

        {active === "settings" && (
          <section className="admin-section">
            <h2>Глобальные настройки</h2>
            <div className="admin-grid">
              {SETTINGS_SCHEMA.map((field) => (
                <label key={field.key} className="admin-field">
                  <span>{field.label}</span>
                  <input
                    type={field.type}
                    value={settings[field.key] ?? ""}
                    onChange={(e) => setSettings((prev) => ({ ...prev, [field.key]: e.target.value }))}
                    disabled={busy}
                  />
                </label>
              ))}
            </div>
            <button className="admin-btn" onClick={saveSettings} disabled={busy}>
              Сохранить настройки
            </button>
          </section>
        )}

        {active === "statuses" && (
          <section className="admin-section">
            <h2>Статусы пользователей</h2>
            <div className="admin-list">
              {statuses.map((row, idx) => (
                <div className="status-row" key={row.code || idx}>
                  <input
                    value={row.code || ""}
                    onChange={(e) => {
                      const v = [...statuses];
                      v[idx] = { ...v[idx], code: e.target.value.toUpperCase() };
                      setStatuses(v);
                    }}
                    disabled={busy}
                  />
                  <input
                    value={row.name_ru || ""}
                    placeholder="RU"
                    onChange={(e) => {
                      const v = [...statuses];
                      v[idx] = { ...v[idx], name_ru: e.target.value };
                      setStatuses(v);
                    }}
                    disabled={busy}
                  />
                  <input
                    value={row.name_en || ""}
                    placeholder="EN"
                    onChange={(e) => {
                      const v = [...statuses];
                      v[idx] = { ...v[idx], name_en: e.target.value };
                      setStatuses(v);
                    }}
                    disabled={busy}
                  />
                  <input
                    value={row.name_in || ""}
                    placeholder="IN"
                    onChange={(e) => {
                      const v = [...statuses];
                      v[idx] = { ...v[idx], name_in: e.target.value };
                      setStatuses(v);
                    }}
                    disabled={busy}
                  />
                  <input
                    type="number"
                    value={row.min_deposit ?? 0}
                    onChange={(e) => {
                      const v = [...statuses];
                      v[idx] = { ...v[idx], min_deposit: e.target.value };
                      setStatuses(v);
                    }}
                    disabled={busy}
                  />
                  <input
                    type="number"
                    value={row.sort_order ?? 100}
                    onChange={(e) => {
                      const v = [...statuses];
                      v[idx] = { ...v[idx], sort_order: e.target.value };
                      setStatuses(v);
                    }}
                    disabled={busy}
                  />
                  <label className="mini-check">
                    <input
                      type="checkbox"
                      checked={Boolean(row.is_active)}
                      onChange={(e) => {
                        const v = [...statuses];
                        v[idx] = { ...v[idx], is_active: e.target.checked };
                        setStatuses(v);
                      }}
                      disabled={busy}
                    />
                    active
                  </label>
                  <button className="admin-btn ghost" onClick={() => saveStatus(row)} disabled={busy}>
                    Сохранить
                  </button>
                </div>
              ))}
            </div>

            <h3>Добавить статус</h3>
            <div className="status-row">
              <input
                placeholder="CODE"
                value={newStatus.code}
                onChange={(e) => setNewStatus((prev) => ({ ...prev, code: e.target.value.toUpperCase() }))}
                disabled={busy}
              />
              <input
                placeholder="RU"
                value={newStatus.name_ru}
                onChange={(e) => setNewStatus((prev) => ({ ...prev, name_ru: e.target.value }))}
                disabled={busy}
              />
              <input
                placeholder="EN"
                value={newStatus.name_en}
                onChange={(e) => setNewStatus((prev) => ({ ...prev, name_en: e.target.value }))}
                disabled={busy}
              />
              <input
                placeholder="IN"
                value={newStatus.name_in}
                onChange={(e) => setNewStatus((prev) => ({ ...prev, name_in: e.target.value }))}
                disabled={busy}
              />
              <input
                type="number"
                value={newStatus.min_deposit}
                onChange={(e) => setNewStatus((prev) => ({ ...prev, min_deposit: e.target.value }))}
                disabled={busy}
              />
              <input
                type="number"
                value={newStatus.sort_order}
                onChange={(e) => setNewStatus((prev) => ({ ...prev, sort_order: e.target.value }))}
                disabled={busy}
              />
              <label className="mini-check">
                <input
                  type="checkbox"
                  checked={Boolean(newStatus.is_active)}
                  onChange={(e) => setNewStatus((prev) => ({ ...prev, is_active: e.target.checked }))}
                  disabled={busy}
                />
                active
              </label>
              <button className="admin-btn" onClick={addStatus} disabled={busy}>
                Добавить
              </button>
            </div>
          </section>
        )}

        {active === "mailing" && (
          <section className="admin-section">
            <h2>Рассылка (заглушка)</h2>
            <label className="admin-field">
              <span>Заголовок</span>
              <input
                value={draft.title}
                onChange={(e) => setDraft((prev) => ({ ...prev, title: e.target.value }))}
                disabled={busy}
              />
            </label>
            <label className="admin-field">
              <span>Текст</span>
              <textarea
                value={draft.body}
                onChange={(e) => setDraft((prev) => ({ ...prev, body: e.target.value }))}
                disabled={busy}
              />
            </label>
            <label className="admin-field">
              <span>Язык</span>
              <select
                value={draft.lang}
                onChange={(e) => setDraft((prev) => ({ ...prev, lang: e.target.value }))}
                disabled={busy}
              >
                <option value="all">All</option>
                <option value="ru">RU</option>
                <option value="en">EN</option>
                <option value="in">IN</option>
              </select>
            </label>
            <button className="admin-btn" onClick={saveDraft} disabled={busy}>
              Создать черновик
            </button>
          </section>
        )}

        {active === "admins" && (
          <section className="admin-section">
            <h2>Администраторы</h2>
            <div className="admin-list compact">
              {(admins || []).map((a, idx) => (
                <div key={idx} className="admin-row">
                  <span>{a.tg_id}</span>
                  <span>{a.role}</span>
                  <span>{a.is_active ? "active" : "off"}</span>
                  <span>{typeof a.permissions_json === "string" ? a.permissions_json : "default"}</span>
                </div>
              ))}
            </div>

            <h3>Добавить/обновить админа</h3>
            <div className="admin-grid">
              <label className="admin-field">
                <span>Telegram ID</span>
                <input
                  value={adminForm.tg_id}
                  onChange={(e) => setAdminForm((prev) => ({ ...prev, tg_id: e.target.value }))}
                  disabled={busy}
                />
              </label>
              <label className="admin-field">
                <span>Роль</span>
                <select
                  value={adminForm.role}
                  onChange={(e) => setAdminForm((prev) => ({ ...prev, role: e.target.value }))}
                  disabled={busy}
                >
                  <option value="editor">editor</option>
                  <option value="owner">owner</option>
                </select>
              </label>
              <label className="mini-check">
                <input
                  type="checkbox"
                  checked={Boolean(adminForm.is_active)}
                  onChange={(e) => setAdminForm((prev) => ({ ...prev, is_active: e.target.checked }))}
                  disabled={busy}
                />
                active
              </label>
            </div>

            <div className="perm-list">
              {["settings", "statuses", "mailing", "admins"].map((perm) => (
                <label className="mini-check" key={perm}>
                  <input
                    type="checkbox"
                    checked={adminForm.permissions.includes(perm)}
                    onChange={() => togglePerm(perm)}
                    disabled={busy}
                  />
                  {perm}
                </label>
              ))}
            </div>

            <button className="admin-btn" onClick={saveAdmin} disabled={busy}>
              Сохранить админа
            </button>
          </section>
        )}

        {(error || info) && (
          <footer className="admin-footer">
            {error && <div className="admin-error">{error}</div>}
            {!error && info && <div className="admin-ok">{info}</div>}
          </footer>
        )}
      </section>
    </div>
  );
}
