"""
Aura Studio — token server for a browser voice agent on the AssemblyAI Voice
Agent API.

This server does just two things:

    Browser  ──(GET /api/voice-token)──►  this server  ──(GET /v1/token)──►  AssemblyAI
    Browser  ══(wss://agents.assemblyai.com/v1/ws?token=…)══════════════════►  AssemblyAI

The agent is configured inline from the browser (system prompt, voice, and tools
in `session.update`), and its tools are simple in-browser mocks that *simulate*
availability and booking — nothing is wired to a real calendar. The API key never
leaves the server; the browser holds only a short-lived, single-use token.

Run:  python3 salon.py   then open  http://localhost:3000
"""

import json
import os
from pathlib import Path

from aiohttp import ClientSession, web


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


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index_handler)
    app.router.add_get("/api/voice-token", token_handler)
    return app


if __name__ == "__main__":
    print("\n  Aura Studio voice appointment setter")
    print(f"  Open http://localhost:{PORT}\n")
    web.run_app(make_app(), port=PORT, print=None)
