"""
Aura Studio — voice appointment setter built on the AssemblyAI Voice Agent API.

Architecture (browser connects DIRECTLY to AssemblyAI via a temporary token):

    Browser  ──(GET /api/voice-token)──►  this server  ──(GET /v1/token)──►  AssemblyAI
    Browser  ══(wss://agents.assemblyai.com/v1/ws?token=…)══════════════════►  AssemblyAI
    Browser  ──(GET /api/availability, POST /api/book)──►  this server (the "calendar DB")

The API key never leaves the server. The browser holds only a short-lived,
single-use token. Tools execute client-side (see salon.html) so the calendar UI
updates the instant the agent acts — the browser calls the endpoints below and
returns the result to the agent.

Run:  python3 salon.py   then open  http://localhost:3000
"""

import json
import os
import random
from datetime import date, datetime, timedelta
from pathlib import Path

from aiohttp import ClientSession, web

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

def _load_dotenv() -> None:
    """Minimal .env loader (no dependency) — only sets vars not already set."""
    env_file = Path(__file__).with_name(".env")
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _load_api_key() -> str:
    _load_dotenv()
    key = os.environ.get("ASSEMBLYAI_API_KEY")
    if key:
        return key
    cfg = Path.home() / ".config" / "aai" / "config.json"
    if cfg.exists():
        data = json.loads(cfg.read_text())
        if data.get("assemblyai_api_key"):
            return data["assemblyai_api_key"]
    raise SystemExit(
        "No API key. Set ASSEMBLYAI_API_KEY (env or .env file) "
        "or add it to ~/.config/aai/config.json"
    )

API_KEY = _load_api_key()
TOKEN_URL = "https://agents.assemblyai.com/v1/token"
PORT = int(os.environ.get("PORT", 3000))

BUSINESS_NAME = "Aura Studio"
OPEN_HOUR = 9       # 9:00 AM
CLOSE_HOUR = 17     # last slot starts 4:30 PM
SLOT_MINUTES = 30
DAYS_AHEAD = 7      # show a rolling week

SERVICES = {
    "haircut": {"label": "Haircut", "minutes": 30},
    "color": {"label": "Color", "minutes": 60},
    "styling": {"label": "Styling", "minutes": 30},
    "consultation": {"label": "Consultation", "minutes": 30},
}

# ─────────────────────────────────────────────────────────────────────────────
# "Calendar DB" — in-memory. Swap these helpers for real CRM / scheduler calls.
# ─────────────────────────────────────────────────────────────────────────────

# bookings[iso_date] = { "HH:MM": {"name", "service", "confirmation"} }
BOOKINGS: dict[str, dict[str, dict]] = {}


def _all_slots() -> list[str]:
    slots = []
    h, m = OPEN_HOUR, 0
    while h < CLOSE_HOUR or (h == CLOSE_HOUR and m == 0):
        if h == CLOSE_HOUR and m > 0:
            break
        slots.append(f"{h:02d}:{m:02d}")
        m += SLOT_MINUTES
        if m >= 60:
            m -= 60
            h += 1
    return slots


def _prebooked(iso: str) -> set[str]:
    """Deterministic 'already taken' slots so the calendar looks lived-in.

    Seeded by date, so a given day always shows the same pre-existing bookings.
    Sundays are closed.
    """
    d = datetime.strptime(iso, "%Y-%m-%d").date()
    if d.weekday() == 6:  # Sunday closed
        return set(_all_slots())
    rng = random.Random(iso)
    slots = _all_slots()
    # ~40% of slots pre-taken
    taken = rng.sample(slots, k=max(1, int(len(slots) * 0.4)))
    return set(taken)


def week_dates() -> list[str]:
    today = date.today()
    return [(today + timedelta(days=i)).isoformat() for i in range(DAYS_AHEAD)]


def day_view(iso: str) -> dict:
    d = datetime.strptime(iso, "%Y-%m-%d").date()
    taken = _prebooked(iso) | set(BOOKINGS.get(iso, {}).keys())
    mine = set(BOOKINGS.get(iso, {}).keys())
    slots = []
    for s in _all_slots():
        slots.append({
            "time": s,
            "label": _fmt_time(s),
            "available": s not in taken,
            "mine": s in mine,
        })
    return {
        "date": iso,
        "weekday": d.strftime("%A"),
        "label": d.strftime("%a %b %-d"),
        "closed": d.weekday() == 6,
        "slots": slots,
    }


def week_view() -> list[dict]:
    return [day_view(iso) for iso in week_dates()]


def _fmt_time(hhmm: str) -> str:
    h, m = map(int, hhmm.split(":"))
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}"


def make_booking(iso: str, time_hhmm: str, name: str, service: str) -> dict:
    taken = _prebooked(iso) | set(BOOKINGS.get(iso, {}).keys())
    if time_hhmm in taken:
        return {"ok": False, "reason": "That time was just taken. Please pick another."}
    if time_hhmm not in _all_slots():
        return {"ok": False, "reason": "That time isn't a valid slot."}
    conf = f"AUR-{random.randint(1000, 9999)}"
    BOOKINGS.setdefault(iso, {})[time_hhmm] = {
        "name": name,
        "service": service,
        "confirmation": conf,
    }
    return {
        "ok": True,
        "confirmation": conf,
        "date": iso,
        "weekday": datetime.strptime(iso, "%Y-%m-%d").strftime("%A"),
        "time": time_hhmm,
        "time_label": _fmt_time(time_hhmm),
        "name": name,
        "service": service,
    }

# ─────────────────────────────────────────────────────────────────────────────
# HTTP handlers
# ─────────────────────────────────────────────────────────────────────────────

async def index_handler(request: web.Request) -> web.StreamResponse:
    return web.FileResponse(Path(__file__).with_suffix(".html"))


async def token_handler(request: web.Request) -> web.Response:
    """Mint a short-lived, single-use Voice Agent token. API key stays here."""
    params = {"expires_in_seconds": "300", "max_session_duration_seconds": "1800"}
    async with ClientSession() as http:
        async with http.get(
            TOKEN_URL, params=params, headers={"Authorization": f"Bearer {API_KEY}"}
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                return web.Response(status=resp.status, text=body)
            token = json.loads(body)["token"]
    return web.json_response({"token": token})


async def availability_handler(request: web.Request) -> web.Response:
    iso = request.query.get("date")
    if iso:
        try:
            datetime.strptime(iso, "%Y-%m-%d")
        except ValueError:
            return web.json_response({"error": "date must be YYYY-MM-DD"}, status=400)
        return web.json_response(day_view(iso))
    return web.json_response({"week": week_view()})


async def book_handler(request: web.Request) -> web.Response:
    data = await request.json()
    iso = data.get("date", "")
    time_hhmm = data.get("time", "")
    name = (data.get("name") or "").strip() or "Guest"
    service = data.get("service") or "appointment"
    try:
        datetime.strptime(iso, "%Y-%m-%d")
    except ValueError:
        return web.json_response({"ok": False, "reason": "Invalid date."}, status=400)
    return web.json_response(make_booking(iso, time_hhmm, name, service))


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index_handler)
    app.router.add_get("/api/voice-token", token_handler)
    app.router.add_get("/api/availability", availability_handler)
    app.router.add_post("/api/book", book_handler)
    return app


if __name__ == "__main__":
    print(f"\n  {BUSINESS_NAME} voice appointment setter")
    print(f"  Open http://localhost:{PORT}\n")
    web.run_app(make_app(), port=PORT, print=None)
