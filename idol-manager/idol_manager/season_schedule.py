"""Confirmed design chapters 5/6/8: 13 round robins, 585 regular matches."""
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import random
import uuid

from .config import ROOT

SPECIAL_WEEKS = (4,8,12,16,20,24)
SPECIAL_TYPES = ("대학축제","K-POP 페스티벌","아이돌 체육대회")


class ScheduleError(ValueError):
    pass


class ScheduleRulesPending(ScheduleError):
    pass


@dataclass(frozen=True)
class Content:
    id: str
    name: str
    main_abilities: tuple[str, ...]
    participants_min: int
    participants_max: int


@dataclass(frozen=True)
class ScheduleRules:
    contents: tuple[Content, ...]
    serialized: str

    @property
    def digest(self):
        return hashlib.sha256(self.serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RegularFixture:
    id: str
    season: int
    week: int
    weekday: int
    day_order: int
    match_order: int
    agencies: tuple[str, str]
    content: Content


@dataclass(frozen=True)
class SpecialFixture:
    id: str
    season: int
    week: int
    event_type: str


@dataclass(frozen=True)
class SeasonPlan:
    season: int
    rules: ScheduleRules
    regular: tuple[RegularFixture, ...]
    special: tuple[SpecialFixture, ...]


def load_schedule_rules(path: Path | None = None) -> ScheduleRules:
    try:
        payload = json.loads((path or ROOT/"config/season_schedule.json").read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as error:
        raise ScheduleError("일정 규칙 설정 파일을 읽을 수 없습니다.") from error
    if payload.get("catalog_status")!="confirmed":
        raise ScheduleRulesPending("기획서 6장의 콘텐츠 30종을 확정해야 정규 시즌 일정을 생성할 수 있습니다.")
    unconfirmed=("actual_match_times","per_agency_content_minimum","per_agency_content_maximum","same_opponent_consecutive_day_limit")
    if any(payload.get(key) is not None for key in unconfirmed):
        raise ScheduleRulesPending("실제 경기 시각·기획사별 콘텐츠 한도·연속 상대 제한은 미확정입니다. 임의 규칙을 적용하지 않습니다.")
    constants = {"agencies":10,"regular_weeks":24,"offseason_weeks":4,"meetings_per_pair":13,
                 "matches_per_agency":117,"regular_match_count":585,"doubleheader_days":3,
                 "content_count":30,"base_appearances":19,"extra_appearance_contents":15,
                 "late_content_name":"연말시상식","late_content_first_week":21,
                 "regular_weekdays":[2,3,4,5,6],"special_weeks":list(SPECIAL_WEEKS),
                 "special_types":list(SPECIAL_TYPES)}
    if any(payload.get(key)!=value for key,value in constants.items()):
        raise ScheduleError("일정 설정이 확정 기획서의 585경기·24주 규칙과 일치하지 않습니다.")
    contents=[]
    for item in payload.get("contents",[]):
        try:
            content = Content(item["id"],item["name"],tuple(item["main_abilities"]),
                              item["participants_min"],item["participants_max"])
        except (KeyError,TypeError) as error:
            raise ScheduleError("콘텐츠 설정에 이름·주요 능력치·출전 인원 범위가 필요합니다.") from error
        if (not isinstance(content.id,str) or not content.id.strip() or not isinstance(content.name,str)
            or not content.name.strip() or not content.main_abilities
            or any(not isinstance(a,str) or not a.strip() for a in content.main_abilities)
            or type(content.participants_min) is not int or type(content.participants_max) is not int
            or not 1<=content.participants_min<=content.participants_max<=5):
            raise ScheduleError("콘텐츠 주요 능력치 또는 1~5명 출전 범위가 잘못되었습니다.")
        contents.append(content)
    if (len(contents)!=30 or len({c.id for c in contents})!=30 or len({c.name for c in contents})!=30
        or sum(c.name=="연말시상식" for c in contents)!=1):
        raise ScheduleError("중복 없는 콘텐츠 30종과 연말시상식 항목이 필요합니다.")
    if not payload.get("source_reference") or not payload.get("rules_version"):
        raise ScheduleError("일정 설정의 기획서 출처와 규칙 버전을 명시해 주세요.")
    return ScheduleRules(tuple(contents),json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")))


def create_season_plan(season: int, agency_ids, rules: ScheduleRules,
                       rng: random.Random | None = None) -> SeasonPlan:
    agencies = tuple(sorted(agency_ids))
    if type(season) is not int or season<1 or len(agencies)!=10 or len(set(agencies))!=10:
        raise ScheduleError("시즌 번호와 중복 없는 기획사 10개가 필요합니다.")
    rng = rng or random.SystemRandom()
    rounds=[]
    for _ in range(13):
        rotation=list(agencies)
        rng.shuffle(rotation)
        for _ in range(9):
            pairs=list(zip(rotation[:5],reversed(rotation[5:])))
            rng.shuffle(pairs)
            rounds.append(tuple(pairs))
            rotation=[rotation[0],rotation[-1],*rotation[1:-1]]
    rng.shuffle(rounds)
    days=[(week,weekday) for week in range(1,25) for weekday in range(2,7)
          if not (weekday==6 and week in SPECIAL_WEEKS)]
    double_days=set(rng.sample(days,3))
    positions=[]
    round_index=0
    for week,weekday in days:
        for day_order in range(1,3 if (week,weekday) in double_days else 2):
            for pair in rounds[round_index]:
                positions.append((week,weekday,day_order,pair))
            round_index+=1
    extra={content.id for content in rng.sample(list(rules.contents),15)}
    targets={content.id:19+(content.id in extra) for content in rules.contents}
    late=next(content for content in rules.contents if content.name=="연말시상식")
    eligible=[index for index,item in enumerate(positions) if item[0]>=21]
    late_indices=set(rng.sample(eligible,targets[late.id]))
    other_contents=[content for content in rules.contents if content.id!=late.id
                    for _ in range(targets[content.id])]
    rng.shuffle(other_contents)
    other_iterator=iter(other_contents)
    namespace=uuid.UUID(int=rng.getrandbits(128))
    fixtures=[]
    for index,(week,weekday,day_order,pair) in enumerate(positions):
        content=late if index in late_indices else next(other_iterator)
        fixtures.append(RegularFixture(str(uuid.uuid5(namespace,f"{season}:regular:{index+1}")),season,
                                       week,weekday,day_order,index+1,pair,content))
    specials=tuple(SpecialFixture(str(uuid.uuid5(namespace,f"{season}:special:{week}")),season,week,
                                 rng.choice(SPECIAL_TYPES)) for week in SPECIAL_WEEKS)
    plan=SeasonPlan(season,rules,tuple(fixtures),specials)
    validate_season_plan(plan,agencies)
    return plan


def validate_season_plan(plan: SeasonPlan, agency_ids):
    agencies=set(agency_ids)
    if len(plan.regular)!=585 or len(plan.special)!=6:
        raise ScheduleError("정규 585경기와 특별전 6회 조건에 맞지 않습니다.")
    identities=[match.id for match in plan.regular]+[event.id for event in plan.special]
    if len(set(identities))!=591:
        raise ScheduleError("경기 고유 ID가 중복되었습니다.")
    catalog={content.id:content for content in plan.rules.contents}
    games=Counter()
    pairs=Counter()
    days=Counter()
    contents=Counter()
    slots={}
    for match in plan.regular:
        if (len(set(match.agencies))!=2 or not set(match.agencies)<=agencies or match.season!=plan.season
            or not 1<=match.week<=24 or not 2<=match.weekday<=6 or match.day_order not in (1,2)
            or (match.weekday==6 and match.week in SPECIAL_WEEKS)):
            raise ScheduleError("정규 대진의 참가 기획사 또는 날짜가 잘못되었습니다.")
        if catalog.get(match.content.id)!=match.content:
            raise ScheduleError("기획서 콘텐츠 목록에 없는 경기 콘텐츠입니다.")
        slot=(match.week,match.weekday,match.day_order)
        assigned=slots.setdefault(slot,set())
        if assigned.intersection(match.agencies):
            raise ScheduleError("같은 경기 순서에 기획사가 중복 참가합니다.")
        assigned.update(match.agencies)
        games.update(match.agencies)
        pairs[tuple(sorted(match.agencies))]+=1
        days[(match.week,match.weekday)]+=1
        contents[match.content.id]+=1
        if match.content.name=="연말시상식" and match.week<21:
            raise ScheduleError("연말시상식은 21~24주차에만 편성할 수 있습니다.")
    if (set(games)!=agencies or any(value!=117 for value in games.values()) or len(pairs)!=45
        or any(value!=13 for value in pairs.values()) or len(days)!=114
        or Counter(days.values())!={5:111,10:3} or any(value!=agencies for value in slots.values())
        or len(slots)!=117 or len(contents)!=30 or Counter(contents.values())!={19:15,20:15}
        or {m.match_order for m in plan.regular}!=set(range(1,586))):
        raise ScheduleError("대진·더블헤더·기획사별 경기 수 또는 콘텐츠 균등 배정 검증에 실패했습니다.")
    if {event.week for event in plan.special}!=set(SPECIAL_WEEKS) or any(event.event_type not in SPECIAL_TYPES or event.season!=plan.season for event in plan.special):
        raise ScheduleError("특별전 날짜 또는 종류가 잘못되었습니다.")
