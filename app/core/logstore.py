"""Anonymous question log. Stores only the question, answer and a few counters, never who asked."""

import json
import re
import uuid
from dataclasses import asdict, dataclass
from typing import Protocol

import httpx

LOG_TTL_SECONDS = 90 * 24 * 60 * 60  # 7776000
DAILY_TTL_SECONDS = 2 * 24 * 60 * 60  # 172800

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# A run that starts and ends on a digit and may contain spaces, dashes, parens and dots inside.
_PHONE = re.compile(r"\+?\(?\d[\d\s().-]*\d")


def _mask_phone(match: re.Match[str]) -> str:
    digits = sum(char.isdigit() for char in match.group())
    return "[phone]" if digits >= 8 else match.group()


def redact(text: str) -> str:
    """Replace emails and phone-like numbers so personal data never reaches the log."""
    return _PHONE.sub(_mask_phone, _EMAIL.sub("[email]", text))


@dataclass(frozen=True)
class LogRecord:
    question: str
    answer: str
    kind: str
    sources: list[str]
    latency_ms: int
    date: str


class LogStore(Protocol):
    async def save(self, record: LogRecord) -> None: ...

    async def incr_daily(self, day: str) -> int: ...


class MemoryStore:
    def __init__(self) -> None:
        self.records: list[LogRecord] = []
        self._daily: dict[str, int] = {}

    async def save(self, record: LogRecord) -> None:
        self.records.append(record)

    async def incr_daily(self, day: str) -> int:
        self._daily[day] = self._daily.get(day, 0) + 1
        return self._daily[day]


class UpstashStore:
    """Upstash Redis over its REST API (one `POST /pipeline` call per operation)."""

    def __init__(self, url: str, token: str, *, http: httpx.AsyncClient) -> None:
        self._url = url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}
        self._http = http

    async def _pipeline(self, commands: list[list[str]]) -> list[dict]:
        response = await self._http.post(
            f"{self._url}/pipeline", json=commands, headers=self._headers
        )
        response.raise_for_status()
        return response.json()

    async def save(self, record: LogRecord) -> None:
        key = f"log:{uuid.uuid4()}"
        command = ["SET", key, json.dumps(asdict(record)), "EX", str(LOG_TTL_SECONDS)]
        await self._pipeline([command])

    async def incr_daily(self, day: str) -> int:
        key = f"daily:{day}"
        results = await self._pipeline([["INCR", key], ["EXPIRE", key, str(DAILY_TTL_SECONDS)]])
        return int(results[0]["result"])
