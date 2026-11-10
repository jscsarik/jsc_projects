"""Public match inputs and replayable outputs. No database or Qt dependency."""
from dataclasses import dataclass, asdict
from .config import SKILLS
from .condition_rules import PublicCondition


class MatchError(ValueError):
    pass


class UnresolvedMatch(MatchError):
    """No fabricated winner: the prepared match remains blocked and unscored."""


@dataclass(frozen=True)
class MatchPlayer:
    id: str
    agency_id: str
    name: str
    health: int
    skills: tuple[int, ...]
    franchise: bool=False

    def value(self, skill):
        return self.skills[SKILLS.index(skill)]


@dataclass(frozen=True)
class MatchTeam:
    agency_id: str
    players: tuple[MatchPlayer, ...]
    leader_id: str | None
    representative_id: str | None


@dataclass(frozen=True)
class MatchInput:
    match_id: str
    content_id: str
    required: int
    main_skills: tuple[str, ...]
    teams: tuple[MatchTeam, MatchTeam]
    # Per-player effective probabilities, frozen before any rolls; default value/100.
    probabilities: dict[str, dict[str, float]]

    def to_dict(self):
        return input_dict(self)

    @classmethod
    def from_dict(cls, data):
        teams = tuple(MatchTeam(t['agency_id'], tuple(MatchPlayer(
            p['id'], p['agency_id'], p['name'], p['health'], tuple(p['skills']),p.get('franchise',False))
            for p in t['players']), t['leader_id'], t['representative_id']) for t in data['teams'])
        return cls(data['match_id'], data['content_id'], data['required'],
                   tuple(data['main_skills']), teams, data['probabilities'])


@dataclass(frozen=True)
class Judgment:
    sequence: int
    agency_id: str
    person_id: str
    phase: str
    skill: str
    tick: int
    round_number: int
    attempt: int
    probability: float
    roll: float
    success: bool


@dataclass(frozen=True)
class MatchResult:
    match_id: str
    resolution: str
    winner_id: str | None
    loser_id: str | None
    teams: tuple[dict, ...]
    players: tuple[dict, ...]
    events: tuple[Judgment, ...]
    teamwork: tuple=()

    def summary(self):
        return {key: value for key, value in asdict(self).items() if key != 'events'}

    @classmethod
    def restore(cls, summary, events):
        return cls(summary['match_id'], summary['resolution'], summary['winner_id'],
                   summary['loser_id'], tuple(summary['teams']), tuple(summary['players']), tuple(events),tuple(summary.get('teamwork',())))

def input_dict(value):
    data=asdict(value)
    for team in data['teams']:
        for player in team['players']:
            if not player.get('franchise'):player.pop('franchise',None)
    return data


@dataclass(frozen=True)
class MatchFixture:
    id: str
    season: int
    week: int
    weekday: int
    day_order: int
    content_name: str
    main_abilities: tuple[str, ...]
    required: int | None
    status: str
    agencies: tuple[tuple[str, str], ...]
    player_agency_id: str | None
    run_state: str | None
    block_reason: str

    @property
    def player_participates(self):
        return any(a[0] == self.player_agency_id for a in self.agencies)


@dataclass(frozen=True)
class LineupOption:
    player: MatchPlayer
    photo_path: str
    is_leader: bool
    available: bool = True
    condition: PublicCondition | None = None


@dataclass(frozen=True)
class MatchSelection:
    fixture: MatchFixture
    options: tuple[LineupOption, ...]
    selection_count: int
    fixed_ids: tuple[str, ...] | None
