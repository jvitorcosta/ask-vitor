"""Run the question set against one or more Ollama models and write the results.

uv run python -m evals.run --models qwen2.5:0.5b qwen2.5:1.5b llama3.2:3b
"""

import argparse
import asyncio
import json
import time
from dataclasses import asdict
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.knowledge.context import StaticContextProvider
from app.knowledge.data import KNOWLEDGE_BASE
from app.llm.ollama import OllamaClient
from app.prompts.qa import FALLBACK_ANSWER
from app.services.qa import QAService
from evals.scoring import Case, Scored, markdown_table, score, summarize

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
        )
        for item in raw
    ]


async def run_model(model: str, cases: list[Case]) -> list[Scored]:
    settings = get_settings()
    async with httpx.AsyncClient(
        base_url=settings.ollama_base_url, timeout=settings.ollama_timeout_seconds
    ) as http:
        service = QAService(OllamaClient(http, model), StaticContextProvider())
        await service.answer("Warm-up: load the model before timing.")

        results = []
        for case in cases:
            start = time.perf_counter()
            answer = await service.answer(case.question)
            latency = time.perf_counter() - start
            results.append(
                score(case, answer, latency, context=KNOWLEDGE_BASE, fallback=FALLBACK_ANSWER)
            )
            print(f"  {case.id:<16} {results[-1].verdict:<9} {latency:5.2f}s")
        return results


def write_results(model: str, results: list[Scored]) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    rows = [
        {
            "id": r.case.id,
            "kind": r.case.kind,
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


async def main(models: list[str]) -> None:
    cases = load_cases()
    summaries = []
    for model in models:
        print(f"{model} ({len(cases)} questions)")
        results = await run_model(model, cases)
        write_results(model, results)
        summaries.append(summarize(model, results))

    table = markdown_table(summaries)
    (RESULTS_DIR / "summary.md").write_text(table + "\n", encoding="utf-8")
    print()
    print(table)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate ask-vitor against Ollama models.")
    parser.add_argument(
        "--models",
        nargs="+",
        default=[get_settings().ollama_model],
        help="Ollama model names to evaluate (default: OLLAMA_MODEL).",
    )
    asyncio.run(main(parser.parse_args().models))
