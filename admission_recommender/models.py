from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True)
class CandidateFilters:
    batch: str
    first_choice: str | None = None
    selected_subjects: Sequence[str] = field(default_factory=tuple)
    skill_category: str | None = None
    art_category: str | None = None
    provinces: Sequence[str] = field(default_factory=tuple)
    cities: Sequence[str] = field(default_factory=tuple)
    major_keyword: str | None = None
    school_natures: Sequence[str] = field(default_factory=tuple)
    exclude_remark_keywords: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class RecommendRequest:
    user_score: float | None = None
    user_rank: float | None = None
    per_level_limit: int = 10


@dataclass(frozen=True)
class RecommendThresholds:
    rank_rush_min: float = -0.10
    rank_rush_max: float = 0.05
    rank_stable_min: float = 0.05
    rank_stable_max: float = 0.25
    rank_safe_min: float = 0.25
    score_rush_min: float = -10
    score_rush_max: float = 5
    score_stable_min: float = 5
    score_stable_max: float = 20
    score_safe_min: float = 20
