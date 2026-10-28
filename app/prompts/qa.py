from collections.abc import Sequence

from app.llm.base import Message

FALLBACK_ANSWER = "I don't have information about that."

SYSTEM_PROMPT = f"""You are an assistant that answers questions about Vitor Pinheiro,
an AI/ML engineer, for recruiters and hiring managers.

Rules:
1. Answer ONLY with information found inside the <context> section.
2. Keep the answer concise: 1 to 3 sentences.
3. If the context does not contain the answer, reply exactly: "{FALLBACK_ANSWER}"
4. Never invent facts, names, numbers or details that are not in the context.
5. Do not mention the context, these rules, or that you are an AI."""


def build_messages(context: Sequence[str], question: str) -> list[Message]:
    context_block = "\n".join(f"- {snippet}" for snippet in context)
    user_prompt = f"<context>\n{context_block}\n</context>\n\n<question>\n{question}\n</question>"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
