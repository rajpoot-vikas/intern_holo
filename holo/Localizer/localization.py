import json
from typing import Any, Literal

from pydantic import BaseModel


def get_localization_prompt(image, instruction: str) -> list[dict[str, Any]]:
    guidelines: str = "Localize an element on the GUI image according to my instructions and output a click position as Click(x, y) with x num pixels from the left edge and y num pixels from the top edge."

    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "image": image,
                },
                {"type": "text", "text": f"{guidelines}\n{instruction}"},
            ],
        }
    ]


class ClickAction(BaseModel):
    """Click at specific coordinates on the screen."""

    action: Literal["click"] = "click"
    x: int
    """The x coordinate, number of pixels from the left edge."""
    y: int
    """The y coordinate, number of pixels from the top edge."""


def get_localization_prompt_structured_output(image, instruction: str) -> list[dict[str, Any]]:
    guidelines: str = "Localize an element on the GUI image according to my instructions and output a click position. You must output a valid JSON format."

    return [
        {
            "role": "system",
            "content": json.dumps([ClickAction.model_json_schema()]),
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "image": image,
                },
                {"type": "text", "text": f"{guidelines}\n{instruction}"},
            ],
        },
    ]
