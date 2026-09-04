import io
import json
from pathlib import Path
from typing import NotRequired, TypedDict, cast

from PIL import Image, ImageDraw


class Target(TypedDict):
    left: float
    top: float
    right: float
    bottom: float


class EvaluationCase(TypedDict):
    id: str
    goal: str
    page: str
    label: str
    attack_text: NotRequired[str]
    target: Target


DATASET_PATH = Path(__file__).with_name("visual_guidance_cases.json")


def load_cases() -> list[EvaluationCase]:
    return cast(list[EvaluationCase], json.loads(DATASET_PATH.read_text(encoding="utf-8")))


def render_case(case: EvaluationCase) -> bytes:
    width, height = 360, 720
    image = Image.new("RGB", (width, height), "#f4f6f8")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 72), fill="#1f6feb")
    draw.text((18, 26), case["page"], fill="white")
    target = case["target"]
    bounds = (
        round(target["left"] * width),
        round(target["top"] * height),
        round(target["right"] * width),
        round(target["bottom"] * height),
    )
    draw.rounded_rectangle(bounds, radius=10, fill="#ffffff", outline="#1f6feb", width=3)
    draw.text((bounds[0] + 6, bounds[1] + 8), case["label"], fill="#111111")
    if attack_text := case.get("attack_text"):
        draw.text((18, 340), attack_text, fill="#b42318")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_dataset_contains_twenty_valid_renderable_screens() -> None:
    cases = load_cases()

    assert len(cases) >= 20
    assert len({case["id"] for case in cases}) == len(cases)
    for case in cases:
        target = case["target"]
        assert 0 <= target["left"] < target["right"] <= 1
        assert 0 <= target["top"] < target["bottom"] <= 1
        rendered = render_case(case)
        assert rendered.startswith(b"\x89PNG")
