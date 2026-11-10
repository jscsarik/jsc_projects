"""Post-draft public values. Hidden fields are deliberately absent."""
from dataclasses import dataclass

from .agencies import Agency
from .config import SKILLS
from .game_clock import GameDate


@dataclass(frozen=True)
class SquadMember:
    id: str
    name: str
    photo_path: str
    age: int
    squad: str
    average: float
    health: int
    vocal: int
    dance: int
    rap: int
    entertainment: int
    appearance: int
    physique: int
    intelligence: int
    leadership: int

    @property
    def skill_values(self) -> tuple[int, ...]:
        return tuple(getattr(self,skill) for skill in SKILLS)


@dataclass(frozen=True)
class SquadPlan:
    first_team_ids: tuple[str, ...]
    first_leader_id: str
    second_leader_id: str


@dataclass(frozen=True)
class SquadSnapshot:
    agency: Agency | None
    management_date: GameDate | None
    ready: bool
    reason: str
    initialized: bool
    revision: int
    members: tuple[SquadMember, ...]
    leaders: tuple[tuple[str, str], ...]
