from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def openai_strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Return a Pydantic schema compatible with OpenAI strict structured output."""

    schema = model.model_json_schema()

    def make_objects_strict(node: Any) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = list(properties)
                node["additionalProperties"] = False
            for value in node.values():
                make_objects_strict(value)
        elif isinstance(node, list):
            for value in node:
                make_objects_strict(value)

    make_objects_strict(schema)
    return schema
