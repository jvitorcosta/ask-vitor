# Study notes: streaming answers and the TypeScript web app

This document explains what was added to ask-vitor, how each piece works, and why it was done
this way. It is written as a study guide: each section names the concept, shows where it lives in
the code, and lists the trade-offs.

## What was added, in one picture

```
Browser (Next.js page, TypeScript)
   │  POST /ask/stream  {"question": "..."}        fetch() + ReadableStream
   ▼
FastAPI  (app/api/routes/qa.py)
   │  turns tokens into Server-Sent Events          StreamingResponse
   ▼
QAService (app/services/qa.py)
   │  builds the same grounded prompt as /ask
   ▼
OllamaClient.stream_chat (app/llm/ollama.py)
   │  POST /api/chat {"stream": true}               httpx streaming, NDJSON lines
   ▼
Ollama (local LLM)
```

The original `POST /ask` endpoint is unchanged. `POST /ask/stream` is a second way to get the same
grounded answer, piece by piece.

## 1. Why stream at all?

An LLM generates its answer one token (a word piece) at a time. Without streaming, the user stares
at a blank screen until the last token is ready. With streaming, the first words appear after a
fraction of a second and the rest "types out". The total time is the same; the **perceived**
latency is much lower. That's why every chat product streams.

Two latency numbers matter in LLM products:

- **Time to first token (TTFT):** how long until something appears. Streaming makes this the
  number users feel.
- **Total generation time:** grows with answer length. Short, grounded answers (this project asks
  for 1–3 sentences) keep it low, and so does cost when you pay per token.

## 2. Step one: streaming from Ollama (NDJSON)

File: `app/llm/ollama.py`, method `stream_chat`.

With `"stream": true`, Ollama does not send one JSON response. It sends **NDJSON**
(newline-delimited JSON): one JSON object per line, as the model generates:

```
{"message": {"content": "Vitor"}, "done": false}
{"message": {"content": " has"}, "done": false}
...
{"message": {"content": ""}, "done": true}
```

`httpx` reads this without waiting for the end: `client.stream(...)` opens the response, and
`response.aiter_lines()` yields each line as it arrives. The method is an **async generator**
(`async def` + `yield`), so callers consume it with `async for token in ...`.

Errors (connection refused, HTTP 500, a malformed line) become `LLMError`, the same exception the
non-streaming `chat()` raises, so the rest of the app handles both the same way.

The `LLMClient` protocol in `app/llm/base.py` got the new method too. The service depends on the
protocol, not on Ollama, so a cloud model (OpenAI, Anthropic, Azure OpenAI) could be swapped in by
writing one more class with `chat` and `stream_chat`.

## 3. Step two: from tokens to Server-Sent Events (SSE)

File: `app/api/routes/qa.py`, endpoint `ask_stream`.

The browser needs a format it can parse while the response is still arriving. **Server-Sent
Events** is the standard for "server pushes text to the browser over plain HTTP": a stream of text
frames, each ending with a blank line.

```
data: {"token": "Vitor"}

data: {"token": " has"}

event: done
data: {}

```

Design decisions:

- **`data` is JSON, not raw text.** A token can contain a newline, which would break an SSE frame.
  `json.dumps` escapes it.
- **An explicit `done` event.** Without it, the client cannot tell "the answer is complete" from
  "the connection dropped".
- **An `error` event.** See the next section.

Why SSE and not WebSockets? SSE is one-way (server → browser), which is all an answer needs,
it runs over normal HTTP (proxies, CORS and auth work as usual), and FastAPI supports it with a
plain `StreamingResponse`. WebSockets are for two-way, long-lived conversations.

## 4. The hard part: errors once the stream has started

An HTTP response starts with the status code. Once the first byte of a stream is sent, the status
(200) cannot change anymore. So there are two kinds of failure:

| When it fails | What the client gets | How |
|---|---|---|
| Before the first token (Ollama down, model missing) | **HTTP 503**, same as `/ask` | The endpoint awaits the first token *before* returning the response. `LLMError` reaches the app's 503 handler. |
| In the middle of the answer | HTTP 200, then **`event: error`** | The generator catches `LLMError` and sends an error frame instead of `done`. |

Waiting for the first token costs nothing (the client would wait for it anyway) and keeps the API
honest: a request that never produced anything is reported as a real error status.

Validation is unchanged: the same `AskRequest` model rejects blank or over-500-character questions
with **422** before any LLM call.

## 5. CORS: letting the browser call the API

File: `app/main.py` (`CORSMiddleware`) and `app/core/config.py` (`cors_origins`).

The web app runs on `http://localhost:3000` and the API on `http://127.0.0.1:8000`. Different
port = different **origin**, and browsers block JavaScript from reading responses from another
origin unless the server allows it. Before the real `POST`, the browser sends an `OPTIONS`
"preflight" request asking "may localhost:3000 POST JSON here?". The middleware answers yes, only
for the origins listed in `CORS_ORIGINS`.

Good practice: list exact origins (never `*` together with credentials), and keep the list in
configuration so production can set its real domain without code changes.

## 6. The web app: Next.js + TypeScript

Folder: `web/`. Deliberately small: one page, one client module, one stylesheet.

| File | Role |
|---|---|
| `web/app/layout.tsx` | The HTML shell every page shares (title, `<html lang>`, global CSS). |
| `web/app/page.tsx` | The page: form, example questions, the streaming answer, Stop button, errors. |
| `web/lib/askStream.ts` | Talks to the API: sends the question, parses SSE, yields tokens. |
| `web/app/globals.css` | Plain CSS with light and dark colours. No CSS framework, to keep it readable. |
| `web/.env.example` | `NEXT_PUBLIC_API_URL`, where the API lives. |

### Next.js concepts used

- **App Router:** a file at `app/page.tsx` *is* the `/` route; `app/layout.tsx` wraps it.
- **Server vs client components:** by default Next.js renders components on the server. This page
  needs state (`useState`) and browser APIs (streaming `fetch`), so it starts with
  `"use client"`. Keep that directive on the smallest component that needs it.
- **`NEXT_PUBLIC_` env vars:** inlined into the browser bundle at build time. Fine for a public API
  URL, never for secrets.

### TypeScript concepts used

- **Union types for state:** `type Status = "idle" | "streaming" | "done" | "error"`. The compiler
  rejects any other value, so the UI can't end up in an undefined state.
- **Async generators:** `askStream` is `async function*` and the page consumes it with
  `for await (const token of askStream(...))`. The same idea as the Python side, end to end.
- **A custom error class** (`AskError`) for messages that are safe to show the user, so the page
  can tell them apart from unexpected bugs.
- **`strict: true`** in `tsconfig.json`: no implicit `any`, null checks on. `npm run typecheck`
  runs the compiler without building.

### Reading a stream in the browser

`EventSource`, the browser's built-in SSE client, only supports `GET`. The question goes in a
`POST` body, so `askStream` reads the stream from `fetch` itself:

1. `response.body` is a `ReadableStream` of bytes; `TextDecoderStream` turns it into text.
2. Network chunks don't line up with SSE frames: a chunk can end mid-frame. The code keeps a
   `buffer`, splits it on the blank line (`\n\n`), and carries the unfinished tail to the next
   chunk.
3. Each complete frame becomes a token, `done` (stop) or `error` (throw `AskError`).
4. If the stream ends without `done`, that's an error too ("connection closed").

### UX details (and why)

- **Answer appends as tokens arrive**, with a blinking cursor while streaming.
- **Stop button** uses an `AbortController`: aborting the `fetch` closes the connection, and the
  partial answer stays on screen.
- **Each failure has its own message:** API unreachable, 422 (bad question), 503 (model down),
  model failed mid-answer, connection dropped.
- **`aria-live="polite"`** on the answer so screen readers announce it as it grows;
  `role="alert"` on errors.
- **`maxLength={500}`** on the input mirrors the API's validation, so most 422s never happen.

## 7. How it was tested

- **Python (pytest, no Ollama needed):**
  - `tests/test_ask_stream.py`: the endpoint sends tokens then `done`; 503 when the model fails
    before the first token; an `error` event when it fails mid-answer; 422 validation; the CORS
    preflight allows the web app.
  - `tests/test_ollama_stream.py`: `stream_chat` parses Ollama's NDJSON and turns HTTP errors and
    malformed lines into `LLMError`. It uses `httpx.MockTransport`, a fake server inside the
    test, so no network is involved.
- **TypeScript:** `npm run typecheck` and `npm run build`.
- **By hand, end to end:** real Ollama (`qwen2.5:1.5b`) → API → browser, plus the "API is down"
  message.

## 8. LLM failure modes, and where this project handles them

| Failure mode | Handling here |
|---|---|
| Hallucination | The grounded prompt (answer only from the context, fixed fallback) and the eval set in `evals/` that measures it. |
| Latency | Streaming (time to first token); a small local model; short answers by design. Measured in the eval. |
| Cost | Runs locally (no per-token bill); 1–3 sentence answers keep token counts low either way. |
| Model down / timeout | 503 before the stream starts, `error` event after; `OLLAMA_TIMEOUT_SECONDS`. |
| Prompt injection | Covered by eval questions; known weak spot documented in the README. |

## 9. What I'd add next

- A browser-side test of `askStream` (feed it a fake stream split at awkward places).
- Showing time to first token in the UI.
- Rate limiting, and auth if it were ever public.
