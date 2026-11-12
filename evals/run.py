"""Run the question set against one or more models and write the results.

uv run python -m evals.run --models qwen2.5:0.5b qwen2.5:1.5b llama3.2:3b
uv run python -m evals.run --backend anthropic --models claude-haiku-5-5 \
    --knowledge evals/knowledge.sample.json
"""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

import anthropic
import httpx

from app.core.config import get_settings
from app.knowledge.context import JsonKnowledgeProvider, StaticKnowledgeProvider
from app.knowledge.facts import KnowledgeProvider
from app.llm.anthropic import AnthropicClient
from app.llm.base import LLMClient
from app.llm.ollama import OllamaClient
from app.services.qa import QAService
from evals.scoring import Case, Scored, Summary, markdown_table, score, summarize

EVALS_DIR = Path(__file__).resolve().parent
QUESTIONS = EVALS_DIR / "questions.json"
RESULTS_DIR = EVALS_DIR / "results"


def load_cases(path: Path = QUESTIONS) -> list[Case]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        Case(
            id=item["id"],
            kind=item["kind"],
            question=item["question"],
            expect=tuple(tuple(group) for group in item.get("expect", [])),
            lang=item.get("lang", "en"),
        )
        for item in raw
    ]


async def run_model(
    model: str, cases: list[Case], llm: LLMClient, knowledge: KnowledgeProvider, *, warm_up: bool
) -> list[Scored]:
    service = QAService(llm, knowledge)
    if warm_up:
        await service.answer("Warm-up: load the model before timing.")
    facts = await knowledge.get_facts()
    context = [fact.text for fact in facts]
    known_ids = {fact.id for fact in facts}

    results = []
    for case in cases:
        start = time.perf_counter()
        answer = await service.answer(case.question)
        latency = time.perf_counter() - start
        results.append(
            score(
                case,
                answer.text,
                latency,
                context=context,
                cited=answer.cited_ids,
                known_ids=known_ids,
            )
        )
        print(f"  {case.id:<20} {results[-1].verdict:<14} {latency:5.2f}s")
    return results


def write_results(model: str, results: list[Scored]) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    rows = [
        {
            "id": r.case.id,
            "kind": r.case.kind,
            "lang": r.case.lang,
            "question": r.case.question,
            "answer": r.answer,
            "verdict": r.verdict,
            "unsupported_numbers": list(r.unsupported_numbers),
            "latency_s": round(r.latency_s, 3),
        }
        for r in results
    ]
    payload = {"model": model, "summary": asdict(summarize(model, results)), "results": rows}
    path = RESULTS_DIR / f"{model.replace(':', '-').replace('/', '-')}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_summary(results_dir: Path = RESULTS_DIR) -> str:
    """Rebuild summary.md from every model's results file, not only this run's models."""
    summaries = [
        Summary(**json.loads(path.read_text(encoding="utf-8"))["summary"])
        for path in sorted(results_dir.glob("*.json"))
    ]
    table = markdown_table(summaries)
    (results_dir / "summary.md").write_text(table + "\n", encoding="utf-8")
    return table


async def main(backend: str, models: list[str], knowledge_path: str | None) -> None:
    settings = get_settings()
    api_key = settings.anthropic_api_key
    if backend == "anthropic" and (api_key is None or not api_key.get_secret_value()):
        sys.exit("ANTHROPIC_API_KEY is not set: add it to .env or the environment.")

    cases = load_cases()
    async with httpx.AsyncClient(
        base_url=settings.ollama_base_url, timeout=settings.ollama_timeout_seconds
    ) as http:
        knowledge: KnowledgeProvider = (
            JsonKnowledgeProvider(knowledge_path, http=http)
            if knowledge_path
            else StaticKnowledgeProvider()
        )
        for model in models:
            print(f"{model} ({len(cases)} questions)")
            llm: LLMClient
            if backend == "anthropic":
                assert api_key is not None
                client = anthropic.AsyncAnthropic(api_key=api_key.get_secret_value())
                llm = AnthropicClient(client, model=model, max_tokens=settings.max_output_tokens)
            else:
                llm = OllamaClient(http, model)
            results = await run_model(model, cases, llm, knowledge, warm_up=backend == "ollama")
            write_results(model, results)

    print()
    print(write_summary())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate ask-vitor against an LLM backend.")
    parser.add_argument(
        "--backend",
        choices=["ollama", "anthropic"],
        default="ollama",
        help="Which LLM to evaluate (default: ollama).",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=None,
        help="Model names to evaluate (default: OLLAMA_MODEL, or ANTHROPIC_MODEL for anthropic).",
    )
    parser.add_argument(
        "--knowledge",
        default=None,
        help="Path to a knowledge.json snapshot (default: the built-in knowledge base).",
    )
    args = parser.parse_args()
    default_model = (
        get_settings().anthropic_model
        if args.backend == "anthropic"
        else get_settings().ollama_model
    )
    asyncio.run(main(args.backend, args.models or [default_model], args.knowledge))
