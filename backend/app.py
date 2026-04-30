import os, asyncio, time, hmac, hashlib, urllib.parse, random, json, re
from datetime import datetime, timedelta, timezone as dt_tz
from typing import Optional, Literal, Dict, Any, List, Tuple
import decimal
from fastapi import FastAPI, HTTPException, Request, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import aiomysql
import httpx
import telebot
from telebot import types
from tradingview_ta import TA_Handler, Interval
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from mysql.connector import pooling

# ======================= ENV / CONFIG =======================

DB_CFG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "db": os.getenv("DB_NAME", ""),
    "port": int(os.getenv("DB_PORT", "3306")),
    "autocommit": False,
}

# LLM credentials / defaults
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
CLIENT_TOKEN = os.getenv("CLIENT_TOKEN")
# API protection (optional)
API_ACCESS_TOKEN = os.getenv("API_ACCESS_TOKEN")

TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")
# CORS
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
PROJECT_NAME_DEFAULT = os.getenv("PROJECT_NAME", "Signals")
MINIAPP_URL_DEFAULT = os.getenv("MINIAPP_URL", "https://example.com")
REGISTRATION_LINK_DEFAULT = os.getenv("REGISTRATION_LINK", "https://example.com/register")
ADMIN_PRIVATE_PATH = os.getenv("ADMIN_PRIVATE_PATH", "2003dldsllsdld")
ACCESS_DEPOSIT_THRESHOLD_DEFAULT = float(os.getenv("ACCESS_DEPOSIT_THRESHOLD", "25"))
VIP_DEPOSIT_THRESHOLD_DEFAULT = float(os.getenv("VIP_DEPOSIT_THRESHOLD", "500"))
POCKET_API_BASE_URL = os.getenv("POCKET_API_BASE_URL", "https://affiliate.pocketoption.com/api/user-info").rstrip("/")
POCKET_PARTNER_ID = os.getenv("POCKET_PARTNER_ID", "")
POCKET_API_TOKEN = os.getenv("POCKET_API_TOKEN", "")
POCKET_API_TIMEOUT_SEC = float(os.getenv("POCKET_API_TIMEOUT_SEC", "10"))
TRADER_ID_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")

ADMIN_SETTING_KEYS = {
    "PROJECT_NAME",
    "MINIAPP_URL",
    "REGISTRATION_LINK",
    "ADMIN_WEBAPP_URL",
    "ACCESS_DEPOSIT_THRESHOLD",
    "VIP_DEPOSIT_THRESHOLD",
}

ADMIN_PERMISSIONS_BY_ROLE = {
    "owner": ["settings", "statuses", "mailing", "admins"],
    "editor": ["settings", "statuses", "mailing"],
}


# ======================= GLOBALS =======================

app = FastAPI(title="Signals API (async)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mysql_pool: aiomysql.Pool | None = None
httpx_client: httpx.AsyncClient | None = None
scheduler: AsyncIOScheduler | None = None

# bot runtime (same service)
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode="HTML")
_bot_started = False
sync_pool = None
try:
    if DB_CFG["db"]:
        sync_pool = pooling.MySQLConnectionPool(
            pool_name="v2_bot_pool",
            pool_size=4,
            host=DB_CFG["host"],
            port=DB_CFG["port"],
            user=DB_CFG["user"],
            password=DB_CFG["password"],
            database=DB_CFG["db"],
            autocommit=True,
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
        )
except Exception as e:
    print("[BOT] sync pool init error:", e)

# ======================= TV 429 cooldown =======================

TV_COOLDOWN_SEC = int(os.getenv("TV_COOLDOWN_SEC", "60"))

# когда можно снова пробовать TradingView (unix ts). 0 = можно сразу
_tv_cooldown_until: float = 0.0

# чтобы при одновременных запросах не было гонки обновления
_tv_cooldown_lock = asyncio.Lock()

def _tv_in_cooldown() -> bool:
    return time.time() < _tv_cooldown_until

async def _tv_start_cooldown(reason: str = "429"):
    global _tv_cooldown_until
    async with _tv_cooldown_lock:
        until = time.time() + TV_COOLDOWN_SEC
        # не уменьшаем cooldown, только продлеваем
        if until > _tv_cooldown_until:
            _tv_cooldown_until = until
        print(f"[TV COOLDOWN] start {TV_COOLDOWN_SEC}s (reason={reason}) until={_tv_cooldown_until:.0f}")
        
# ======================= Справочники =======================

CRYPTO_MAP = {
    "Bitcoin":  ("BTCUSDT", "BINANCE", "crypto"),
    "Ethereum": ("ETHUSDT", "BINANCE", "crypto"),
    "Polkadot OTC":  ("DOTUSDT", "BINANCE", "crypto"),
    "Polygon OTC":   ("MATICUSDT", "BINANCE", "crypto"),
    "Bitcoin ETF OTC": ("BTCUSDT", "BINANCE", "crypto"),
    "Chainlink OTC": ("LINKUSDT", "BINANCE", "crypto"),
    "Solana OTC":    ("SOLUSDT", "BINANCE", "crypto"),
    "BNB OTC":       ("BNBUSDT", "BINANCE", "crypto"),
    "TRON OTC":      ("TRXUSDT", "BINANCE", "crypto"),
    "Bitcoin OTC":   ("BTCUSDT", "BINANCE", "crypto"),
    "Ethereum OTC":  ("ETHUSDT", "BINANCE", "crypto"),
    "Cardano OTC":   ("ADAUSDT", "BINANCE", "crypto"),
    "Avalanche OTC": ("AVAXUSDT", "BINANCE", "crypto"),
    "Dogecoin OTC":  ("DOGEUSDT", "BINANCE", "crypto"),
    "Litecoin OTC":  ("LTCUSDT", "BINANCE", "crypto"),
    "Toncoin OTC":   ("TONUSDT", "BINANCE", "crypto"),
}
CRYPTO_LIST = ["Bitcoin", "Ethereum"] + [k for k in CRYPTO_MAP.keys() if k.endswith("OTC")]

COMMODITIES_MAP = {
    "Gold":          ("GOLD",      "TVC", "cfd"),
    "Silver":        ("SILVER",    "TVC", "cfd"),
    "Palladium spot":("PALLADIUM", "TVC", "cfd"),
    "Platinum spot": ("PLATINUM",  "TVC", "cfd"),
}
COMMODITIES_LIST = list(COMMODITIES_MAP.keys())

STOCKS_MAP = {
    "ExxonMobil": ("XOM","NYSE","america"),
    "Netflix": ("NFLX","NASDAQ","america"),
    "McDonald's": ("MCD","NYSE","america"),
    "FedEx": ("FDX","NYSE","america"),
    "Palantir Technologies": ("PLTR","NYSE","america"),
    "VISA": ("V","NYSE","america"),
    "Citigroup Inc": ("C","NYSE","america"),
    "Johnson & Johnson": ("JNJ","NYSE","america"),
    "GameStop Corp": ("GME","NYSE","america"),
    "Alibaba": ("BABA","NYSE","america"),
    "Coinbase Global": ("COIN","NASDAQ","america"),
    "Microsoft": ("MSFT","NASDAQ","america"),
    "AMD": ("AMD","NASDAQ","america"),
    "Marathon Digital Holdings": ("MARA","NASDAQ","america"),
    "Pfizer Inc": ("PFE","NYSE","america"),
    "Boeing Company": ("BA","NYSE","america"),
    "Apple": ("AAPL","NASDAQ","america"),
    "American Express": ("AXP","NYSE","america"),
    "Cisco": ("CSCO","NASDAQ","america"),
    "Facebook Inc": ("META","NASDAQ","america"),
    "Intel": ("INTC","NASDAQ","america"),
    "Amazon": ("AMZN","NASDAQ","america"),
}
STOCKS_LIST = list(STOCKS_MAP.keys())


# ======================= Модели =======================

class SignalRequest(BaseModel):
    uid: int = Field(..., description="Telegram user_id")
    lang: Literal["ru","en","in"] = "ru"
    pair: str
    expiry_min: Literal[1,2,3,4,5,10,15]

class SignalResponse(BaseModel):
    id: Optional[int] = None
    decision: Literal["BUY","SELL"]
    confidence: int
    tf_used: str
    at: str
    expiry_min: Optional[int] = None
    asset_type: Optional[str] = None
    pair_label: Optional[str] = None
    tv_symbol: Optional[str] = None
    tv_exchange: Optional[str] = None
    tv_screener: Optional[str] = None
    open_at: Optional[str] = None
    close_at: Optional[str] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    result: Optional[Literal["WIN","LOSS","DRAW","N/A"]] = None
    status: Optional[Literal["IN_PROGRESS","SETTLED","ERROR"]] = None

class ChatMsg(BaseModel):
    role: Literal["system","user","assistant"]
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMsg]
    model: Optional[str] = None              # можно оставить, чтобы иногда менять модель
    temperature: Optional[float] = Field(default=0.6, ge=0.0, le=1.5)
    system_prompt: Optional[str] = None
    
class ChatResponse(BaseModel):
    reply: str


class AccessCheckRequest(BaseModel):
    trader_id: Optional[str] = Field(default=None, max_length=64)


class AdminSettingPatch(BaseModel):
    key: str
    value: str


class AdminStatusPatch(BaseModel):
    code: str
    name_ru: str
    name_en: str
    name_in: str
    min_deposit: float
    sort_order: int = 100
    is_active: bool = True


class AdminBroadcastDraft(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    body: str = Field(min_length=1, max_length=4096)
    lang: Literal["ru", "en", "in", "all"] = "all"


class AdminUserPatch(BaseModel):
    tg_id: int
    role: Literal["owner", "editor"] = "editor"
    is_active: bool = True
    permissions: Optional[List[Literal["settings", "statuses", "mailing", "admins"]]] = None


# ======================= Auth (Telegram initData +/или API key) =======================

def _parse_init_data(init_data: str) -> Tuple[Dict[str, str], Optional[int], Optional[int]]:
    """
    Возвращает: (map параметров, user_id или None, auth_date(ts) или None)
    """
    data = {}
    for kv in init_data.split("&"):
        if not kv:
            continue
        if "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        data[k] = urllib.parse.unquote_plus(v)

    user_id = None
    if "user" in data:
        # user — это JSON-строка
        try:
            import json
            u = json.loads(data["user"])
            user_id = int(u.get("id")) if isinstance(u, dict) and "id" in u else None
        except Exception:
            user_id = None

    auth_date = None
    if "auth_date" in data:
        try:
            auth_date = int(data["auth_date"])
        except Exception:
            auth_date = None

    return data, user_id, auth_date


def verify_telegram_init_data(init_data: str, bot_token: Optional[str]) -> Tuple[bool, Optional[int]]:
    if not init_data or not bot_token:
        return False, None

    params, user_id, auth_date = _parse_init_data(init_data)
    provided_hash = params.pop("hash", None)
    if not provided_hash:
        return False, None

    # (опционально) проверяем "свежесть"
    if auth_date:
        now = int(time.time())
        if now - auth_date > 24 * 3600:
            return False, user_id

    # === ВАЖНО: КЛЮЧ ДЛЯ WebApp ===
    # secret_key = HMAC_SHA256(key="WebAppData", data=bot_token)
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()

    # data-check-string: пары key=value, отсортированные по ключу, БЕЗ hash
    data_check_string = "\n".join(f"{k}={params[k]}" for k in sorted(params.keys()))

    calc_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    ok = hmac.compare_digest(calc_hash, provided_hash)
    return ok, user_id

async def require_auth(
    request: Request,
    x_api_key: Optional[str] = Header(default=None),
    # ЯВНОЕ соответствие нашему заголовку
    x_tg_init_data: Optional[str] = Header(default=None, alias="X-TG-Init-Data"),
) -> Dict[str, Any]:
    ctx = {"tg_ok": False, "tg_uid": None, "api_key_ok": False}

    # 1) API key — как было
    if API_ACCESS_TOKEN and x_api_key and x_api_key == API_ACCESS_TOKEN:
        ctx["api_key_ok"] = True
        return ctx

    # 2) initData: сначала берём из alias-параметра,
    # затем подстрахуемся руками всеми возможными вариантами
    init_data = (
        x_tg_init_data
        or request.headers.get("X-TG-Init-Data")
        or request.headers.get("x-tg-init-data")
    )

    if not init_data:
        # из body (POST) или query (GET)
        try:
            body = await request.json()
            init_data = body.get("initData")
        except Exception:
            pass
        if not init_data:
            init_data = request.query_params.get("initData")

    ok, uid = verify_telegram_init_data(init_data or "", TELEGRAM_BOT_TOKEN)
    if not ok:
        # ВКЛЮЧИТЕ это логирование на время отладки
        print("[AUTH FAIL] headers keys:", list(request.headers.keys())[:20])
        raise HTTPException(status_code=401, detail="Telegram auth required")

    ctx["tg_ok"] = True
    ctx["tg_uid"] = uid
    return ctx


def _load_admin_permissions(role: str, permissions_raw: Any) -> List[str]:
    defaults = list(ADMIN_PERMISSIONS_BY_ROLE.get((role or "").lower(), []))
    if permissions_raw in (None, "", []):
        return defaults

    parsed = permissions_raw
    if isinstance(permissions_raw, (bytes, bytearray)):
        try:
            parsed = permissions_raw.decode("utf-8")
        except Exception:
            return defaults

    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except Exception:
            return defaults

    if not isinstance(parsed, list):
        return defaults

    allowed_scopes = {"settings", "statuses", "mailing", "admins"}
    sanitized = []
    for x in parsed:
        s = str(x or "").strip().lower()
        if s in allowed_scopes and s not in sanitized:
            sanitized.append(s)
    return sanitized or defaults


async def require_admin(auth: Dict[str, Any] = Depends(require_auth)) -> Dict[str, Any]:
    tg_uid = auth.get("tg_uid")
    if not tg_uid:
        raise HTTPException(status_code=401, detail="Telegram auth required")

    row = await DB.fetchone_dict(
        """
        SELECT tg_id, role, permissions_json
        FROM admin_users
        WHERE tg_id=%s AND is_active=1
        LIMIT 1
        """,
        (int(tg_uid),),
    )
    if not row:
        raise HTTPException(status_code=403, detail="Admin access denied")

    role = str(row.get("role") or "editor").lower()
    permissions = _load_admin_permissions(role, row.get("permissions_json"))
    return {"tg_uid": int(tg_uid), "role": role, "permissions": permissions}


def require_admin_scope(scope: str):
    async def _checker(admin: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
        if scope not in set(admin.get("permissions") or []):
            raise HTTPException(status_code=403, detail=f"Insufficient permissions: {scope}")
        return admin

    return _checker


async def setting_get(key: str, default: str = "") -> str:
    row = await DB.fetchone_dict("SELECT svalue FROM app_settings WHERE skey=%s", (key,))
    return str(row["svalue"]) if row and row.get("svalue") is not None else default


async def setting_set(key: str, value: str) -> None:
    await DB.execute(
        """
        INSERT INTO app_settings (skey, svalue)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE svalue=VALUES(svalue), updated_at=UTC_TIMESTAMP()
        """,
        (key, value),
    )


async def get_thresholds() -> tuple[float, float]:
    access = float(await setting_get("ACCESS_DEPOSIT_THRESHOLD", str(ACCESS_DEPOSIT_THRESHOLD_DEFAULT)))
    vip = float(await setting_get("VIP_DEPOSIT_THRESHOLD", str(VIP_DEPOSIT_THRESHOLD_DEFAULT)))
    return access, vip


async def ensure_default_statuses() -> None:
    row = await DB.fetchone_dict("SELECT COUNT(*) c FROM user_statuses WHERE is_active=1")
    if row and int(row["c"] or 0) > 0:
        return

    access, vip = await get_thresholds()
    defaults = [
        ("TRADER", "Трейдер", "Trader", "Trader", 0.0, 10, 1),
        ("BRONZE", "Бронза", "Bronze", "Bronze", access, 20, 1),
        ("PREMIUM", "Премиум", "Premium", "Premium", vip, 30, 1),
    ]
    for code, ru, en, i18n, min_dep, order_num, is_active in defaults:
        await DB.execute(
            """
            INSERT INTO user_statuses (code, name_ru, name_en, name_in, min_deposit, sort_order, is_active)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
              name_ru=VALUES(name_ru),
              name_en=VALUES(name_en),
              name_in=VALUES(name_in),
              min_deposit=VALUES(min_deposit),
              sort_order=VALUES(sort_order),
              is_active=VALUES(is_active),
              updated_at=UTC_TIMESTAMP()
            """,
            (code, ru, en, i18n, float(min_dep), int(order_num), int(is_active)),
        )


async def resolve_status_by_deposit(deposit_total: float) -> Dict[str, Any]:
    rows = await DB.fetchall_dict(
        """
        SELECT code, name_ru, name_en, name_in, min_deposit, sort_order
        FROM user_statuses
        WHERE is_active=1
        ORDER BY min_deposit ASC, sort_order ASC
        """
    )
    if not rows:
        return {"code": "TRADER", "name_ru": "Трейдер", "name_en": "Trader", "name_in": "Trader", "min_deposit": 0.0}

    selected = rows[0]
    for r in rows:
        if float(deposit_total) >= float(r["min_deposit"]):
            selected = r
    return selected


async def upsert_user_profile(user_id: int, first_name: str = "", last_name: str = "", username: str = "") -> None:
    await DB.execute(
        """
        INSERT INTO users (
            user_id, first_name, last_name, username,
            registration_status, deposit_status,
            first_seen_at, created_at, updated_at, language
        )
        VALUES (%s,%s,%s,%s,0,0,UTC_TIMESTAMP(),UTC_TIMESTAMP(),UTC_TIMESTAMP(),'ru')
        ON DUPLICATE KEY UPDATE
            first_name=VALUES(first_name),
            last_name=VALUES(last_name),
            username=VALUES(username),
            updated_at=UTC_TIMESTAMP(),
            first_seen_at=IFNULL(users.first_seen_at, VALUES(first_seen_at))
        """,
        (user_id, first_name, last_name, username),
    )


async def get_or_init_user(user_id: int) -> Dict[str, Any]:
    row = await DB.fetchone_dict("SELECT * FROM users WHERE user_id=%s", (user_id,))
    if row:
        return row
    await upsert_user_profile(user_id)
    row = await DB.fetchone_dict("SELECT * FROM users WHERE user_id=%s", (user_id,))
    return row or {"user_id": user_id, "registration_status": 0, "deposit_status": 0}


def compute_gate(registration_status: int, deposit_status: int) -> str:
    if int(registration_status or 0) == 0:
        return "registration_required"
    if int(deposit_status or 0) == 0:
        return "deposit_required"
    return "allowed"


async def compute_gate_for_user_row(user_row: Dict[str, Any]) -> Tuple[str, int]:
    reg = int(user_row.get("registration_status") or 0)
    dep_status = int(user_row.get("deposit_status") or 0)
    return compute_gate(reg, dep_status), dep_status


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


async def ensure_partner_profile_table() -> None:
    await DB.execute(
        """
        CREATE TABLE IF NOT EXISTS user_partner_profile (
          user_id BIGINT NOT NULL,
          trader_id VARCHAR(64) DEFAULT NULL,
          balance VARCHAR(64) DEFAULT NULL,
          first_deposit_sum VARCHAR(64) DEFAULT NULL,
          first_deposit_date VARCHAR(64) DEFAULT NULL,
          deposits_count VARCHAR(32) DEFAULT NULL,
          deposits_sum VARCHAR(64) DEFAULT NULL,
          reg_date VARCHAR(64) DEFAULT NULL,
          activity_date VARCHAR(64) DEFAULT NULL,
          country VARCHAR(64) DEFAULT NULL,
          is_verified VARCHAR(32) DEFAULT NULL,
          company VARCHAR(128) DEFAULT NULL,
          registration_link VARCHAR(512) DEFAULT NULL,
          verification_code VARCHAR(32) DEFAULT NULL,
          raw_json LONGTEXT NULL,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (user_id),
          KEY idx_upp_trader_id (trader_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )


async def upsert_partner_profile(user_id: int, trader_id: str, ext: Dict[str, Any]) -> None:
    raw = ext.get("raw") if isinstance(ext, dict) else {}
    if not isinstance(raw, dict):
        raw = {}

    profile = {
        "trader_id": trader_id,
        "balance": raw.get("balance"),
        "first_deposit_sum": raw.get("sum_ftd"),
        "first_deposit_date": raw.get("date_ftd"),
        "deposits_count": raw.get("count_deposits"),
        "deposits_sum": raw.get("sum_deposits"),
        "reg_date": raw.get("reg_date"),
        "activity_date": raw.get("activity_date"),
        "country": raw.get("country"),
        "is_verified": raw.get("is_verified"),
        "company": raw.get("company"),
        "registration_link": raw.get("link"),
        "verification_code": ext.get("code") or "ok",
    }

    await DB.execute(
        """
        INSERT INTO user_partner_profile (
          user_id, trader_id, balance, first_deposit_sum, first_deposit_date,
          deposits_count, deposits_sum, reg_date, activity_date, country, is_verified,
          company, registration_link, verification_code, raw_json
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
          trader_id=VALUES(trader_id),
          balance=VALUES(balance),
          first_deposit_sum=VALUES(first_deposit_sum),
          first_deposit_date=VALUES(first_deposit_date),
          deposits_count=VALUES(deposits_count),
          deposits_sum=VALUES(deposits_sum),
          reg_date=VALUES(reg_date),
          activity_date=VALUES(activity_date),
          country=VALUES(country),
          is_verified=VALUES(is_verified),
          company=VALUES(company),
          registration_link=VALUES(registration_link),
          verification_code=VALUES(verification_code),
          raw_json=VALUES(raw_json),
          updated_at=UTC_TIMESTAMP()
        """,
        (
            int(user_id),
            str(profile["trader_id"] or ""),
            None if profile["balance"] is None else str(profile["balance"]),
            None if profile["first_deposit_sum"] is None else str(profile["first_deposit_sum"]),
            None if profile["first_deposit_date"] is None else str(profile["first_deposit_date"]),
            None if profile["deposits_count"] is None else str(profile["deposits_count"]),
            None if profile["deposits_sum"] is None else str(profile["deposits_sum"]),
            None if profile["reg_date"] is None else str(profile["reg_date"]),
            None if profile["activity_date"] is None else str(profile["activity_date"]),
            None if profile["country"] is None else str(profile["country"]),
            None if profile["is_verified"] is None else str(profile["is_verified"]),
            None if profile["company"] is None else str(profile["company"]),
            None if profile["registration_link"] is None else str(profile["registration_link"]),
            str(profile["verification_code"]),
            json.dumps(raw, ensure_ascii=False),
        ),
    )


async def _call_pocket_verify_api(trader_id: str) -> Dict[str, Any]:
    if not httpx_client:
        raise RuntimeError("HTTP client is not initialized")
    if not POCKET_PARTNER_ID or not POCKET_API_TOKEN:
        raise RuntimeError("Pocket API credentials are not configured")

    raw = f"{trader_id}:{POCKET_PARTNER_ID}:{POCKET_API_TOKEN}"
    md5_hash = hashlib.md5(raw.encode("utf-8")).hexdigest()
    url = (
        f"{POCKET_API_BASE_URL}/"
        f"{urllib.parse.quote_plus(trader_id)}/"
        f"{urllib.parse.quote_plus(str(POCKET_PARTNER_ID))}/"
        f"{md5_hash}"
    )

    try:
        r = await httpx_client.get(
            url,
            headers={"accept": "application/json"},
            timeout=POCKET_API_TIMEOUT_SEC,
            follow_redirects=True,
        )
    except Exception as e:
        raise RuntimeError(f"Pocket API request error: {e}") from e

    if r.status_code == 404:
        return {"registered": False, "deposit_total": 0.0, "raw": {}, "code": "user_not_found", "source": "pocket"}
    if r.status_code != 200:
        raise RuntimeError(f"Pocket API status: {r.status_code}")

    try:
        data = r.json() if r.content else {}
    except Exception as e:
        raise RuntimeError(f"Pocket API invalid JSON: {e}") from e

    deposit_total = _to_float(data.get("sum_deposits"))
    if deposit_total <= 0:
        deposit_total = _to_float(data.get("sum_ftd"))

    return {
        "registered": True,
        "deposit_total": max(0.0, deposit_total),
        "raw": data,
        "code": "ok",
        "source": "pocket",
    }


async def call_external_verify_api(trader_id: str) -> Dict[str, Any]:
    if not POCKET_PARTNER_ID or not POCKET_API_TOKEN:
        raise RuntimeError("Pocket verification is not configured (POCKET_PARTNER_ID / POCKET_API_TOKEN)")
    return await _call_pocket_verify_api(trader_id)


async def alert_admins(text: str) -> None:
    rows = await DB.fetchall_dict("SELECT tg_id FROM admin_users WHERE is_active=1")
    for row in rows:
        chat_id = int(row["tg_id"])
        try:
            await asyncio.to_thread(bot.send_message, chat_id, text)
        except Exception as e:
            print("[ALERT BOT ERROR]", chat_id, e)


def _sync_conn():
    if sync_pool is None:
        raise RuntimeError("Sync DB pool is not initialized")
    return sync_pool.get_connection()


def bot_get_setting(key: str, default: str) -> str:
    try:
        conn = _sync_conn()
        cur = conn.cursor()
        cur.execute("SELECT svalue FROM app_settings WHERE skey=%s", (key,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return str(row[0]) if row and row[0] is not None else default
    except Exception:
        return default


def bot_is_admin(tg_id: int) -> bool:
    try:
        conn = _sync_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM admin_users WHERE tg_id=%s AND is_active=1 LIMIT 1", (int(tg_id),))
        ok = cur.fetchone() is not None
        cur.close()
        conn.close()
        return ok
    except Exception:
        return False


def bot_upsert_user(message) -> None:
    try:
        u = message.from_user
        conn = _sync_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (
              user_id, first_name, last_name, username,
              registration_status, deposit_status,
              first_seen_at, created_at, updated_at, language
            )
            VALUES (%s,%s,%s,%s,0,0,UTC_TIMESTAMP(),UTC_TIMESTAMP(),UTC_TIMESTAMP(),'ru')
            ON DUPLICATE KEY UPDATE
              first_name=VALUES(first_name),
              last_name=VALUES(last_name),
              username=VALUES(username),
              updated_at=UTC_TIMESTAMP(),
              first_seen_at=IFNULL(users.first_seen_at, VALUES(first_seen_at))
            """,
            (u.id, u.first_name, u.last_name, u.username),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("[BOT UPSERT ERROR]", e)


def register_bot_handlers() -> None:
    @bot.message_handler(commands=["start"])
    def on_start(message):
        bot_upsert_user(message)
        project_name = bot_get_setting("PROJECT_NAME", PROJECT_NAME_DEFAULT)
        miniapp_url = bot_get_setting("MINIAPP_URL", MINIAPP_URL_DEFAULT)
        admin_webapp_url = bot_get_setting("ADMIN_WEBAPP_URL", f"{miniapp_url.rstrip('/')}/{ADMIN_PRIVATE_PATH}")

        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("Open Mini App", web_app=types.WebAppInfo(url=miniapp_url)))
        if bot_is_admin(message.from_user.id):
            kb.add(types.InlineKeyboardButton("Admin Center", web_app=types.WebAppInfo(url=admin_webapp_url)))

        bot.send_message(
            message.chat.id,
            f"Welcome to <b>{project_name}</b>\\n\\nOpen the mini app to continue.",
            reply_markup=kb,
        )

    @bot.message_handler(commands=["admin"])
    def on_admin(message):
        if not bot_is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "Access denied")
            return
        miniapp_url = bot_get_setting("MINIAPP_URL", MINIAPP_URL_DEFAULT)
        admin_webapp_url = bot_get_setting("ADMIN_WEBAPP_URL", f"{miniapp_url.rstrip('/')}/{ADMIN_PRIVATE_PATH}")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("Open Admin Center", web_app=types.WebAppInfo(url=admin_webapp_url)))
        bot.send_message(message.chat.id, "Admin center", reply_markup=kb)


def start_bot_thread() -> None:
    global _bot_started
    if _bot_started:
        return
    register_bot_handlers()

    def _run():
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            print("[BOT POLLING ERROR]", e)

    th = asyncio.get_running_loop().run_in_executor(None, _run)
    _bot_started = True

#  =================API=================
DEVS_BASE = "https://api.devsbite.com"
DEVS_ANALYSIS_PATH = "/analysis/tv"
PAIRS_CACHE_TTL = 2

_pairs_cache: dict[str, tuple[float, set[str]]] = {}  # kind -> (ts_until, set(pairs))

async def fetch_pairs_from_devsbite(kind: str, min_payout: int = 70) -> set[str]:
    now = time.time()
    cached = _pairs_cache.get(kind)
    if cached and cached[0] > now:
        return cached[1]

    url = f"{DEVS_BASE}/pairs/{kind}?min_payout={min_payout}"

    headers = {}
    if CLIENT_TOKEN:
        headers["X-Client-Token"] = CLIENT_TOKEN

    r = await httpx_client.get(url, timeout=10.0, headers=headers)
    if r.status_code != 200:
        raise HTTPException(502, f"devsbite error {r.status_code}")

    data = r.json()
    pairs = {(x.get("pair") or "").strip() for x in (data.get("pairs") or [])}
    pairs.discard("")
    _pairs_cache[kind] = (now + PAIRS_CACHE_TTL, pairs)
    return pairs
    
def _pair_for_price(pair: str) -> str:
    p = (pair or "").strip()
    if p.endswith(" OTC"):
        p = p[:-4].strip()
    return p
    
async def fetch_tv_analysis_from_devsbite(
    symbol: str,
    exchange: str,
    screener: str,
    interval: str,
) -> Dict[str, Optional[str]]:
    """
    Fallback: дергаем devsbite, если локально получили 429.
    Никаких кэшей. Всегда live-запрос.

    Ожидаемый ответ devsbite описан ниже (см. "Спека ответа").
    """
    if not httpx_client:
        raise HTTPException(500, "httpx_client is not initialized")

    url = f"{DEVS_BASE}{DEVS_ANALYSIS_PATH}"

    payload = {
        "symbol": symbol,
        "exchange": exchange,
        "screener": screener,
        "interval": interval,
        "client": "signals-api",
    }

    headers = {"accept": "application/json"}
    if CLIENT_TOKEN:
        headers["X-Client-Token"] = CLIENT_TOKEN

    r = await httpx_client.post(url, json=payload, timeout=10.0, headers=headers)
    if r.status_code != 200:
        raise HTTPException(502, f"devsbite analysis error {r.status_code}")

    data = r.json() or {}
    print("[DEVSBITE ANALYSIS RAW]", {
        "symbol": symbol,
        "exchange": exchange,
        "screener": screener,
        "interval": interval,
        "keys": list((data or {}).keys()),
        "summary": (data.get("summary") if isinstance(data.get("summary"), dict) else data.get("summary")),
    })
    
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    osc = data.get("oscillators") if isinstance(data.get("oscillators"), dict) else {}
    ma  = data.get("moving_averages") if isinstance(data.get("moving_averages"), dict) else {}
    ind = data.get("indicators") if isinstance(data.get("indicators"), dict) else {}

    reco = summary.get("RECOMMENDATION") or data.get("reco") or data.get("recommendation") or "NEUTRAL"
    print("[DEVSBITE ANALYSIS PARSED]", {
        "reco": reco,
        "osc_reco": (osc.get("RECOMMENDATION") if isinstance(osc, dict) else None),
        "ma_reco": (ma.get("RECOMMENDATION") if isinstance(ma, dict) else None),
    })
    
    return {
        "reco": reco,
        "osc_reco": osc.get("RECOMMENDATION"),
        "ma_reco": ma.get("RECOMMENDATION"),

        "summary": summary,
        "oscillators": osc,
        "moving_averages": ma,
        "indicators": ind,

        "provider": data.get("provider") or "devsbite",
        "fetched_at": data.get("fetched_at"),
    }
    
async def fetch_price_from_devsbite(pair: str) -> float:
    if not httpx_client:
        raise HTTPException(500, "httpx_client is not initialized")

    sym = _pair_for_price(pair)
    if not sym or "/" not in sym:
        raise HTTPException(400, "Bad pair for price")

    encoded = urllib.parse.quote(sym, safe="")
    encoded = urllib.parse.quote(encoded, safe="")
    url = f"{DEVS_BASE}/price/{encoded}"
    print("[DEVSBITE PRICE REQ]", pair, "->", sym, "->", url)

    headers = {"accept": "application/json"}
    if CLIENT_TOKEN:
        headers["X-Client-Token"] = CLIENT_TOKEN

    r = await httpx_client.get(url, timeout=10.0, headers=headers)
    if r.status_code != 200:
        raise HTTPException(502, f"devsbite price error {r.status_code}")

    data = r.json() or {}
    price = data.get("price")
    if price is None:
        raise HTTPException(502, "devsbite price: empty price")

    return float(price)
    
# ======================= Вспомогательные =======================
def _reco_to_sign(r: Optional[str]) -> int:
    r = (r or "").upper()
    if r in ("STRONG_BUY", "BUY"): return +1
    if r in ("STRONG_SELL", "SELL"): return -1
    return 0

def _clamp(n: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, n))
    
def _short_tv_log(tv: Dict[str, Any]) -> Dict[str, Any]:
    """Короткая выжимка для логов (без огромных COMPUTE)."""
    summary = tv.get("summary") if isinstance(tv.get("summary"), dict) else {}
    ind = tv.get("indicators") if isinstance(tv.get("indicators"), dict) else {}

    def pick(d: dict, keys: list[str]):
        out = {}
        for k in keys:
            if k in d:
                out[k] = d.get(k)
        return out

    return {
        "_source": tv.get("_source"),
        "provider": tv.get("provider"),
        "fetched_at": tv.get("fetched_at"),
        "reco": tv.get("reco"),
        "osc_reco": tv.get("osc_reco"),
        "ma_reco": tv.get("ma_reco"),
        "summary": pick(summary, ["RECOMMENDATION", "BUY", "SELL", "NEUTRAL"]),
        "indicators": pick(ind, ["Recommend.All", "Recommend.MA", "Recommend.Other", "RSI", "close", "MACD.macd", "MACD.signal"]),
    }
    
def compute_confidence(tv: Dict[str, Any], decision: str) -> int:
    """
    Возвращает confidence 0..100.
    Учитывает:
    - summary BUY/SELL/NEUTRAL counts (если есть)
    - indicators Recommend.All / Recommend.MA / Recommend.Other (если есть)
    - конфликт между summary/MA/OSC
    - урезанный ответ devsbite: только summary.RECOMMENDATION => 80%
    """
    decision = (decision or "NEUTRAL").upper()

    summary = tv.get("summary") if isinstance(tv.get("summary"), dict) else {}
    ind     = tv.get("indicators") if isinstance(tv.get("indicators"), dict) else {}

    has_counts = any(k in summary for k in ("BUY", "SELL", "NEUTRAL"))
    has_any_ind = any(k in ind for k in ("Recommend.All", "Recommend.MA", "Recommend.Other"))

    # 1) Урезанный ответ: только RECOMMENDATION без чисел/индикаторов
    if summary and not has_counts and not has_any_ind:
        # как ты просил: всегда 80 (но не для NEUTRAL)
        if decision == "NEUTRAL":
            return 50
        return 80

    # 2) Базовая сила из counts
    strength_counts = None
    try:
        b = float(summary.get("BUY", 0) or 0)
        s = float(summary.get("SELL", 0) or 0)
        n = float(summary.get("NEUTRAL", 0) or 0)
        tot = b + s + n
        if tot > 0:
            # 0..1: насколько доминирует выбранная сторона над противоположной
            if decision == "BUY":
                strength_counts = _clamp((b - s) / tot, 0.0, 1.0)
            elif decision == "SELL":
                strength_counts = _clamp((s - b) / tot, 0.0, 1.0)
            else:
                # для нейтрала — насколько NEUTRAL доминирует
                strength_counts = _clamp(n / tot, 0.0, 1.0)
    except Exception:
        strength_counts = None

    # 3) Сила из indicators (Recommend.* обычно в диапазоне [-1..+1])
    strength_ind = None
    try:
        rec_all = ind.get("Recommend.All", None)
        rec_ma  = ind.get("Recommend.MA", None)
        rec_oth = ind.get("Recommend.Other", None)

        vals = []
        for v in (rec_all, rec_ma, rec_oth):
            if isinstance(v, (int, float)):
                vals.append(float(v))
        if vals:
            # среднее, берём модуль (сила), но проверим знак согласованности с decision ниже
            avg = sum(vals) / len(vals)
            strength_ind = _clamp(abs(avg), 0.0, 1.0)
            ind_sign = 0
            if avg > 0.05: ind_sign = +1
            elif avg < -0.05: ind_sign = -1
        else:
            ind_sign = 0
    except Exception:
        strength_ind = None
        ind_sign = 0

    # 4) Согласованность (summary vs osc vs ma vs indicators sign)
    s_summary = _reco_to_sign(summary.get("RECOMMENDATION") or tv.get("reco"))
    s_osc     = _reco_to_sign(tv.get("osc_reco"))
    s_ma      = _reco_to_sign(tv.get("ma_reco"))

    want = 0
    if decision == "BUY": want = +1
    elif decision == "SELL": want = -1

    agree = 0
    checks = 0
    for sgn in (s_summary, s_ma, s_osc, ind_sign):
        if sgn == 0:
            continue
        checks += 1
        if want != 0 and sgn == want:
            agree += 1

    agreement_ratio = (agree / checks) if checks else 0.5  # 0..1
    # штраф за конфликт: если согласие < 0.5, режем сильно
    conflict_penalty = 1.0
    if checks >= 2 and agreement_ratio < 0.5:
        conflict_penalty = 0.65
    elif checks >= 2 and agreement_ratio < 0.75:
        conflict_penalty = 0.85

    # 5) Склейка источников
    # counts — главный, indicators — вторичный
    sc = strength_counts if strength_counts is not None else 0.45
    si = strength_ind    if strength_ind    is not None else 0.35

    # если решение NEUTRAL — держим ближе к 50
    if decision == "NEUTRAL":
        base = 40 + 30 * max(sc, si)
    else:
        base = 45 + 45 * (0.65 * sc + 0.35 * si)

    base *= conflict_penalty

    # 6) Минимумы/максимумы, чтобы не было 0/100 слишком часто
    if decision == "NEUTRAL":
        base = _clamp(base, 35, 70)
    else:
        base = _clamp(base, 45, 92)

    return int(round(base))

def map_interval(expiry_min: int) -> str:
    if expiry_min in (1,2,3):
        return Interval.INTERVAL_1_MINUTE
    if expiry_min in (4,5,10):
        return Interval.INTERVAL_5_MINUTES
    return Interval.INTERVAL_15_MINUTES

def get_tv_params(pair: str):
    if pair in CRYPTO_MAP:
        sym, ex, scr = CRYPTO_MAP[pair]
        return sym, ex, scr, "crypto", pair
    if pair in COMMODITIES_MAP:
        sym, ex, scr = COMMODITIES_MAP[pair]
        return sym, ex, scr, "commodity", pair
    if pair in STOCKS_MAP:
        sym, ex, scr = STOCKS_MAP[pair]
        return sym, ex, scr, "stock", pair
    if pair.endswith(" OTC") and "/" in pair:
        base = pair.replace(" OTC","").replace("/","")
        return base, "FX_IDC", "forex", "forex_otc", pair
    if "/" in pair:
        base = pair.replace("/","")
        return base, "FX_IDC", "forex", "forex", pair
    raise ValueError("Unsupported pair")

def normalize(reco: str) -> str:
    if reco in ("STRONG_BUY","BUY"): return "BUY"
    if reco in ("STRONG_SELL","SELL"): return "SELL"
    return "NEUTRAL"

def _decide_result(side: str, entry: Optional[float], exit: Optional[float]) -> str:
    try:
        if entry is None or exit is None:
            return "N/A"
        if isinstance(entry, decimal.Decimal): entry = float(entry)
        if isinstance(exit, decimal.Decimal): exit = float(exit)
        if abs(exit - entry) <= 1e-9:
            return "DRAW"
        side = (side or "").upper()
        if side == "BUY":  return "WIN" if exit > entry else "LOSS"
        if side == "SELL": return "WIN" if exit < entry else "LOSS"
        return "N/A"
    except Exception as e:
        print(f"[DECIDE ERROR] {e}")
        return "ERROR"


# ======================= TradingView (в пуле потоков) =======================

class TradingViewRateLimit(Exception):
    pass
    
async def _ta_analysis(symbol: str, exchange: str, screener: str, interval: str) -> Dict[str, Optional[str]]:
    def _run():
        handler = TA_Handler(symbol=symbol, exchange=exchange, screener=screener, interval=interval)
        analysis = handler.get_analysis()
        print("[TV LOCAL RAW] symbol=", symbol, "ex=", exchange, "scr=", screener, "tf=", interval,
              "| summary=", analysis.summary)        
        return {
            "reco": analysis.summary.get("RECOMMENDATION", "NEUTRAL"),
            "osc_reco": analysis.oscillators.get("RECOMMENDATION"),
            "ma_reco": analysis.moving_averages.get("RECOMMENDATION"),
            "summary": dict(analysis.summary or {}),
            "oscillators": dict(analysis.oscillators or {}),
            "moving_averages": dict(analysis.moving_averages or {}),
            "indicators": dict(getattr(analysis, "indicators", {}) or {}),
        }

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        msg = str(e).lower()

        if "429" in msg or "too many" in msg or "rate limit" in msg:
            raise TradingViewRateLimit(str(e))

        print(f"[TV ANALYSIS ERROR] {symbol}: {e}")
        raise
    
async def get_tv_analysis(symbol: str, exchange: str, screener: str, interval: str):
    if _tv_in_cooldown():
        print(f"[TV SKIP] cooldown active -> devsbite (symbol={symbol}, tf={interval})")
        tv = await fetch_tv_analysis_from_devsbite(symbol, exchange, screener, interval)
        tv["_source"] = "devsbite_cooldown"
        print("[ANALYSIS GOT]", _short_tv_log(tv))
        return tv

    try:
        tv = await _ta_analysis(symbol, exchange, screener, interval)
        tv["_source"] = "local_tradingview_ta"
        print("[ANALYSIS GOT]", _short_tv_log(tv))
        return tv

    except TradingViewRateLimit as e:
        print(f"[TV 429] {symbol} -> cooldown + devsbite: {e}")
        await _tv_start_cooldown("429")

        tv = await fetch_tv_analysis_from_devsbite(symbol, exchange, screener, interval)
        tv["_source"] = "devsbite_fallback_429"
        print("[ANALYSIS GOT]", _short_tv_log(tv))
        return tv

    except Exception as e:
        print(f"[TV ANALYSIS FAIL] {symbol}: {e}")
        print("[ANALYSIS ERROR NEUTRAL]", {"symbol": symbol, "tf": interval})
        return {"reco": "NEUTRAL", "osc_reco": None, "ma_reco": None, "_source": "error_neutral"}


# ======================= LLM клиенты =======================

def _normalize_reply(text: str) -> str:
    if not text:
        return text
    cleaned = text.strip()
    signature = "С уважением, команда Profit Days."
    if signature.lower() not in cleaned.lower():
        if not cleaned.endswith((".", "!", "?", "…")):
            cleaned += "."
        cleaned += f" {signature}"
    return cleaned

async def call_openai(messages: List[Dict[str,str]], model: str, temperature: float) -> Optional[str]:
    if not OPENAI_API_KEY:
        return None
    try:
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": model, "messages": messages, "temperature": temperature}
        r = await httpx_client.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers, json=payload,
            timeout=httpx.Timeout(60.0),
        )
        if r.status_code != 200:
            print("[OPENAI ERROR]", r.status_code, r.text[:400]); return None
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print("[OPENAI EXC]", e); return None

LIGHT_CHAT_PROMPT = """
Ты — Profit Days, ассистент трейдеров команды Profit Days
Основные задачи:
помогать пользователям Pocket Option;
объяснять торговые сигналы, таймфреймы и управление рисками;
отвечать на вопросы о трейдинге, психологии и деньгах;
вести лёгкий, дружелюбный диалог (на «привет», «как дела» и т.п. отвечай естественно и кратко, затем мягко направляй разговор в сторону трейдинга).
ВАЖНО: отвечай на языке, на котором писал пользователь.
Формат ответа:
Если пользователь запрашивает АНАЛИЗ РЫНКА или СИГНАЛ по инструменту, используй структуру:
Сценарий (восходящий / нисходящий / консолидация)
Ключевые уровни / индикаторы
Риск ≤ 2% депозита, избегать новостей
Дисклеймер: это не инвестиционная рекомендация
С уважением, команда Profit Days.
Если вопрос общий (обучение, психология, деньги, неформальное общение),
отвечай обычным текстом без пунктов 1–5, но кратко, по делу и с уважением.
Если по конкретному инструменту или сигналу действительно нет данных,
честно сообщи об отсутствии данных и дай общую логику или рекомендацию.
Не обещай прибыль и не давай прямых инвестиционных рекомендаций.
""".strip()


# ======================= Вспом. для чата =======================

def _build_messages(req: ChatRequest) -> List[Dict[str, str]]:
    sys_prompt = (req.system_prompt or LIGHT_CHAT_PROMPT).strip()
    msgs: List[Dict[str, str]] = [{"role": "system", "content": sys_prompt}]
    client_system = [m for m in req.messages if m.role == "system"]
    client_others = [m for m in req.messages if m.role != "system"]
    for m in client_system:
        msgs.append({"role": "system", "content": m.content})
    for m in client_others:
        role = m.role if m.role in ("system", "user", "assistant") else "user"
        msgs.append({"role": role, "content": m.content})
    return msgs

def _pick_openai_model(req: ChatRequest) -> str:
    return req.model or OPENAI_MODEL
# ======================= DB helpers =======================

class DB:
    @staticmethod
    async def get_pool() -> aiomysql.Pool:
        assert mysql_pool is not None, "MySQL pool is not initialized"
        return mysql_pool

    @staticmethod
    async def execute(query: str, params: tuple = ()) -> int:
        pool = await DB.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                await conn.commit()
                return cur.lastrowid or 0

    @staticmethod
    async def fetchone_dict(query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        pool = await DB.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, params)
                return await cur.fetchone()

    @staticmethod
    async def fetchall_dict(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        pool = await DB.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, params)
                return await cur.fetchall()


# ======================= Лайфцикл приложения =======================

@app.on_event("startup")
async def on_startup():
    global mysql_pool, httpx_client, scheduler

    limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)
    httpx_client = httpx.AsyncClient(
        timeout=httpx.Timeout(10.0),
        limits=limits,
        trust_env=False,
        headers={"Connection": "keep-alive"},
    )

    mysql_pool = await aiomysql.create_pool(
        minsize=1, maxsize=10,
        host=DB_CFG["host"], port=DB_CFG["port"],
        user=DB_CFG["user"], password=DB_CFG["password"],
        db=DB_CFG["db"], autocommit=False
    )

    scheduler = AsyncIOScheduler()
    scheduler.start()
    scheduler.add_job(auto_settle, trigger=IntervalTrigger(seconds=30))
    print("[SCHEDULER] started")
    await ensure_partner_profile_table()
    await ensure_default_statuses()
    start_bot_thread()

@app.on_event("shutdown")
async def on_shutdown():
    global mysql_pool, httpx_client, scheduler
    if scheduler:
        scheduler.shutdown(wait=False)
    if httpx_client:
        await httpx_client.aclose()
    if mysql_pool:
        mysql_pool.close()
        await mysql_pool.wait_closed()


# ======================= Эндпоинты =======================

@app.post("/api/tg/verify")
async def tg_verify(request: Request):
    """
    Роут для фронта при старте: принимает {initData}, проверяет подпись.
    """
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(500, "BOT_TOKEN is not configured")
    try:
        body = await request.json()
    except Exception:
        body = {}
    init_data = body.get("initData") or request.headers.get("X-TG-Init-Data")
    ok, uid = verify_telegram_init_data(init_data or "", TELEGRAM_BOT_TOKEN)
    if not ok:
        raise HTTPException(401, "Bad Telegram signature")
    return {"ok": True, "uid": uid}


@app.get("/api/settings/public", dependencies=[Depends(require_auth)])
async def public_settings():
    project_name = await setting_get("PROJECT_NAME", PROJECT_NAME_DEFAULT)
    registration_link = await setting_get("REGISTRATION_LINK", REGISTRATION_LINK_DEFAULT)
    access_threshold, vip_threshold = await get_thresholds()
    return {
        "project_name": project_name,
        "registration_link": registration_link,
        "access_deposit_threshold": access_threshold,
        "vip_deposit_threshold": vip_threshold,
    }


@app.get("/api/me", dependencies=[Depends(require_auth)])
async def me(auth: Dict[str, Any] = Depends(require_auth)):
    uid = int(auth["tg_uid"])
    user = await get_or_init_user(uid)
    partner = await DB.fetchone_dict(
        """
        SELECT trader_id, balance, first_deposit_sum, first_deposit_date, deposits_count, deposits_sum,
               reg_date, activity_date, country, is_verified, company, registration_link, verification_code, updated_at
        FROM user_partner_profile
        WHERE user_id=%s
        """,
        (uid,),
    )
    status = await resolve_status_by_deposit(float(user.get("deposit_total") or 0.0))
    gate, dep_status_dynamic = await compute_gate_for_user_row(user)
    return {
        "user_id": uid,
        "username": user.get("username"),
        "trader_id": user.get("trader_id"),
        "registration_status": int(user.get("registration_status") or 0),
        "deposit_status": dep_status_dynamic,
        "deposit_total": float(user.get("deposit_total") or 0.0),
        "status": {
            "code": status["code"],
            "name_ru": status["name_ru"],
            "name_en": status["name_en"],
            "name_in": status["name_in"],
        },
        "partner_profile": partner or None,
        "gate": gate,
    }


@app.post("/api/access/check", dependencies=[Depends(require_auth)])
async def access_check(req: AccessCheckRequest, auth: Dict[str, Any] = Depends(require_auth)):
    uid = int(auth["tg_uid"])
    user = await get_or_init_user(uid)
    request_tid = (req.trader_id or "").strip()
    saved_tid = str(user.get("trader_id") or "").strip()
    trader_id = request_tid or saved_tid
    if not trader_id:
        raise HTTPException(400, "Trader ID is required")
    if not TRADER_ID_RE.match(trader_id):
        raise HTTPException(400, "Invalid Trader ID format")

    current_reg = int(user.get("registration_status") or 0)
    current_dep = int(user.get("deposit_status") or 0)
    current_gate = compute_gate(current_reg, current_dep)
    if current_gate == "allowed" and not request_tid:
        status = await resolve_status_by_deposit(float(user.get("deposit_total") or 0.0))
        return {
            "ok": True,
            "gate": "allowed",
            "registration_found": True,
            "verification_code": "cached_allowed",
            "provider": "cache",
            "trader_id": trader_id,
            "deposit_total": float(user.get("deposit_total") or 0.0),
            "required_deposit": float((await get_thresholds())[0]),
            "missing_deposit": 0.0,
            "status": {
                "code": status["code"],
                "name_ru": status["name_ru"],
                "name_en": status["name_en"],
                "name_in": status["name_in"],
            },
        }

    try:
        ext = await call_external_verify_api(trader_id)
    except Exception as e:
        await alert_admins(f"[ALERT] verify API unavailable: {e}")
        raise HTTPException(503, "Registration check is temporarily unavailable")

    registered = bool(ext["registered"])
    deposit_total = float(ext["deposit_total"])
    access_threshold, _vip_threshold = await get_thresholds()
    deposit_status = 1 if deposit_total >= access_threshold else 0
    missing_deposit = max(0.0, float(access_threshold) - float(deposit_total))
    status = await resolve_status_by_deposit(deposit_total)

    await DB.execute(
        """
        INSERT INTO users (
            user_id, trader_id, registration_status, deposit_status, deposit_total, status_code,
            first_seen_at, created_at, updated_at, last_access_check_at, registered_at, language
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            UTC_TIMESTAMP(), UTC_TIMESTAMP(), UTC_TIMESTAMP(), UTC_TIMESTAMP(),
            CASE WHEN %s=1 THEN UTC_TIMESTAMP() ELSE NULL END, 'ru'
        )
        ON DUPLICATE KEY UPDATE
            trader_id=VALUES(trader_id),
            registration_status=VALUES(registration_status),
            deposit_status=VALUES(deposit_status),
            deposit_total=VALUES(deposit_total),
            status_code=VALUES(status_code),
            country=COALESCE(NULLIF(%s, ''), users.country),
            last_access_check_at=UTC_TIMESTAMP(),
            updated_at=UTC_TIMESTAMP(),
            registered_at=CASE WHEN VALUES(registration_status)=1 THEN COALESCE(users.registered_at, UTC_TIMESTAMP()) ELSE users.registered_at END
        """,
        (
            uid,
            trader_id,
            1 if registered else 0,
            deposit_status,
            deposit_total,
            status["code"],
            1 if registered else 0,
            str((ext.get("raw") or {}).get("country") or ""),
        ),
    )

    await upsert_partner_profile(uid, trader_id, ext)

    gate = compute_gate(1 if registered else 0, deposit_status)

    await DB.execute(
        """
        INSERT INTO access_check_log (user_id, trader_id, is_registered, deposit_total, gate_result, raw_json)
        VALUES (%s,%s,%s,%s,%s,%s)
        """,
        (
            uid,
            trader_id,
            1 if registered else 0,
            deposit_total,
            gate,
            json.dumps(ext.get("raw") or {}, ensure_ascii=False),
        ),
    )

    return {
        "ok": True,
        "gate": gate,
        "registration_found": registered,
        "verification_code": str(ext.get("code") or "ok"),
        "provider": str(ext.get("source") or "unknown"),
        "trader_id": trader_id,
        "deposit_total": deposit_total,
        "required_deposit": float(access_threshold),
        "missing_deposit": missing_deposit,
        "status": {
            "code": status["code"],
            "name_ru": status["name_ru"],
            "name_en": status["name_en"],
            "name_in": status["name_in"],
        },
    }

@app.get("/api/health", dependencies=[Depends(require_auth)])
async def health():
    return {
        "ok": bool(OPENAI_API_KEY),
        "providers": {
            "openai": {"ok": bool(OPENAI_API_KEY), "model": OPENAI_MODEL}
        }
    }

@app.get("/api/models", dependencies=[Depends(require_auth)])
async def list_llm_models():
    return {"source": "openai", "ok": True, "models": [OPENAI_MODEL]}

@app.get("/api/llm-test", dependencies=[Depends(require_auth)])
async def llm_test(prompt: str="ping"):
    if not OPENAI_API_KEY:
        return {"ok": False, "error": "OPENAI_API_KEY is not configured"}
    messages = [{"role":"system","content":"Reply with a single word: OK."},
                {"role":"user","content":prompt}]
    text = await call_openai(messages, OPENAI_MODEL, 0.2)
    return {"ok": bool(text), "text": text}
    
@app.get("/api/pairs", dependencies=[Depends(require_auth)])
async def list_pairs(min_payout: int = 70):
    forex = await fetch_pairs_from_devsbite("forex", min_payout=min_payout)
    otc   = await fetch_pairs_from_devsbite("otc",   min_payout=min_payout)
    return {
        "forex": sorted(forex),
        "forex_otc": sorted(otc),
        "crypto": CRYPTO_LIST,
        "commodities": COMMODITIES_LIST,
        "stocks": STOCKS_LIST,
    }
    
@app.post("/api/signal", response_model=SignalResponse)
async def make_signal(req: SignalRequest, request: Request, auth: Dict[str, Any] = Depends(require_auth)):
    if auth.get("tg_ok") and auth.get("tg_uid") and int(req.uid) != int(auth["tg_uid"]):
        raise HTTPException(403, "UID mismatch")

    profile = await DB.fetchone_dict(
        "SELECT registration_status, deposit_status, deposit_total FROM users WHERE user_id=%s",
        (req.uid,),
    )
    if not profile:
        raise HTTPException(403, "User profile not found")
    gate, _dep_status = await compute_gate_for_user_row(profile)
    if gate != "allowed":
        raise HTTPException(403, "Access denied: complete registration and deposit")

    try:
        pair = (req.pair or "").strip()

        if pair.endswith(" OTC"):
            allowed = await fetch_pairs_from_devsbite("otc", min_payout=70)
        else:
            allowed = await fetch_pairs_from_devsbite("forex", min_payout=70)

        if "/" in pair:
            if pair not in allowed:
                raise HTTPException(400, "Pair is not available (min_payout filter)")
        tv_symbol, tv_exchange, tv_screener, asset_type, pair_label = get_tv_params(pair)

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Unsupported pair")

    tf = map_interval(req.expiry_min)
    now_utc = datetime.now(dt_tz.utc)
    open_dt  = now_utc.replace(tzinfo=None)
    close_dt = (now_utc + timedelta(minutes=req.expiry_min)).replace(tzinfo=None)

    open_at  = now_utc.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    close_at = (now_utc + timedelta(minutes=req.expiry_min)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    
    tv = await get_tv_analysis(tv_symbol, tv_exchange, tv_screener, tf)
    print("[SIGNAL TV INPUT]", {
        "uid": req.uid,
        "pair": pair_label,
        "tv_symbol": tv_symbol,
        "exchange": tv_exchange,
        "screener": tv_screener,
        "tf": tf,
        "tv": _short_tv_log(tv),
    })
    
    decision = normalize(tv["reco"])

    if decision == "NEUTRAL":
        decision = "BUY" if random.random() < 0.5 else "SELL"
        confidence = 50
    else:
        confidence = compute_confidence(tv, decision)
    print("[SIGNAL FRONT OUTPUT]", {
        "decision": decision,
        "confidence": confidence,
        "raw_reco": tv.get("reco"),
        "osc_reco": tv.get("osc_reco"),
        "ma_reco": tv.get("ma_reco"),
        "_source": tv.get("_source"),
    })
    
    entry_price = None
    try:
        entry_price = await fetch_price_from_devsbite(pair_label)
    except Exception as e:
        print("[DEVSBITE PRICE ERROR]", e)
        entry_price = None

    inserted_id = None
    try:
        inserted_id = await DB.execute("""
            INSERT INTO signals_log
              (user_id, lang, asset_type, pair_label,
               tv_symbol, tv_exchange, tv_screener, tv_interval,
               raw_reco, osc_reco, ma_reco,
               expiry_min, decision, confidence,
               open_at, close_at, created_at, user_agent, ip_addr,
               entry_price, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, UTC_TIMESTAMP(), %s, %s, %s, 'IN_PROGRESS')
        """, (
            req.uid, req.lang, asset_type, pair_label,
            tv_symbol, tv_exchange, tv_screener, tf,
            tv["reco"], tv.get("osc_reco"), tv.get("ma_reco"),
            req.expiry_min, decision, confidence,
            open_dt, close_dt,  # ✅ ВОТ ЭТО ВАЖНО
            request.headers.get("user-agent", ""),
            request.client.host if request.client else None,
            entry_price
        ))        
    except Exception as e:
        print("[DB ERROR]", e)

    return SignalResponse(
        id=inserted_id, decision=decision, confidence=confidence, tf_used=tf,
        at=open_at, asset_type=asset_type, pair_label=pair_label,
        tv_symbol=tv_symbol, tv_exchange=tv_exchange, tv_screener=tv_screener,
        open_at=open_at, close_at=close_at, expiry_min=req.expiry_min,
        entry_price=entry_price, status="IN_PROGRESS",
    )
   
@app.post("/api/settle", dependencies=[Depends(require_auth)])
async def settle(id: int):
    try:
        row = await DB.fetchone_dict("SELECT * FROM signals_log WHERE id=%s", (id,))
        if not row:
            raise HTTPException(404, "Signal not found")

        if row["status"] == "SETTLED":
            return {"id": id, "settled": True, "exit_price": row["exit_price"], "result": row["result"], "reason": "already_settled"}

        close_at = row.get("close_at")
        if isinstance(close_at, datetime):
            close_dt = close_at
        elif close_at:
            s = str(close_at).strip()
            if s.endswith("Z"): s = s[:-1] + "+00:00"
            if "." in s:
                parts = s.split(".")
                s = parts[0] + "." + parts[1][:6] + (parts[1][6:] if "+" in parts[1] else "")
            close_dt = datetime.fromisoformat(s)
        else:
            raise HTTPException(500, "Invalid close_at timestamp")

        now_utc = datetime.now(dt_tz.utc)
        if now_utc < close_dt.replace(tzinfo=dt_tz.utc):
            return {"id": id, "settled": False, "reason": "not_yet_time"}

        exit_price = None
        try:
            exit_price = await fetch_price_from_devsbite(row["pair_label"])
        except Exception as e:
            print("[DEVSBITE EXIT PRICE ERROR]", e)
            exit_price = None
            
        entry_price = float(row["entry_price"]) if row["entry_price"] is not None else None
        exit_price = float(exit_price) if exit_price is not None else None
        result = _decide_result(row["decision"], entry_price, exit_price)

        await DB.execute("""
            UPDATE signals_log
            SET exit_price=%s, result=%s, status='SETTLED', settled_at=UTC_TIMESTAMP()
            WHERE id=%s
        """, (exit_price, result, id))

        return {"id": id, "settled": True, "exit_price": exit_price, "result": result}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Settle error: {e}")

@app.get("/api/history", dependencies=[Depends(require_auth)])
async def history(uid: int, limit: int = 100, auth: Dict[str, Any] = Depends(require_auth)):
    # Если пришли из Telegram — uid должен совпадать
    if auth.get("tg_ok") and auth.get("tg_uid") and int(uid) != int(auth["tg_uid"]):
        raise HTTPException(403, "UID mismatch")

    try:
        rows = await DB.fetchall_dict("""
            SELECT id, created_at, lang, asset_type, pair_label,
                   tv_symbol, tv_exchange, tv_screener, tv_interval,
                   raw_reco, osc_reco, ma_reco,
                   expiry_min, decision, confidence,
                   open_at, close_at, settled_at,
                   entry_price, exit_price, result, status
            FROM signals_log
            WHERE user_id=%s
            ORDER BY id DESC
            LIMIT %s
        """, (uid, limit))

        def iso_z(dt_obj):
            if not isinstance(dt_obj, datetime): return dt_obj
            return dt_obj.replace(tzinfo=dt_tz.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

        for r in rows:
            for k in ("created_at", "open_at", "close_at", "settled_at"):
                if k in r and r[k]:
                    r[k] = iso_z(r[k])

        return rows

    except Exception as e:
        raise HTTPException(500, f"History error: {e}")

@app.post("/api/free-gpt", response_model=ChatResponse, dependencies=[Depends(require_auth)])
@app.post("/api/chat",     response_model=ChatResponse, dependencies=[Depends(require_auth)])
async def free_gpt(req: ChatRequest):
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="OpenAI API key is not configured")

    messages = _build_messages(req)
    model = _pick_openai_model(req)
    temperature = float(req.temperature or 0.6)

    text = await call_openai(messages, model, temperature)
    if not text:
        raise HTTPException(status_code=502, detail="OpenAI is unavailable")

    return ChatResponse(reply=_normalize_reply(text))


@app.get("/api/admin/me")
async def admin_me(admin: Dict[str, Any] = Depends(require_admin)):
    return {
        "ok": True,
        "role": admin["role"],
        "tg_uid": admin["tg_uid"],
        "permissions": admin["permissions"],
    }


@app.get("/api/admin/settings")
async def admin_settings(admin: Dict[str, Any] = Depends(require_admin_scope("settings"))):
    keys = sorted(ADMIN_SETTING_KEYS)
    placeholders = ",".join(["%s"] * len(keys))
    rows = await DB.fetchall_dict(
        f"SELECT skey, svalue, updated_at FROM app_settings WHERE skey IN ({placeholders}) ORDER BY skey ASC",
        tuple(keys),
    )
    return rows


@app.post("/api/admin/settings")
async def admin_settings_update(payload: AdminSettingPatch, admin: Dict[str, Any] = Depends(require_admin_scope("settings"))):
    key = payload.key.strip().upper()
    if key not in ADMIN_SETTING_KEYS:
        raise HTTPException(400, "Unsupported setting key")
    await setting_set(key, payload.value)
    return {"ok": True}


@app.get("/api/admin/statuses")
async def admin_statuses(admin: Dict[str, Any] = Depends(require_admin_scope("statuses"))):
    rows = await DB.fetchall_dict(
        """
        SELECT code, name_ru, name_en, name_in, min_deposit, sort_order, is_active, updated_at
        FROM user_statuses
        ORDER BY min_deposit ASC, sort_order ASC
        """
    )
    return rows


@app.post("/api/admin/statuses")
async def admin_statuses_upsert(payload: AdminStatusPatch, admin: Dict[str, Any] = Depends(require_admin_scope("statuses"))):
    code = payload.code.strip().upper()
    await DB.execute(
        """
        INSERT INTO user_statuses (code, name_ru, name_en, name_in, min_deposit, sort_order, is_active)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            name_ru=VALUES(name_ru),
            name_en=VALUES(name_en),
            name_in=VALUES(name_in),
            min_deposit=VALUES(min_deposit),
            sort_order=VALUES(sort_order),
            is_active=VALUES(is_active),
            updated_at=UTC_TIMESTAMP()
        """,
        (
            code,
            payload.name_ru,
            payload.name_en,
            payload.name_in,
            float(payload.min_deposit),
            int(payload.sort_order),
            1 if payload.is_active else 0,
        ),
    )
    return {"ok": True}


@app.get("/api/admin/list")
async def admin_list(admin: Dict[str, Any] = Depends(require_admin_scope("admins"))):
    rows = await DB.fetchall_dict(
        """
        SELECT tg_id, role, is_active, permissions_json, created_at
        FROM admin_users
        ORDER BY tg_id
        """
    )
    return rows


@app.post("/api/admin/users/upsert")
async def admin_users_upsert(payload: AdminUserPatch, admin: Dict[str, Any] = Depends(require_admin_scope("admins"))):
    permissions_json = None
    if payload.permissions is not None:
        permissions_json = json.dumps(sorted(set(payload.permissions)), ensure_ascii=False)

    await DB.execute(
        """
        INSERT INTO admin_users (tg_id, role, is_active, permissions_json)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          role=VALUES(role),
          is_active=VALUES(is_active),
          permissions_json=VALUES(permissions_json),
          updated_at=UTC_TIMESTAMP()
        """,
        (
            int(payload.tg_id),
            payload.role,
            1 if payload.is_active else 0,
            permissions_json,
        ),
    )
    return {"ok": True}


@app.post("/api/admin/broadcast/draft")
async def admin_broadcast_draft(payload: AdminBroadcastDraft, admin: Dict[str, Any] = Depends(require_admin_scope("mailing"))):
    return {
        "ok": True,
        "stub": True,
        "message": "Broadcast module is in draft mode",
        "preview": {
            "title": payload.title,
            "body": payload.body,
            "lang": payload.lang,
        },
    }


@app.get(f"/{ADMIN_PRIVATE_PATH}", response_class=HTMLResponse)
async def hidden_admin_entry():
    return HTMLResponse(
        """
        <!doctype html>
        <html>
          <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>Admin Center</title>
            <style>
              body { margin:0; font-family: ui-sans-serif, system-ui; background:#071529; color:#f1d58e; display:grid; place-items:center; min-height:100vh; }
              .card { max-width:680px; width:92%; border:1px solid #b08b3a; border-radius:16px; padding:28px; background:#0b1d36; }
              h1 { margin-top:0; }
              code { color:#fff; }
            </style>
          </head>
          <body>
            <section class="card">
              <h1>Admin Center Entry</h1>
              <p>Server-side access is protected by Telegram initData + admin role checks.</p>
              <p>Use <code>/api/admin/me</code> from your admin frontend.</p>
            </section>
          </body>
        </html>
        """
    )


# ======================= Фоны / задачи планировщика =======================

async def auto_settle():
    try:
        rows = await DB.fetchall_dict("""
            SELECT id
            FROM signals_log
            WHERE status = 'IN_PROGRESS'
              AND close_at < UTC_TIMESTAMP()
        """)
        if rows:
            print(f"[AUTO_SETTLE] Найдено {len(rows)} сигналов для закрытия")

        for row in rows:
            try:
                res = await settle(row["id"])
                print(f"[AUTO_SETTLE OK] id={row['id']} → {res}")
            except Exception as e:
                print(f"[AUTO_SETTLE ERROR] id={row['id']} → {e}")
    except Exception as e:
        print(f"[AUTO_SETTLE FAIL] Ошибка при проверке сигналов: {e}")
