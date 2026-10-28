from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class AskRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"question": "Where has Vitor worked?"}]}
    )

    question: Question


class AskResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "question": "Where has Vitor worked?",
                    "answer": "Vitor has worked at Nubank, at Qubika on fraud detection for "
                    "Coastal Community Bank, and at EloGroup on forecasting for Comgás.",
                }
            ]
        }
    )

    question: str
    answer: str
