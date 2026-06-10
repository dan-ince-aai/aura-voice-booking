# Aura Studio — Voice Appointment Setter

A browser-based voice agent that books salon appointments by **talking**. Built on
the [AssemblyAI Voice Agent API](https://www.assemblyai.com/docs/voice-agents/voice-agent-api).

Say *"what's open Friday?"* and *"book me a haircut at 2pm, my name's Alex"* — the
agent checks availability and books it, hands-free. The calendar is **simulated**
in the browser (no real backend), so the whole thing runs locally with just an
AssemblyAI key.

> Building this in a workshop? See **[WALKTHROUGH.md](WALKTHROUGH.md)** for the
> step-by-step build narrative.

## Why this exists

A small, complete reference for a **browser voice agent** on AssemblyAI:

- **The API key never touches the browser.** The backend mints a short-lived,
  single-use **temporary token**; the browser connects directly to AssemblyAI.
- **Agent configured inline.** The browser sends the system prompt, voice, and
  tool definitions in `session.update` over the WebSocket.
- **Client-side tools.** The browser runs the tool calls (here, mocked) and shows
  each one in the transcript, then returns the result to the agent.
- **No build step, no framework.** One Python file, one HTML file.

## Architecture

```
Browser ──(GET /api/voice-token)──►  Backend  ──(GET /v1/token)──►  AssemblyAI
Browser ══(wss://agents.assemblyai.com/v1/ws?token=…)══════════════►  AssemblyAI   ← direct, key-free
        (configures the agent inline; runs tool calls in-browser)
```

- **`salon.py`** — aiohttp server. Mints temp tokens and serves the UI. That's it.
- **`salon.html`** — single-file frontend. Captures mic audio (PCM16 @ 24 kHz via
  an `AudioWorklet`), streams it to the Voice Agent API, plays the reply back
  through a ring-buffer worklet, shows the live transcript, and runs the agent's
  `tool.call`s client-side — displaying each as a marker in the feed.

The agent has two **simulated** tools:

| Tool                | What it does (mock)                                       |
| ------------------- | --------------------------------------------------------- |
| `get_availability`  | Returns a few open times for a given day                  |
| `book_appointment`  | Returns a fake confirmation number                        |

Both are pure in-browser functions — swap them for real `fetch` calls to your
scheduler when you're ready.

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

## Deploy to Railway

This runs on [Railway](https://railway.com) as-is — one web process that reads
`$PORT` and your API key from the environment, and Railway gives it a public HTTPS
URL (which is exactly what the microphone needs).

1. Create a new Railway project **→ Deploy from GitHub repo**, and pick this repo.
2. Under **Variables**, add `ASSEMBLYAI_API_KEY` (your key).
3. Deploy. Railway builds with Nixpacks, installs `requirements.txt`, and runs
   `python salon.py` (see [`railway.toml`](railway.toml)).

Open the assigned `*.up.railway.app` URL and click **Start conversation**.

Or from the CLI:

```bash
npm i -g @railway/cli
railway init
railway up
# then set ASSEMBLYAI_API_KEY in the Railway dashboard (Variables tab)
```

## How the temp-token flow works

1. The browser calls `GET /api/voice-token` on this server.
2. The server calls AssemblyAI's `GET /v1/token` with the API key and returns just
   the token.
3. The browser opens `wss://agents.assemblyai.com/v1/ws?token=<token>` directly.

Tokens are single-use and short-lived (5 min redemption window here). Fetch a fresh
one for every connection. See the
[browser integration docs](https://www.assemblyai.com/docs/voice-agents/voice-agent-api/browser-integration).

## Customizing

- **Make it your business:** tweak the persona in `systemPrompt()` and the tool
  definitions in `toolDefs()` in `salon.html`.
- **Real data:** replace `runTool()` / `mockAvailability()` / `mockBooking()` with
  `fetch` calls to your scheduler or CRM.
- **Voice:** change `VOICE` in `salon.html`
  ([voice catalog](https://www.assemblyai.com/docs/voice-agents/voice-agent-api/voices)).

## License

MIT
