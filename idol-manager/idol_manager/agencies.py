"""Stable agency identities and game-start funds (KRW)."""
from dataclasses import dataclass

INITIAL_FUNDS_KRW = 1_000_000_000


@dataclass(frozen=True)
class Agency:
    id: str
    name: str
    logo_path: str
    funds_krw: int


AGENCY_SEEDS = (
    ("ador", "ADOR", "assets/agencies/ADOR.png"),
    ("belift", "BELIFT", "assets/agencies/BELIFT.png"),
    ("bighit", "BIGHIT", "assets/agencies/BIGHIT.png"),
    ("cube", "CUBE", "assets/agencies/CUBE.png"),
    ("dsp", "DSPmedia", "assets/agencies/DSPmedia.png"),
    ("jyp", "JYP entertainment", "assets/agencies/JYP entertainment.png"),
    ("sm", "SM entertainment", "assets/agencies/SM entertainment.png"),
    ("source", "SOURCE MUSIC", "assets/agencies/SOURCE MUSIC.png"),
    ("starship", "STARship", "assets/agencies/STARship.png"),
    ("yg", "YG entertainment", "assets/agencies/YG entertainment.png"),
)

CAREER_STATUSES = ("unassigned", "pro_pending", "first_team", "second_team", "fa", "retired", "trainee")
