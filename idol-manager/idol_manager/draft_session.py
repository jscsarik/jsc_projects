"""UI-facing draft coordinator. All picks still go through DraftEngine.pick()."""
from contextlib import closing
from dataclasses import dataclass
import sqlite3

from .agencies import Agency
from .ai_policy import BlindDraftPolicy
from .draft_estimates import EstimatedCandidate,public_prospects
from .config import SKILLS
from .draft import BlindCandidate, DraftEngine, DraftError, DraftPick, DraftState, DraftTurn


@dataclass(frozen=True)
class PublicDraftPick:
    pick_number: int
    round_number: int
    agency_id: str
    person_id: str
    name: str
    age: int
    photo_path: str


@dataclass(frozen=True)
class DraftSnapshot:
    state: DraftState
    player_agency_id: str | None
    agencies: tuple[Agency, ...]
    candidates: tuple[EstimatedCandidate, ...]
    order: tuple[DraftTurn, ...]
    history: tuple[PublicDraftPick, ...]
    prospects: tuple[EstimatedCandidate, ...]


class DraftSession:
    def __init__(self, engine: DraftEngine, policy: BlindDraftPolicy | None = None):
        self.engine = engine
        self.database = engine.database
        self.policy = policy

    @staticmethod
    def _player(connection) -> str | None:
        row = connection.execute("SELECT agency_id FROM player_settings WHERE game_id=1").fetchone()
        return row[0] if row else None

    def player_agency(self) -> str | None:
        with closing(self.database.connect()) as connection:
            return self._player(connection)

    def select_agency(self, agency_id: str):
        try:
            with closing(self.database.connect()) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                if not connection.execute("SELECT 1 FROM game WHERE id=1").fetchone():
                    raise DraftError("먼저 새 게임을 생성해 주세요.")
                if not connection.execute("SELECT 1 FROM agencies WHERE id=?", (agency_id,)).fetchone():
                    raise DraftError("선택한 기획사를 찾을 수 없습니다.")
                if self._player(connection) == agency_id:
                    from .recruitment_philosophy import ensure
                    ensure(connection)
                    return
                if connection.execute("SELECT 1 FROM draft_state").fetchone():
                    raise DraftError("드래프트 시작 후에는 플레이어 기획사를 변경할 수 없습니다.")
                connection.execute("""INSERT INTO player_settings(game_id,agency_id) VALUES (1,?)
                    ON CONFLICT(game_id) DO UPDATE SET agency_id=excluded.agency_id,selected_at=CURRENT_TIMESTAMP""", (agency_id,))
                from .recruitment_philosophy import ensure
                ensure(connection)
        except sqlite3.IntegrityError as error:
            raise DraftError("플레이어 기획사 선택을 저장할 수 없습니다. 현재 드래프트 상태를 확인해 주세요.") from error

    def snapshot(self) -> DraftSnapshot:
        # Read every displayed field in one consistent snapshot, with explicit
        # public projections. No abilities/potential/health/market-value queries.
        with closing(self.database.connect()) as connection, connection:
            connection.execute("BEGIN")
            state = self.engine._state(connection)
            agencies = tuple(Agency(**dict(row)) for row in connection.execute(
                "SELECT id,name,logo_path,funds_krw FROM agencies ORDER BY name"))
            order = tuple(DraftTurn(row[0],row[1],row[2],row[3]) for row in connection.execute(
                "SELECT pick_number,round_number,position,agency_id FROM draft_turns ORDER BY pick_number"))
            history = tuple(PublicDraftPick(**dict(row)) for row in connection.execute("""
                SELECT t.pick_number,t.round_number,t.agency_id,k.person_id,p.name,i.age,p.photo_path
                FROM draft_picks k JOIN draft_turns t ON t.pick_number=k.pick_number
                JOIN people p ON p.id=k.person_id JOIN idols i ON i.person_id=k.person_id
                ORDER BY t.pick_number
            """))
            prospects=public_prospects(connection)
            available={p.id for p in self.engine._available(connection)}
            return DraftSnapshot(state,self._player(connection),agencies,
                                 tuple(p for p in prospects if p.id in available),order,history,prospects)

    def revealed_player(self,person_id):
        """Owner-only exact CA projection after a committed pick; PA is never queried."""
        with closing(self.database.connect()) as c,c:
            c.execute('BEGIN');player=self._player(c)
            row=c.execute('''SELECT p.id,p.name,p.photo_path,i.age FROM draft_picks k
                JOIN draft_turns t ON t.pick_number=k.pick_number JOIN people p ON p.id=k.person_id
                JOIN idols i ON i.person_id=p.id JOIN roster_memberships r ON r.person_id=p.id
                WHERE k.person_id=? AND t.agency_id=? AND r.agency_id=?''',(person_id,player,player)).fetchone()
            if row is None:raise DraftError('운영 기획사가 지명한 선수의 현재 능력치만 확인할 수 있습니다.')
            values=dict(c.execute('SELECT skill,value FROM abilities WHERE person_id=?',(person_id,)))
            if set(values)!=set(SKILLS):raise DraftError('현재 능력치 기록이 불완전합니다.')
            return dict(row),tuple(values[s] for s in SKILLS),round(sum(values.values())/8,1)

    def start(self):
        if self.player_agency() is None:
            raise DraftError("운영할 기획사를 먼저 선택해 저장해 주세요.")
        return self.engine.start()

    def pick_player(self, person_id: str, *, expected_pick_number: int) -> DraftPick:
        player = self.player_agency()
        if player is None:
            raise DraftError("저장된 플레이어 기획사가 없습니다.")
        return self.engine.pick(player,person_id,expected_pick_number=expected_pick_number)

    def pick_ai_turn(self) -> DraftPick | None:
        snapshot = self.snapshot()
        if snapshot.player_agency_id is None:
            raise DraftError("플레이어 기획사를 먼저 선택해 주세요.")
        turn = snapshot.state.next_turn
        if snapshot.state.status != "in_progress" or turn is None or turn.agency_id == snapshot.player_agency_id:
            return None
        if self.policy is not None:
            identity=self.policy.choose(snapshot.candidates)
        else:
            from .recruitment_philosophy import ensure
            from .recruitment_policy import decide,public_view
            from .market_service import public_people
            with closing(self.database.connect()) as c,c:
                c.execute('BEGIN IMMEDIATE')
                philosophy=ensure(c)[turn.agency_id]
                own=[public_view(p) for p in public_people(c,agency=turn.agency_id)]
            candidates=[dict(id=p.id,age=p.age,skills=[e.midpoint for e in p.estimates]) for p in snapshot.candidates]
            identity=decide(candidates,own,philosophy,context='founding',round_number=turn.round_number)[0]['id']
        return self.engine.pick(turn.agency_id,identity,expected_pick_number=turn.pick_number)

    def validate_completion(self):
        with closing(self.database.connect()) as connection, connection:
            connection.execute("BEGIN")
            if self.engine._state(connection).status != "completed":
                raise DraftError("드래프트가 아직 완료되지 않았습니다.")
            # Completion validates immutable picks, not the current market roster.
            counts = connection.execute("""SELECT a.id,COUNT(p.person_id) FROM agencies a
                LEFT JOIN draft_turns t ON t.agency_id=a.id
                LEFT JOIN draft_picks p ON p.pick_number=t.pick_number GROUP BY a.id""").fetchall()
            remaining = connection.execute("SELECT COUNT(*) FROM initial_draft_undrafted").fetchone()[0]
            if len(counts) != 10 or any(row[1] != 16 for row in counts) or remaining != 40:
                raise DraftError("완료 인원 검증에 실패했습니다. 저장 데이터를 확인해 주세요.")
