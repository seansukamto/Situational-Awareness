from app.agents.models import AgentProposal
from app.agents.schema import openai_strict_json_schema
from app.game.models import GameLearningNarrative


def test_agent_proposal_schema_requires_nullable_fields_for_openai_strict_mode():
    schema = openai_strict_json_schema(AgentProposal)

    assert schema["required"] == list(schema["properties"])
    assert schema["additionalProperties"] is False
    assert {item.get("type") for item in schema["properties"]["target_id"]["anyOf"]} == {
        "string",
        "null",
    }


def test_learning_narrative_schema_requires_every_output_field():
    schema = openai_strict_json_schema(GameLearningNarrative)

    assert schema["required"] == [
        "summary",
        "patterns",
        "recommendations",
        "task_assessments",
    ]
    assert schema["additionalProperties"] is False
    assessment_schema = schema["$defs"]["TaskLearningAssessment"]
    assert assessment_schema["required"] == list(assessment_schema["properties"])
    assert assessment_schema["additionalProperties"] is False
