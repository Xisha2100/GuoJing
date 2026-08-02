"""Framework-independent values returned by tutorial application services."""

from dataclasses import dataclass
from datetime import datetime

from guojing.domain.tutorials.models import TutorialGraph


@dataclass(frozen=True, slots=True)
class TutorialRevision:
    """One immutable saved revision of a tutorial graph."""

    graph: TutorialGraph
    revision_number: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PublishedTutorial:
    """The revision currently visible to Android clients."""

    graph: TutorialGraph
    revision_number: int
    published_at: datetime


@dataclass(frozen=True, slots=True)
class PublishedTutorialSummary:
    """Small catalog entry that avoids transferring every graph at once."""

    graph_id: str
    title: str
    package_name: str
    recorded_version_name: str
    recorded_version_code: int
    revision_number: int
    published_at: datetime
