"""Pure fatigue/injury rules; percentages are converted to probabilities here."""
from dataclasses import dataclass


def projected_streak(last_day, streak, day):
    if last_day == day:return max(1,streak)
    return streak+1 if last_day == day-1 else 1


def fatigue_penalty(streak):
    return round(min(1.0,max(0,streak-2)*.1),10)


def registration_multiplier(weeks):
    return 1 if weeks<=2 else (weeks-2)*10


def required_rest_weeks(registration_weeks):
    return 0 if registration_weeks<=2 else 1 if registration_weeks==3 else 2


def injury_probability(health,weeks,kind):
    base={'match':.0001,'first_rest':.00005,'second':.0001/3}[kind]
    return min(1.0,max(0.0,(100-health)*base*registration_multiplier(weeks)))


def recovery_day(injured_day):return (injured_day//7+1)*7+1


def return_day(forced_down_day):return forced_down_day+14


@dataclass(frozen=True)
class PublicCondition:
    last_day: int | None
    streak: int
    projected_days: int
    penalty: float
    registration_weeks: int
    injured: bool
    recovery_day: int | None
    return_not_before: int | None
    history_known_since: int
