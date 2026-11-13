# Website TALK Dialogue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** jvitorcosta.github.io publishes `knowledge.json` on every build and gets the "▶ ASK ME"
button, the TALK dialogue that streams answers from the ask-vitor API, and a website privacy page.

**Architecture:** The stdlib build gains a pure `homepage/knowledge.py` that turns hand-written facts
(`data/about.toml`), public repos and the latest live item per source into `knowledge.json`. The
renderer adds the button, a TALK action and a hidden dialogue section; a separate
`assets/ask.js` does the streaming. Everything is gated on `ask_api` in `data/links.toml`, so the
site ships safely before the API is live.

**Tech Stack:** Python 3.12 standard library (build), pytest, plain JS and CSS (no build step).

**Spec:** `D:\dev\projects\ask-vitor\docs\superpowers\specs\2026-11-12-ask-vitor-website-embed-design.md`.
API side and the shared **Contracts** (knowledge.json shape, SSE events):
`D:\dev\projects\ask-vitor\docs\superpowers\plans\2026-11-12-hosted-ask-vitor-api.md` — read that section first.

**Repo:** `D:\dev\projects\jvitorcosta.github.io`. Before starting, check `git status`, open
branches and PRs; if another session has open work touching `homepage/render.py`,
`assets/site.js`, `assets/site.css` or `data/strings.toml`, stop and ask Vitor. Branch:
`git switch -c feat/ask-vitor main`.

## Global Constraints

- Build stays Python stdlib only; no new runtime dependency. Tests with pytest (`uv run pytest`).
- `data/strings.toml`: every new key in both `[en]` and `[pt]`.
- WCAG AA in both palettes (Nu Purple, Red Lantern); keyboard reachable; `aria-live="polite"` on
  the answer, `role="alert"` on errors; focus moves to the input when the dialogue opens.
- No cookies, no tracking, no third-party request on page load. The API is called only after the
  visitor opens TALK.
- `knowledge.json` holds only public facts and never any never-share item (spec list). Strava:
  sport and distance only — no title, date, map, place, health or heart-rate data.
- Fixed replies are handled by `kind` from the API, never by matching text.
- Copy (EN / PT), exact:
  - greeting: `Hi! I'm a bot that knows Vitor's CV, projects and what he's been up to lately. What do you want to know?` /
    `Oi! Sou um bot que conhece o currículo, os projetos e o que o Vitor anda fazendo. O que você quer saber?`
  - notice: `Answers come only from this site, my CV and my repos. Questions are saved anonymously to improve answers.` /
    `As respostas vêm só deste site, do meu currículo e dos meus repositórios. As perguntas são salvas anonimamente para melhorar as respostas.`
  - fallback hint: `Try asking about my work, projects, education or hobbies, or email me.` /
    `Pergunte sobre meu trabalho, projetos, formação ou hobbies, ou me mande um e-mail.`
  - rate limited: `I need a short break. Try again in a minute.` / `Preciso de uma pausa. Tente de novo em um minuto.`
  - down: `I can't answer right now. My CV is here.` / `Não consigo responder agora. Meu currículo está aqui.`
- Commit only with Vitor's OK; Conventional Commits.

## Review Focus

- A page built with no `ask_api` link must look exactly as today (no button, no section, no script) — Task 3.
- An SSE frame split across network chunks, or a token containing `\n` — Task 4's manual check
  uses the API's real stream; the parser mirrors `web/lib/askStream.ts` from ask-vitor.
- Switching EN ⇄ PT with the dialogue open: labels switch; the next question is asked in the new
  language (send nothing extra, the model follows the question) — Task 4.
- A Letterboxd review or Strava title containing an address or phone number must not reach
  `knowledge.json` (they are excluded by field, not filtered) — Task 2.
- A visitor double-clicks ASK or presses Enter twice: one request at a time, the second is ignored — Task 4.

---

### Task 1: Hand-written facts (`data/about.toml`)

**Files:**
- Create: `data/about.toml`, `tests/test_about.py`
- Modify: `homepage/content.py` (`Content.about`), `homepage/model.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class AboutFact: id: str; source: str; text: str` in `model.py`.
- Produces: `Content.about: list[AboutFact]`, loaded from `[[fact]]` tables (`id`, `source`, `text`);
  a missing file → `[]`; a bad row → warning and skipped, like `activity.toml`.

- [ ] **Step 1: Write failing tests** in `tests/test_about.py` against the real `data/about.toml`:
  `test_ids_unique_and_well_formed` (`^[a-z0-9._-]+$`), `test_every_fact_has_source_and_text`,
  `test_no_never_share_content` — no `@`, no run of ≥8 digits, and none of these as whole words
  (case-insensitive, `\b` boundaries, so "Pará" doesn't trip "pai")
  `salary`, `salário`, `address`, `endereço`, `bairro`, `heart rate`, `injury`, `injuries`, `lesão`, `cpf`,
  `not working`, `unemployed`, `girlfriend`, `namorada`, `father`, `pai`; and
  `test_load_content_reads_about` with a tmp fixture.
- [ ] **Step 2: Run** `uv run pytest tests/test_about.py -v` → FAIL.
- [ ] **Step 3: Write `data/about.toml`.**
  - Personal facts (`source = "About Vitor"`, ids `about.*`): the spec's "Personal facts" list,
    one fact per bullet, wording as approved.
  - CV facts (`source = "CV · Experience"`, `"CV · Education"`, `"CV · Skills"`, `"CV · Projects"`,
    ids `cv.*`): drafted from `D:\dev\projects\curriculum-vitae\main\` (`summaries.md`,
    `experience/*.md`, `education.md`, `skills.md`, `projects/`, `languages.md`), limited to what
    the public resume PDF and LinkedIn already show: roles, companies, dates, responsibilities,
    first job, education, main skills, languages. No numbers or claims that aren't in `main/`.
    Never copy anything from `private/`.
  - **Stop and show Vitor the full file before committing**; he approves the wording.
- [ ] **Step 4: Implement** the loader; run `uv run pytest` → PASS.
- [ ] **Step 5: Commit** `feat: hand-written facts for the Ask Vitor knowledge file`

### Task 2: Build `knowledge.json`

**Files:**
- Create: `homepage/knowledge.py`, `tests/test_knowledge.py`
- Modify: `homepage/build.py`, `.gitignore`, `tests/test_build.py`, `docs/architecture.md`

**Interfaces:**
- Consumes: `Content.about`, `Repo`, `LiveData`, `state["updated"]`.
- Produces: `build_knowledge(about: list[AboutFact], repos: list[Repo], live: LiveData, updated: dict[str, str], today: str) -> dict`
  returning the Contract shape; `write_knowledge(path: Path, data: dict) -> None` (sorted keys,
  `ensure_ascii=False`, LF, byte-identical for equal input).

| Fact id | source | text built from |
|---|---|---|
| `about.*`, `cv.*` | as written | `AboutFact.text`, `updated = today` |
| `repo.<name>` | `GitHub` | name, description, url |
| `live.song` | `Spotify` | title, artist ("last played") |
| `live.film` | `Letterboxd` | title, year, rating, liked — no review |
| `live.book` | `Goodreads` | title, author, reading or finished |
| `live.anime` | `MyAnimeList` | title, watching or finished, episode/episodes |
| `live.activity` | `Strava` | sport and distance only |

`updated` for `live.*` and `repo.*` comes from `updated[name]` (`"song"`, `"film"`, `"book"`,
`"anime"`, `"activity"`, `"repos"`); a source with no item produces no fact.

- [ ] **Step 1: Write failing tests:** `test_contract_shape` (`version == 1`, unique ids),
  `test_film_has_no_review` (a `Film` with review `"Rua X 123, call 99999-0000"` → text contains
  neither), `test_activity_only_sport_and_distance` (`title="Morning run at Ponta Negra"` → no
  "Ponta Negra", no date), `test_missing_sources_are_skipped`, `test_build_writes_knowledge_json`
  (in `test_build.py`: file exists, parses, and a second build is byte-identical).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; call it at the end of `build()` writing `<root>/knowledge.json`; add
  `knowledge.json` to `.gitignore` next to `index.html` (the Pages artifact uploads the whole
  folder, so it deploys without a workflow change). Add it to the "built files" box in `docs/architecture.md`.
- [ ] **Step 4: Run** `uv run pytest` → PASS; `uv run python -m homepage` → `knowledge.json`
  exists; open it and check no never-share item appears.
- [ ] **Step 5: Commit** `feat: publish knowledge.json for Ask Vitor on every build`

### Task 3: Button, TALK action and dialogue markup

**Files:**
- Modify: `homepage/render.py`, `data/strings.toml`, `data/links.toml`, `tests/test_render.py`

**Interfaces:**
- Consumes: `links["ask_api"]` (absent or empty → feature off), `links["resume"]`, `links["email"]`.
- Produces markup that Task 4 relies on:
  - header: `<button type="button" class="ask-open" data-ask-open>▶ ASK ME</button>` (PT `▶ PERGUNTE`)
    inside `<header class="top">`, before the language button;
  - trainer card: `<button type="button" data-ask-open>▶ TALK</button>` (PT `▶ FALAR`) first in `nav.links`;
  - after `#trainer`: `<section class="box ask" id="ask" hidden data-endpoint="{ask_api}/ask/stream" aria-labelledby="ask-title">`
    with `#ask-title` (`VITOR:`), `.ask-answer[aria-live=polite]`, `.ask-sources`, `.ask-chips`,
    `<form class="ask-form">` (input `maxlength="500"`, submit `A`, a STOP button `hidden`),
    `.ask-error[role=alert][hidden]`, the notice with a link to `site-privacy.html`;
  - `<script src="assets/ask.js" defer></script>` before `</body>`;
  - every text in both languages via `p.both` / `p.t`; suggested questions as
    `<button type="button" data-ask-q>` chips.
- New `strings.toml` keys (EN and PT): `ask_open`, `ask_talk`, `ask_greeting`, `ask_notice`,
  `ask_placeholder`, `ask_stop`, `ask_fallback_hint`, `ask_rate_limited`, `ask_down`,
  `ask_suggest` (3 questions, `|`-separated), `ask_followups` (6 questions, `|`-separated),
  `privacy_link`. Copy from Global Constraints; suggestions are my call, e.g.
  `What do you do for work?|What's your best project?|What are you watching lately?`.

- [ ] **Step 1: Write failing tests:** `test_no_ask_api_means_no_ask_markup` (no `data-ask-open`,
  no `id="ask"`, no `ask.js`), `test_ask_api_renders_button_section_and_script`,
  `test_ask_section_starts_hidden_with_endpoint`, `test_ask_strings_in_both_languages`.
- [ ] **Step 2: Run** `uv run pytest tests/test_render.py -v` → FAIL.
- [ ] **Step 3: Implement.** Leave `ask_api` empty in `data/links.toml` until the API is deployed
  (comment: "ask-vitor API base URL; empty hides Ask Vitor").
- [ ] **Step 4: Run** `uv run pytest` → PASS.
- [ ] **Step 5: Commit** `feat: ASK ME button and TALK dialogue markup, hidden until the API is set`

### Task 4: `assets/ask.js` and dialogue styles

**Files:**
- Create: `assets/ask.js`
- Modify: `assets/site.css`, `tests/test_assets.py`

**Interfaces:**
- Consumes: Task 3 markup; the SSE Contract (`token`, `done` with `kind`/`sources`, `error`; 422/429/503).
- Behaviour (states from the spec's table):
  - any `[data-ask-open]` → unhide `#ask`, scroll to it, focus the input; Escape or a close
    control hides it and returns focus.
  - submit or chip → one request at a time (ignore while streaming); clear the previous answer;
    `fetch(endpoint, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({question}), signal})`;
    parse SSE frames with a buffer split on `\n\n` (same algorithm as ask-vitor `web/lib/askStream.ts`);
    append tokens with a blinking cursor; STOP aborts and keeps the partial text.
  - `done`: `kind == "answer"` → render each source as `[label · updated]` (`updated` as a short
    date in the page language) and 2 follow-up chips not asked yet; `fallback` → show the hint
    with the `mailto:` link; `off_topic` → one suggestion chip.
  - `429` → rate-limited text; `503`, network failure or `event: error` → down text with the
    resume link; `422` → keep the input, show nothing new (the input's `maxlength` prevents most).
  - Never insert API text as HTML (`textContent` only); source `label` and `updated` too.
- Styles: reuse `.box` tokens; thicker border (4px) for `.ask`, `VITOR:` in Press Start 2P,
  cursor blink with `@media (prefers-reduced-motion: reduce)` turning it off, full width on
  narrow screens, `.ask-open` styled like the language button.

- [ ] **Step 1: Write failing tests** in `tests/test_assets.py`: `ask.js` exists, uses no
  `innerHTML`, and contains no URL (the endpoint comes from `data-endpoint`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `ask.js` and the CSS.
- [ ] **Step 4: Verify by hand:** set `ask_api = "http://127.0.0.1:8000"` locally (don't commit),
  run ask-vitor with `make dev` and `CORS_ORIGINS` including the local site origin, build and serve
  the site (`uv run python -m homepage`, `python -m http.server 8080`), then in the browser check:
  open via both buttons; an answer streams with sources; `"What's his salary?"` shows the
  fallback hint; `"Write me a poem"` shows the off-topic state; STOP; EN ⇄ PT switch; stop the API
  → down state; keyboard only; both palettes; 375 px width. Then `uv run pytest` → PASS.
- [ ] **Step 5: Commit** `feat: TALK dialogue streams answers from Ask Vitor`

### Task 5: Website privacy page

**Files:**
- Create: `site-privacy.html`
- Modify: `homepage/render.py` (`_footer` gains the `privacy_link`), `sitemap.xml`, `tests/test_render.py`

**Interfaces:**
- Consumes: `strings["privacy_link"]` (Task 3).
- Leave `privacy.html` (the Google OAuth app's policy) unchanged.

- [ ] **Step 1: Write failing test** `test_footer_links_site_privacy_page` (footer contains
  `href="site-privacy.html"` in both languages) and `test_site_privacy_page_exists`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Write** `site-privacy.html` in the case-page style (EN and PT on the page, same
  CSS), stating: no cookies, analytics or tracking; on page load the only outside request is
  Vitor's Spotify server; when you use Ask Vitor, your question goes to the ask-vitor API on
  Vercel and to Anthropic to generate the answer; what is saved (question, answer, sources,
  whether it fell back, time taken, date), with emails and phone numbers removed; what is never
  saved (IP address, browser details, cookies); deletion after 90 days; contact email.
  Add the footer link and the sitemap entry.
- [ ] **Step 4: Run** `uv run pytest` → PASS; open the page in both palettes.
- [ ] **Step 5: Commit** `docs: privacy page for the website and Ask Vitor`

### Task 6: Turn it on

Run only after the API plan's Task 9 is deployed and smoke-tested.

- [ ] **Step 1:** Set `ask_api` in `data/links.toml` to the deployed Vercel URL; `uv run pytest` → PASS.
- [ ] **Step 2:** Update `README.md` and `docs/sources.md` / `docs/design.md` (one section each:
  what Ask Vitor is, the knowledge file, the dialogue, privacy page).
- [ ] **Step 3: Commit** `feat: turn on Ask Vitor`; open a PR with Vitor's OK; after the Pages
  deploy, repeat Task 4's browser checklist on `https://jvitorcosta.github.io`.
