"""Transport schema and domain mapping behavior."""

import pytest
from pydantic import ValidationError

from guojing.application.tutorials.dto import TutorialGraphDto
from tests.tutorial_factory import make_tutorial_graph


def test_graph_dto_round_trips_without_losing_domain_data() -> None:
    graph = make_tutorial_graph()

    dto = TutorialGraphDto.from_domain(graph)

    assert dto.schema_version == "1.0"
    assert dto.to_domain() == graph
    assert TutorialGraphDto.model_validate_json(dto.model_dump_json()).to_domain() == graph


def test_graph_dto_rejects_unknown_fields() -> None:
    payload = TutorialGraphDto.from_domain(make_tutorial_graph()).model_dump(mode="json")
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        TutorialGraphDto.model_validate(payload)


def test_graph_dto_rejects_an_unknown_schema_version() -> None:
    payload = TutorialGraphDto.from_domain(make_tutorial_graph()).model_dump(mode="json")
    payload["schema_version"] = "2.0"

    with pytest.raises(ValidationError):
        TutorialGraphDto.model_validate(payload)


def test_graph_dto_rejects_a_blank_supplied_locator_value() -> None:
    payload = TutorialGraphDto.from_domain(make_tutorial_graph()).model_dump(mode="json")
    payload["nodes"][0]["anchors"][0]["locator"]["resource_id"] = "valid-id"
    payload["nodes"][0]["anchors"][0]["locator"]["text"] = "   "

    with pytest.raises(ValidationError):
        TutorialGraphDto.model_validate(payload)
