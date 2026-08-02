"""Editor DTO validation and domain mapping behavior."""

import pytest
from pydantic import ValidationError

from guojing.application.tutorial_drafts.dto import TutorialDraftDocumentDto
from guojing.application.tutorials.dto import ScreenAnchorDto
from guojing.domain.tutorials.authoring import TutorialDraftDocument
from tests.tutorial_factory import make_complete_draft_document


def test_empty_partial_document_round_trips() -> None:
    dto = TutorialDraftDocumentDto()

    assert dto.to_domain() == TutorialDraftDocument()
    assert TutorialDraftDocumentDto.model_validate_json(dto.model_dump_json()) == dto


def test_complete_document_round_trips_without_losing_graph_data() -> None:
    document = make_complete_draft_document()

    assert TutorialDraftDocumentDto.from_domain(document).to_domain() == document


def test_local_only_capture_rejects_backend_artifact_references() -> None:
    payload = {
        "captures": [
            {
                "capture_id": "capture-1",
                "sharing_policy": "local_only",
                "artifacts": [
                    {
                        "artifact_id": "asset-1",
                        "kind": "screenshot",
                        "sha256": "a" * 64,
                    }
                ],
            }
        ]
    }

    with pytest.raises(ValidationError, match="local-only"):
        TutorialDraftDocumentDto.model_validate(payload)


def test_accepted_ai_candidate_rejects_missing_reviewer() -> None:
    anchor = make_complete_draft_document().graph.nodes[0].anchors[0]
    payload = {
        "captures": [
            {
                "capture_id": "capture-1",
                "sharing_policy": "sanitized",
                "candidates": [
                    {
                        "candidate_id": "candidate-1",
                        "source": "ai",
                        "suggested_anchor": ScreenAnchorDto.from_domain(anchor).model_dump(
                            mode="json"
                        ),
                        "decision": "accepted",
                    }
                ],
            }
        ]
    }

    with pytest.raises(ValidationError, match="admin reviewer"):
        TutorialDraftDocumentDto.model_validate(payload)
