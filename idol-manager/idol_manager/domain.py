from dataclasses import dataclass
import random

from .config import SKILLS
from .health_rules import cap_health


@dataclass(frozen=True)
class Person:
    id: str
    name: str
    name_key: str
    photo_path: str


@dataclass(frozen=True)
class PublicIdol:
    """Only these fields may reach the roster UI."""
    id: str
    name: str
    photo_path: str
    age: int
    status: str


def generate_skill_distribution(rng: random.Random, overall: int, kind: dict) -> dict[str, int]:
    """Shape eight abilities while keeping their sum exactly overall * 8.

    The shared overall level is independent of archetype. Specialty boosts use
    part of that fixed budget; the remaining skills share the rest. Bounded
    transfers add variety without changing the sum or crossing 0/100.
    """
    count = rng.randint(*kind["specialty_count"])
    specialties = rng.sample(list(SKILLS), count)
    others = [skill for skill in SKILLS if skill not in specialties]
    # Reserve a feasible specialty budget even at unusual configured levels.
    boost_cap = min(100 - overall, overall * len(others) // count)
    values = {
        skill: overall + min(boost_cap, rng.randint(*kind["specialty_boost"]))
        for skill in specialties
    }
    remaining = overall * len(SKILLS) - sum(values.values())
    base, remainder = divmod(remaining, len(others))
    rng.shuffle(others)
    values.update({skill: base + (index < remainder) for index, skill in enumerate(others)})
    low = max(0, base - kind["spread"])
    high = min(100, base + 1 + kind["spread"], overall)
    for _ in range(len(others) * 3):
        donor, receiver = rng.sample(others, 2)
        amount = rng.randint(0, max(0, min(values[donor] - low, high - values[receiver])))
        values[donor] -= amount
        values[receiver] += amount
    return {skill: int(values[skill]) for skill in SKILLS}


def generate_attributes(rng: random.Random, settings: dict, *, age_context: str = "initial_draft") -> dict:
    # Context keys allow a later annual-rookie rule without reusing draft ages.
    # No annual appearance mechanics are implemented here.
    age_range = settings["age_rules"][age_context]
    overall = rng.randint(*settings["overall_level"])
    kinds = settings["archetypes"]
    kind = rng.choices(kinds, weights=[item["weight"] for item in kinds], k=1)[0]
    skills = generate_skill_distribution(rng, overall, kind)
    potentials = {
        skill: min(100, value + rng.randint(*settings["potential_gain"]))
        for skill, value in skills.items()
    }
    return {
        "age": rng.randint(*age_range),
        "health": cap_health(rng.randint(*settings["health"])),
        "archetype": kind["name"],
        "skills": skills,
        "potentials": potentials,
        "average": sum(skills.values()) / len(SKILLS),
    }
