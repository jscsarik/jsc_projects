"""Trusted one-time CA estimation and separate range-only public projections."""
from dataclasses import dataclass
import random
from .config import SKILLS

V9_STATEMENTS=(
    '''CREATE TABLE draft_estimates (
        person_id TEXT NOT NULL REFERENCES initial_draft_candidates(person_id) ON DELETE CASCADE,
        skill TEXT NOT NULL,low INTEGER NOT NULL CHECK(typeof(low)='integer' AND low BETWEEN 0 AND 96),
        high INTEGER NOT NULL CHECK(typeof(high)='integer' AND high=low+4),
        PRIMARY KEY(person_id,skill),
        FOREIGN KEY(person_id,skill) REFERENCES abilities(person_id,skill) ON DELETE CASCADE)''',
    '''CREATE TRIGGER immutable_draft_estimate BEFORE UPDATE ON draft_estimates
        BEGIN SELECT RAISE(ABORT,'Published draft estimates cannot be rewritten'); END''',
)


@dataclass(frozen=True)
class AbilityEstimate:
    low:int
    high:int

    @property
    def midpoint(self):return (self.low+self.high)/2
    def __str__(self):return f'{self.low}~{self.high}'


@dataclass(frozen=True)
class EstimatedCandidate:
    id:str
    name:str
    photo_path:str
    age:int
    estimates:tuple[AbilityEstimate,...]
    agency_id:str|None=None
    pick_number:int|None=None

    @property
    def estimated_overall(self):return round(sum(e.midpoint for e in self.estimates)/8,1)
    @property
    def status(self):return '지명 완료' if self.pick_number is not None else '지명 가능'


def estimate(value,rng):
    if type(value) is not int or not 0<=value<=100:raise ValueError('현재 능력치는 0~100 정수여야 합니다.')
    low=rng.randint(max(0,value-4),min(value,96))
    return AbilityEstimate(low,low+4)


def initialize_estimates(connection,*,rng=None):
    """Generation-only access to CA. Never reads PA, health or archetype.

    Called inside new-game/migration transactions, never from UI or AI reads.
    An independent RNG leaves existing attribute/draft random streams intact.
    """
    rng=rng or random.SystemRandom()
    rows=connection.execute('''SELECT a.person_id,a.skill,a.value FROM abilities a
        JOIN initial_draft_candidates d ON d.person_id=a.person_id
        LEFT JOIN draft_estimates e ON e.person_id=a.person_id AND e.skill=a.skill
        WHERE e.person_id IS NULL ORDER BY a.person_id,a.skill''').fetchall()
    for person,skill,value in rows:
        bounds=estimate(value,rng)
        connection.execute('INSERT INTO draft_estimates VALUES (?,?,?,?)',(person,skill,bounds.low,bounds.high))


def public_prospects(connection):
    """No abilities.value/PA/actual average can enter this payload or its query."""
    bounds={}
    for person,skill,low,high in connection.execute('SELECT person_id,skill,low,high FROM draft_estimates'):
        bounds.setdefault(person,{})[skill]=AbilityEstimate(low,high)
    rows=connection.execute('''SELECT p.id,p.name,p.photo_path,i.age,t.agency_id,k.pick_number
        FROM initial_draft_candidates d JOIN people p ON p.id=d.person_id JOIN idols i ON i.person_id=d.person_id
        LEFT JOIN draft_picks k ON k.person_id=d.person_id LEFT JOIN draft_turns t ON t.pick_number=k.pick_number
        ORDER BY p.name,p.id''')
    result=[]
    for r in rows:
        values=bounds.get(r['id'],{})
        if set(values)!=set(SKILLS):
            from .draft import DraftError
            raise DraftError('후보 추정 범위 저장이 불완전합니다. 백업과 저장 구조를 확인해 주세요. 실제 수치로 대체하지 않습니다.')
        result.append(EstimatedCandidate(r['id'],r['name'],r['photo_path'],r['age'],tuple(values[s] for s in SKILLS),r['agency_id'],r['pick_number']))
    return tuple(result)
