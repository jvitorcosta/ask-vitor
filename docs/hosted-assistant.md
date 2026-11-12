# Study notes: the hosted assistant (Claude Haiku 5.5 behind the portfolio site)

This document explains how ask-vitor became a public assistant on Vitor's website, how each piece
works, and why it was done this way. It is written as a study guide: each section names the
concept, shows where it lives in the code, and lists the trade-offs. It builds on
[streaming-and-web-ui.md](streaming-and-web-ui.md), which covers the streaming itself.

## What was added, in one picture

```
jvitorcosta.github.io (static page, owns knowledge.json)
   │  POST /ask/stream  {"question": "..."}
   ▼
FastAPI on Vercel  (app/main.py, app/api/routes/qa.py)
   │  enforce_limits: hourly per visitor, then the daily cap   (app/api/dependencies.py)
   ▼
QAService (app/services/qa.py)
   │  facts from the site's knowledge.json (cached 15 min)     (app/knowledge/context.py)
   │  grounded prompt with the facts inside                    (app/prompts/qa.py)
   ▼
AnthropicClient.stream_chat (app/llm/anthropic.py)  ──►  Claude Haiku 5.5
   │  tokens → SourcesTrailer hides "<<sources: …>>"           (app/services/sources.py)
   ▼
SSE: token frames, then  event: done  {"kind": …, "sources": […]}
   │
   └─ after the answer: an anonymous, redacted log record      (app/core/logstore.py)
```

The same code still runs locally against Ollama (`LLM_BACKEND=ollama`, the default). The hosted
mode is the same service with a different LLM client, a different knowledge source and three
cost and abuse protections.

## 1. Grounding with a knowledge file, not retrieval

File: `app/knowledge/facts.py`, `app/knowledge/context.py`, `app/prompts/qa.py`.

The site publishes one file, `knowledge.json`: a list of **facts**, each with an `id`, a `source`
label, an `updated` date and the `text`. The API loads it (`KNOWLEDGE_SOURCE`) and puts **every
fact into the prompt**, as `[id] text` lines inside a `<context>` block. The model is told to
answer only from that block.

Why not retrieval (embeddings, a vector store)? The file is small enough to fit in the prompt
every time. Retrieval adds a database, an embedding model and a new way to fail (fetching the
wrong snippet). Putting everything in the prompt has none of that, and with prompt caching
(section 6) the repeated part is cheap. The trade-off is that it stops scaling if the file grows
past what is sensible to send with every question; at that point retrieval becomes worth its
cost.

How the file is handled:

- `parse_knowledge` validates the shape: `version` must be `1`, ids must match `^[a-z0-9._-]+$`
  and be unique, every field must be a string. Unknown top-level keys are ignored. Anything else
  raises `KnowledgeError`.
- `JsonKnowledgeProvider` caches the parsed facts for 15 minutes (`ttl_seconds=900`). If a refresh
  fails it keeps serving the last good copy; with no copy at all it raises `LLMError`, which the
  API turns into a `503`. A failed refresh also waits out the TTL before retrying, so an outage
  of the site isn't hit on every request.
- With `KNOWLEDGE_SOURCE` empty, `StaticKnowledgeProvider` serves the built-in sample
  (`app/knowledge/data.py`) as facts `base.1`, `base.2`, ...

## 2. The fixed-reply contract and `kind`

File: `app/prompts/qa.py` (the strings), `app/services/replies.py` (the classifier).

The assistant has two fixed replies, each in English and Portuguese:

| kind | English | Portuguese |
|---|---|---|
| `fallback` | `I don't have information about that.` | `Não tenho informação sobre isso.` |
| `off_topic` | `I only answer questions about Vitor.` | `Só respondo perguntas sobre o Vitor.` |

The prompt tells the model to use the one in the question's language, with nothing else added.
Everything that is not one of these is `kind: "answer"`.

The website should not guess the state of the dialogue by matching text, so the API says it:
`reply_kind` compares the finished answer, normalised (lowercase, collapsed whitespace, quotes
and the final period stripped), against the four strings. The result goes out as `kind` in
`/ask`'s JSON and in the final `done` event of `/ask/stream`. The UI picks "unknown",
"off-topic" or "answered" from `kind`.

Trade-off: the match is exact. If the model wraps the fallback in extra words ("Sorry. I don't
have information about that."), it is classified as an `answer`, not a `fallback`. The evals
measure this as the "exact fallback" column, separately from refusing in any wording.

Fixed replies carry no sources: `_build_answer` returns an empty `sources` list for them.

## 3. Citations: the sources trailer

File: `app/prompts/qa.py` (rule 10), `app/services/sources.py`, `app/services/qa.py`.

Visitors see where an answer came from (tags such as `CV · Experience`). To get that without a
second model call, the prompt asks the model to end a real answer with one extra line:

```
Vitor worked at Nubank on fraud detection.
<<sources: cv.nubank, cv.skills>>
```

Why a trailer and not JSON output? Streaming. The answer must reach the visitor token by token,
and a JSON object only parses once it is complete. A plain line at the end costs nothing while
streaming.

The visitor must never see that line, and it arrives token by token like everything else, so it
can be split anywhere: `"<"`, `"<sour"`, `"ces: a"`, `">>"`. `SourcesTrailer.feed` handles this:

- It holds back any ending of the text that could still turn into the marker `<<sources:`
  (`_partial_marker_len`), and releases it as soon as it is clear it was not the marker.
- Once the full marker is seen it stops showing text and collects the rest.
- `finish()` parses the ids between the marker and `>>`: valid ids only, in order, no
  duplicates. A trailer cut off by the token limit still yields what it has.

It is stripped **server-side** because the browser cannot be trusted to do it: any client that
forgets, or any visitor calling the API directly, would see the raw line.

Then `_build_answer` maps ids to facts:

- Ids that are not in the knowledge file are **dropped** from `sources`, so the UI never renders
  a tag for a made-up source.
- `Answer.cited_ids` keeps **all** the cited ids, including the unknown ones. The service hides
  the problem from visitors, but the evals can still see it: an in-scope answer that cites an
  unknown id scores `bad_source`.
- Any `<<` that is still in an answer text scores `leaked_trailer` in the evals, which would mean
  the stripping failed.

## 4. Privacy by design

The strongest guarantee comes from what is *not* in the system.

- **Only public data in the file.** `knowledge.json` is generated by the site and published on
  GitHub Pages, so everything in it is already public. The model cannot leak what it never
  received. Keeping private facts out of the file is the site build's job; this repo cannot
  check it, but the evals use a sample file (`evals/knowledge.sample.json`) so the behaviour is
  tested without touching the real one.
- **A never-share list, in the prompt and in the data.** Rule 7 of the system prompt lists what
  is never shared (address and regular places, health, salary and finances, family details,
  IDs, reasons for leaving jobs, politics and religion, relationships) and says to use the
  fallback even if a fact seems to contain it. That is the second layer, for the day something
  slips into the file. The first layer is not putting it there.
- **No IPs, no cookies.** The visitor key for the rate limiter is the first hop of
  `X-Forwarded-For` (`client_key` in `app/core/ratelimit.py`), or the socket address as a
  fallback. It lives only in the limiter's in-memory dictionary and is never logged or saved.
  The question log has no field for it (section 8).

## 5. Why no `temperature`

File: `app/llm/anthropic.py`.

For a grounded assistant you would normally set temperature 0 so the same question gives the
same answer, and the Ollama runs in the README did. Claude Haiku 5.5 rejects sampling values
other than the default, so the Anthropic request sends no `temperature`, `top_p`, `top_k` or
`thinking`. The consistency has to come from the prompt (fixed replies, short answers, explicit
rules) and from the evals, which check the behaviour instead of assuming it. Run-to-run wording
can still differ; the evals are written to accept any correct wording and to score the contract
(fallback strings, sources, no leaked trailer), not the exact sentence.

## 6. Prompt caching and cost per question

File: `app/llm/anthropic.py` (`_request`).

Each question sends the same large block first: the rules plus every fact. `_request` puts that
system text in one block marked `cache_control: {"type": "ephemeral"}`. Claude can then reuse the
processed prefix across questions for a short time instead of reading it again at full price,
which lowers both cost and latency. Only the visitor's question changes between calls.

Trade-offs to know:

- The cache lives for minutes, so a quiet site gets little from it. A busy burst gets a lot.
- The facts and the prompt must stay byte-identical for a hit. Editing the knowledge file
  (every 15 minutes at most, because of the provider's TTL) starts a new cache entry.
- The output is capped by `MAX_OUTPUT_TOKENS` (default 300); the prompt already asks for 1 to 3
  sentences.

The design estimate was about $0.001 to $0.003 per question. That is an estimate from the
prompt size, not a measurement. At that price the $5 monthly limit (next section) pays for
roughly 1,700 to 5,000 questions, which is more than a personal site should see.

## 7. Three layers against running up the bill

Anyone on the internet can call the API, so three independent limits stand between a visitor and
Vitor's wallet. Each covers a weakness of the others.

| Layer | Where | What it limits | Strength |
|---|---|---|---|
| Hourly per visitor | `RateLimiter` in `app/core/ratelimit.py`, `RATE_LIMIT_PER_HOUR` (default 10) | One visitor flooding | Approximate on Vercel |
| Daily cap | `incr_daily` in `app/core/logstore.py`, `DAILY_QUESTION_CAP` (default 300) | All visitors together, per UTC day | Hard, shared across instances through Upstash |
| Monthly spend limit | Claude Console workspace, $5 | Everything, including a bug in the two above | Hard, enforced by Anthropic |

How the first two work, in `enforce_limits` (`app/api/dependencies.py`):

1. The limiter checks the visitor's key. Over the limit raises `RateLimited`, which the app turns
   into `429 {"detail": "rate_limited"}`.
2. Then the daily counter is incremented (`INCR` on a key per UTC day in Upstash, which expires
   after two days). Over the cap also raises `RateLimited`.

Details that were decided on purpose:

- **The hourly limit is only approximate on Vercel.** The limiter is a sliding window in memory,
  and each serverless instance has its own copy. A visitor whose requests land on different
  instances can get more than 10 an hour. That is acceptable because it is not the protection
  that matters for money; the daily cap and the spend limit are.
- **A `422` does not use quota.** `enforce_limits` takes the request body as a parameter, which
  makes FastAPI validate it first. If validation fails, the limits are never checked and nothing
  is counted.
- **The daily cap fails open.** If the counter store is down, the question is allowed and a
  line is printed (the error type only). A broken counter should not take the site down; the
  Console spend limit is still there.
- **The key never leaves memory.** It is used as a dictionary key and dropped when its window
  empties.

## 8. Anonymous logs and redaction

File: `app/core/logstore.py`, and `_log` in `app/api/routes/qa.py`.

Logs exist to improve the answers. After each answer one record is saved: the question, the
answer, the cited source ids, the `kind`, the latency in milliseconds and the date. There is no
field for an IP, user agent, cookie or session id, so they cannot be stored by accident.

Before saving, `redact` replaces emails with `[email]` and any run of digits (allowing spaces,
dashes, dots and parentheses inside) with 8 or more digits with `[phone]`. It is applied to both
the question and the answer. A visitor who pastes their number into the dialogue does not end up
in the log.

Known quirk: the phone rule is simple, so it also masks year ranges like `2019-2024`
(8 digits) as `[phone]`. That errs in the privacy-safe direction: it hides too much and never
too little.

Storage:

- With `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` set, `UpstashStore` writes each
  record with `SET ... EX 7776000`: the record deletes itself after 90 days, with no cleanup job
  to run or forget.
- Without them, `MemoryStore` keeps records in the process. This is for local runs and tests.
- Saving is best-effort. If it raises, `_log` prints the error to stderr and the visitor still
  gets the answer.

## 9. The evals, and the Haiku row

File: `evals/questions.json`, `evals/scoring.py`, `evals/run.py`, `evals/knowledge.sample.json`.

The question set grew from 28 to 53. The original 28 are unchanged; the new 25 cover personal and
live-data facts, every never-share category (including location probing), Portuguese questions
and off-topic ones. Scoring is rule-based, with no LLM judge:

| Verdict | Meaning |
|---|---|
| `correct` | In-scope answer with the expected facts, no invented numbers, only known source ids |
| `missed` / `wrong` / `invented` | Refused an answerable question / wrong content / used a number from nowhere |
| `bad_source` | Cited an id that is not in the knowledge file |
| `leaked_trailer` | The text still contains `<<` |
| `refused` | Should refuse, and gave the exact fixed reply for the question's language |
| `declined` / `answered` | Should refuse, but refused in its own words / answered anyway |

The fixed reply is accepted in the question's language (`FALLBACKS[case.lang]`), and an
off-topic question also accepts the off-topic reply.

Results. The Ollama rows were measured on the original 28 questions and have not been re-run on
the larger set. The Haiku row is **not run yet**: `make eval-haiku` calls the Claude API, costs a
few cents of Vitor's API credit and needs his `ANTHROPIC_API_KEY`, so it is run by hand when he
decides. No numbers are filled in until then.

| Model | Questions | Passed | Answers correct | Exact fallback | Refuses in any wording | Invented numbers | Latency p50 | Latency p95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `qwen2.5:0.5b` | 28 | 16/28 | 93% | 15% | 31% | 11% | 0.15s | 0.31s |
| `qwen2.5:1.5b` | 28 | 24/28 | 100% | 69% | 77% | 4% | 0.33s | 0.75s |
| `llama3.2:3b` | 28 | 25/28 | 100% | 77% | 92% | 0% | 0.74s | 1.47s |
| `claude-haiku-5-5` | 53 | not run yet | | | | | | |

To fill in the last row:

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."   # or put it in .env
make eval-haiku
```

It runs `python -m evals.run --backend anthropic --models claude-haiku-5-5 --knowledge
evals/knowledge.sample.json`, writes `evals/results/claude-haiku-5-5.json` and rewrites
`evals/results/summary.md`. Note that `summary.md` is rebuilt from only the models in that run,
so keep the other rows from git history or the table above.

## 10. Known limits

- **The hourly limiter is per instance.** See section 7. The real protections are the daily cap
  and the Console spend limit.
- **Prompt injection is reduced, not solved.** Rule 6 sends instruction-like questions to the
  off-topic reply, and two eval questions test it, but a determined visitor can try phrasings
  the eval does not cover. The damage is bounded by design: the model only holds public facts,
  answers are capped at 300 tokens, and the caps limit volume. There is no separate model-side
  check of the answer.
- **The file is trusted.** Whatever is in `knowledge.json` is treated as true and shown to the
  model. A wrong or private fact published there would be repeated.
- **Exact-match `kind`.** A fallback with extra words is classified as an `answer` (section 2).
- **Answers vary in wording** without temperature (section 5).
- **No memory between questions.** Each question is answered alone.
- **Timeouts over retries.** The Claude client has a 30 second timeout and no automatic retries
  (`app/main.py`), so an API problem becomes a quick `503` or `error` event instead of a long
  wait; the page shows its service-down state.

## 11. Python 3.12

Vercel's Python runtime supports 3.12 and newer only, and the repo had pinned 3.11. The project
now targets 3.12 (`requires-python = ">=3.12,<3.13"` in `pyproject.toml`, `.python-version`) so
that what runs locally is what runs in production.

## 12. How it was tested

- Unit tests with fakes (no network, no key): the Anthropic client request shape and error
  mapping (`tests/test_anthropic_client.py`), the sources trailer including splits across tokens
  (`tests/test_sources.py`), the reply classifier (`tests/test_replies.py`), cited ids
  (`tests/test_qa_cited_ids.py`), the log store and redaction (`tests/test_logstore.py`), the
  limiter and the daily cap (`tests/test_ratelimit.py`), the knowledge loader
  (`tests/test_knowledge.py`), the prompt (`tests/test_prompts.py`), the streaming endpoint
  (`tests/test_ask_stream.py`) and the deploy entry point (`tests/test_deploy_entrypoint.py`).
- Scoring is tested without any model (`tests/test_eval_scoring.py`).
- `make check` runs lint and the whole suite.
- The smoke test against the deployed API is in the README ("Hosted mode").
