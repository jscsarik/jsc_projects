"""Replaceable blind draft policy; this module has no database access."""
import random
from typing import Protocol, Sequence

from .draft import BlindCandidate, DraftError


class BlindDraftPolicy(Protocol):
    def choose(self, candidates: Sequence[BlindCandidate]) -> str: ...


class RandomBlindPolicy:
    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.SystemRandom()

    def choose(self, candidates: Sequence[BlindCandidate]) -> str:
        if not candidates:
            raise DraftError("지명 가능한 후보가 없습니다.")
        return self.rng.choice(candidates).id


class EstimatedDraftPolicy:
    """Same published ranges as the player; no database or actual CA/PA access."""
    def choose(self,candidates):
        if not candidates:raise DraftError('지명 가능한 후보가 없습니다.')
        return min(candidates,key=lambda c:(-c.estimated_overall,-max(e.midpoint for e in c.estimates),c.age,c.id)).id
