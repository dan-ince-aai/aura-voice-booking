# Build walkthrough — voice booking agent in the browser

A presenter-friendly narrative for building this app from scratch on the
[AssemblyAI Voice Agent API](https://www.assemblyai.com/docs/voice-agents/voice-agent-api).
Each step is one idea; the ⚠️ callouts are the two mistakes that are easy to make
live, so they make good "watch out for this" moments.

The finished app is two files: a tiny Python token server (`salon.py`) and a
single-page browser client (`salon.html`). Everything else is the Voice Agent API.

---

## The mental model

Speech in, speech out, over one WebSocket. The browser streams microphone audio
up; the API streams the agent's spoken reply back. You configure the agent once
(prompt, voice, tools) and then just move audio. When the agent decides to use a
tool, you run it and hand back the result.

```
mic → PCM16 → WebSocket → AssemblyAI → reply audio → speakers
                              │
                         tool.call → you run it → tool.result
```

---

## Step 1 — Keep the API key off the browser (temp token)

The browser must never see your AssemblyAI key. So the only job of the backend is
to mint a **short-lived, single-use token**: the browser asks our server, our
server calls `GET /v1/token` with the real key, and hands back just the token.

- Server: [`salon.py`](salon.py) → `token_handler` (calls `/v1/token`, returns `{ token }`).
- Browser: `start()` fetches `/api/voice-token` before connecting.

Tokens are single-use — fetch a fresh one for **every** connection.

## Step 2 — Capture microphone audio as PCM16 @ 24 kHz

The API wants raw PCM16 mono at 24 kHz. In the browser:

- `new AudioContext({ sampleRate: 24000 })` so we don't have to resample on the way up.
- `getUserMedia({ audio: { echoCancellation: true, noiseSuppression: false } })` —
  echo cancellation is what lets it run hands-free on a laptop without the agent
  hearing itself.
- An **`AudioWorklet`** (`capture-processor`) converts float samples to Int16 and
  posts ~50 ms chunks, which we base64-encode and send as `input.audio` events.

## Step 3 — Connect and configure the agent inline

Open `wss://agents.assemblyai.com/v1/ws?token=<token>`. On `open`, send one
`session.update` with the whole agent definition — prompt, greeting, voice, tools:

```js
ws.send(JSON.stringify({
  type: "session.update",
  session: { system_prompt, greeting, tools, output: { voice } },
}));
```

Then wait for `session.ready` before streaming audio. (See `systemPrompt()` and
`toolDefs()` in [`salon.html`](salon.html).)

## Step 4 — Play the agent's audio back

Each `reply.audio` event is a base64 PCM16 chunk. We decode it to float and push
it into a **ring-buffer `AudioWorklet`** (`playback-processor`) that drains it to
the speakers at a steady rate — smooth playback even if chunks arrive bursty.

> ⚠️ **Gotcha #1 — the `process()` argument order.** An `AudioWorkletProcessor`'s
> callback is `process(inputs, outputs, params)` — **inputs first**. For the
> playback node (which has no input connected), if you write `process(outputs)`
> you're actually reading the *inputs* array, it's empty, and you silently emit
> nothing. The agent looks like it's talking (state flips to "speaking") but you
> hear silence. Take **both** args and write into `outputs[0][0]`.

## Step 5 — Render the conversation from events

Drive the whole UI off the event stream — no polling:

- `transcript.user.delta` → live partial of what the caller is saying
- `transcript.user` → finalized caller turn
- `transcript.agent` → the agent's turn
- `input.speech.started` / `reply.audio` / `reply.done` → the orb's
  listening / speaking / thinking states

(See `handleEvent()` in [`salon.html`](salon.html).)

## Step 6 — Give the agent tools, and run them client-side

Declare tools in `session.update`. When the model wants one, the API sends a
`tool.call` with `name` + `arguments`; you run it and send back a `tool.result`.
Here the tools are **simulated** in the browser — `get_availability` returns a few
open times, `book_appointment` returns a fake confirmation number — and each call
is shown as a marker in the transcript. Swap them for real `fetch` calls when you
want a real calendar.

> ⚠️ **Gotcha #2 — *when* to send `tool.result`.** When the agent calls a tool it
> usually speaks a transition phrase first ("sure, let me check") — that's its own
> `reply.started → reply.audio → reply.done` cycle. If you fire `tool.result` the
> instant your function returns (mid-phrase), the agent ignores it and the booking
> never lands. The rule: send the result only when **`reply.done` is the latest
> event you've received**. We *buffer* completed results and *drain* them in the
> `reply.done` handler (`pendingResults` + `flushResults()` in
> [`salon.html`](salon.html)).

## Step 7 — Handle interruptions (barge-in)

If the caller talks over the agent, the API sends `reply.done` with
`status: "interrupted"`. We flush the playback ring buffer (so stale audio stops
immediately) and discard any pending tool results from the cut-off turn.

---

## Demo script for the talk

1. Run `python3 salon.py`, open `http://localhost:3000`, click **Start**.
2. "What's open on Friday?" → point out the `get_availability` marker appearing in
   the feed, then the agent reading back the times.
3. "Book me a haircut at 2pm, my name's Alex." → the `book_appointment` marker, then
   the agent confirming a confirmation number.
4. Interrupt it mid-sentence to show barge-in.

## If you want to go further

- **Real bookings:** replace `runTool()` with `fetch` calls to your scheduler.
- **Phone / stored agent:** instead of configuring inline, you can create a stored
  agent via REST and deploy the same `agent_id` to a phone number — see
  [Deploy your agent](https://www.assemblyai.com/docs/voice-agents/voice-agent-api/deploy).
  (Note: server-side **HTTP tools** require that stored-agent path.)
- **Tuning:** add `input.turn_detection` to `session.update` to adjust barge-in
  sensitivity.
