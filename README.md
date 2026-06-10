# Aura Studio — Voice Appointment Setter

A browser-based voice agent that books appointments by **talking**. Built on the
[AssemblyAI Voice Agent API](https://www.assemblyai.com/docs/voice-agents/voice-agent-api).

Say *"what's open Friday?"* and the calendar lights up. Say *"book me a haircut at
2pm, my name's Alex"* and the slot turns green — all hands-free, no typing.

![Aura Studio](https://www.assemblyai.com/docs/voice-agents/voice-agent-api) <!-- swap for a screenshot/gif -->

## Why this exists

It's a small, complete reference for building **production-shaped** voice apps on
AssemblyAI:

- **The API key never touches the browser.** The backend mints a short-lived,
  single-use **temporary token**; the browser connects directly to AssemblyAI with it.
- **Tools drive the UI.** When the agent calls a tool, the browser executes it,
  updates the calendar, and returns the result to the agent — so what you *hear*
  and what you *see* stay in sync.
- **No build step, no framework.** One Python file, one HTML file.

## Architecture

```
Browser ──(GET /api/voice-token)──►  Backend  ──(GET /v1/token)──►  AssemblyAI
Browser ══(wss://agents.assemblyai.com/v1/ws?token=…)══════════════►  AssemblyAI   ← direct, key-free
Browser ──(GET /api/availability, POST /api/book)──►  Backend  (the "calendar DB")
```

- **`salon.py`** — aiohttp server. Mints temp tokens, serves the UI, and exposes
  `/api/availability` + `/api/book` as a stand-in calendar database (swap these
  helpers for your real CRM/scheduler).
- **`salon.html`** — single-file frontend. Captures mic audio (PCM16 @ 24 kHz via
  an `AudioWorklet`), streams it to the Voice Agent API, plays back the reply
  through a ring-buffer worklet, renders the live week calendar, and executes the
  agent's `tool.call`s client-side.

The agent has two tools:

| Tool                | What it does                                              |
| ------------------- | -------------------------------------------------------- |
| `get_availability`  | Look up open slots for a day → highlights that day on the calendar |
| `book_appointment`  | Book a slot → flips the cell to green and returns a confirmation # |

## Quick start

Requires **Python 3.11+**.

```bash
pip install -r requirements.txt

# Add your AssemblyAI key (https://www.assemblyai.com/app)
cp .env.example .env        # then edit .env
# ...or just:  export ASSEMBLYAI_API_KEY=your_key

python3 salon.py
```

Open **http://localhost:3000**, click **Start conversation**, allow the mic, and talk.

> Mic access requires a secure origin — `localhost` counts, so local dev works.
> To run it remotely, serve over HTTPS.

## How the temp-token flow works

1. The browser calls `GET /api/voice-token` on this server.
2. The server calls AssemblyAI's `GET /v1/token` with the API key in the
   `Authorization` header and returns just the token.
3. The browser opens `wss://agents.assemblyai.com/v1/ws?token=<token>` directly.

Tokens are single-use and short-lived (5 min redemption window here). Fetch a
fresh one for every connection. See the
[browser integration docs](https://www.assemblyai.com/docs/voice-agents/voice-agent-api/browser-integration).

## Customizing

- **Make it your business:** edit `BUSINESS_NAME`, `SERVICES`, and hours in
  `salon.py`; tweak the persona in `systemPrompt()` and the brand in `salon.html`.
- **Real data:** replace `_prebooked`, `make_booking`, and the availability
  helpers with calls to your scheduler/CRM.
- **Voice & turn-taking:** change `VOICE` in `salon.html`
  ([voice catalog](https://www.assemblyai.com/docs/voice-agents/voice-agent-api/voices))
  and add `input.turn_detection` to the `session.update`.

## License

MIT
