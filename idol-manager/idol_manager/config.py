import json
from pathlib import Path

from .storage import resource_root
ROOT = resource_root()
SKILLS = ("vocal", "dance", "rap", "entertainment", "appearance", "physique", "intelligence", "leadership")


def load_settings(path: Path | None = None) -> dict:
    with (path or ROOT / "config" / "generation.json").open(encoding="utf-8") as stream:
        settings = json.load(stream)
    for key in ("overall_level", "health", "potential_gain"):
        low, high = settings[key]
        if not 0 <= low <= high <= 100:
            raise ValueError(f"잘못된 생성 설정: {key}")
    if "initial_draft" not in settings["age_rules"]:
        raise ValueError("최초 드래프트 나이 규칙이 필요합니다.")
    for context, (low, high) in settings["age_rules"].items():
        if not 0 <= low <= high <= 100:
            raise ValueError(f"잘못된 나이 규칙: {context}")
    types = settings["archetypes"]
    if len(types) == 0 or any(t["weight"] <= 0 for t in types):
        raise ValueError("유형 가중치는 양수여야 합니다.")
    for kind in types:
        for key in ("specialty_boost",):
            low, high = kind[key]
            if not 0 <= low <= high <= 100:
                raise ValueError(f"잘못된 능력치 범위: {key}")
        low, high = kind["specialty_count"]
        if not 1 <= low <= high <= 3:
            raise ValueError("특화 능력치 개수 범위는 1~3이어야 합니다.")
        if not isinstance(kind["spread"], int) or not 0 <= kind["spread"] <= 100:
            raise ValueError("일반 능력치의 분산 폭은 0~100이어야 합니다.")
    if settings["initial_candidates"] < 0:
        raise ValueError("후보 인원은 음수일 수 없습니다.")
    return settings
