# ask-vitor

A FastAPI service that answers questions with a local LLM (via [Ollama](https://ollama.com)), grounded in a small knowledge base. The sample knowledge base is about me: ask it about my experience, projects and stack. Swap in your own snippets in `app/knowledge/data.py`.

The model answers only from that context, in 1–3 sentences, and returns a fixed fallback instead of guessing when the answer isn't there.

## How it works

`POST /ask` → `QAService` gets the knowledge base from a `ContextProvider`, builds a grounded prompt (answer only from context, 1–3 sentences, fixed fallback when unknown) and sends it to the LLM through the `LLMClient` interface (Ollama implementation). The answer is returned as JSON.

## Prerequisites

| Tool | Install (Windows) |
|------|-------------------|
| [uv](https://docs.astral.sh/uv/) — manages Python 3.11 + deps | `winget install astral-sh.uv` |
| [Ollama](https://ollama.com/download) — runs the local LLM | `winget install Ollama.Ollama` |
| GNU make (optional) | `winget install ezwinports.make` (or use `mingw32-make`) |

## Quickstart

```powershell
make install   # Python 3.11 + dependencies
make env       # create .env from .env.example (optional)
make model     # ollama pull qwen2.5:0.5b
make dev       # http://127.0.0.1:8000/docs
```

Without make: `uv sync`, `ollama pull qwen2.5:0.5b`, `uv run fastapi dev app/main.py`.

## Usage

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/ask `
  -ContentType "application/json" `
  -Body '{"question": "Where has Vitor worked?"}'
```

```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Where has Vitor worked?"}'
```

Response:

```json
{"question": "Where has Vitor worked?", "answer": "..."}
```

| Status | When |
|--------|------|
| `200` | Answer generated. Questions outside the knowledge base get `"I don't have information about that."` |
| `422` | `question` missing, blank, or longer than 500 characters |
| `503` | Ollama is unreachable or failed |

## Configuration

Set via environment variables or `.env` (see `.env.example`):

| Variable | Default |
|----------|---------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` |
| `OLLAMA_MODEL` | `qwen2.5:0.5b` |
| `OLLAMA_TIMEOUT_SECONDS` | `60` |

## Commands

Recipes in the `Makefile` run in PowerShell 7 (`pwsh`). Run `make help` to list them:

| Command | Does |
|---------|------|
| `make install` | Install Python 3.11 + dependencies |
| `make env` | Create `.env` from `.env.example` |
| `make model` | `ollama pull` the configured model (`make model OLLAMA_MODEL=...` to override) |
| `make dev` / `make run` | Run the API with / without auto-reload |
| `make test` | Run tests (no Ollama needed — the LLM is faked) |
| `make lint` / `make format` | Check / fix lint and formatting |
| `make check` | Lint + tests |
| `make clean` | Remove caches |

## Project layout

```
app/
  main.py             # app factory, lifespan, error handlers
  core/               # settings, exceptions
  api/                # routes + dependency wiring
  schemas/            # request/response models
  knowledge/          # knowledge base + context providers
  prompts/            # prompt templates
  llm/                # LLM client interface + Ollama implementation
  services/           # question-answering orchestration
tests/
```
