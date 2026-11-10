"""Persistent blind initial draft. Human and future AI callers use pick()."""
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import random
import sqlite3

from .migrations import backup_database

ROUNDS = 16
AGENCY_COUNT = 10
POOL_SIZE = 200
TOTAL_PICKS = ROUNDS * AGENCY_COUNT


class DraftError(ValueError):
    """A rejected operation leaves all draft and game data unchanged."""


class AgeApprovalRequired(DraftError):
    pass


@dataclass(frozen=True)
class BlindCandidate:
    id: str
    name: str
    photo_path: str
    age: int


@dataclass(frozen=True)
class DraftTurn:
    pick_number: int
    round_number: int
    position: int
    agency_id: str


@dataclass(frozen=True)
class DraftPick:
    pick_number: int
    round_number: int
    position: int
    agency_id: str
    person_id: str


@dataclass(frozen=True)
class DraftState:
    status: str
    picks_made: int
    total_picks: int
    next_turn: DraftTurn | None


@dataclass(frozen=True)
class AgeCorrectionResult:
    corrected_ids: tuple[str, ...]
    backup_path: Path


def _turn(row) -> DraftTurn:
    return DraftTurn(row["pick_number"], row["round_number"], row["position"], row["agency_id"])


class DraftEngine:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def _state(connection) -> DraftState:
        row = connection.execute("SELECT status FROM draft_state WHERE id=1").fetchone()
        if row is None:
            return DraftState("not_started", 0, TOTAL_PICKS, None)
        count = connection.execute("SELECT COUNT(*) FROM draft_picks").fetchone()[0]
        next_row = connection.execute("SELECT * FROM draft_turns WHERE pick_number=?", (count + 1,)).fetchone()
        return DraftState(row["status"], count, TOTAL_PICKS, _turn(next_row) if next_row else None)

    def state(self) -> DraftState:
        with closing(self.database.connect()) as connection, connection:
            connection.execute("BEGIN")
            return self._state(connection)

    @staticmethod
    def _age_issues(connection) -> list[BlindCandidate]:
        rows = connection.execute("""
            SELECT p.id,p.name,p.photo_path,i.age FROM initial_draft_candidates d
            JOIN idols i ON i.person_id=d.person_id JOIN people p ON p.id=d.person_id
            WHERE i.age NOT BETWEEN 17 AND 26 ORDER BY p.name
        """).fetchall()
        return [BlindCandidate(**dict(row)) for row in rows]

    def age_issues(self) -> list[BlindCandidate]:
        with closing(self.database.connect()) as connection:
            return self._age_issues(connection)

    def correct_legacy_ages(self, *, approved: bool = False,
                            person_ids: tuple[str, ...] = ()) -> AgeCorrectionResult:
        """Only an explicitly approved, enumerated set of age-16 candidates.

        This method is never called by migration, startup, or start(). The caller
        must obtain human consent before supplying approved=True and these IDs.
        """
        if approved is not True:
            raise AgeApprovalRequired("16세 후보의 나이 변경에는 사용자의 명시적인 승인이 필요합니다.")
        if isinstance(person_ids, str) or not person_ids or len(set(person_ids)) != len(person_ids):
            raise DraftError("승인한 후보 ID를 중복 없이 명시해 주세요.")
        with closing(self.database.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM draft_state").fetchone():
                raise DraftError("드래프트 시작 후에는 최초 후보 나이 보정을 실행할 수 없습니다.")
            eligible = {p.id for p in self._age_issues(connection) if p.age == 16}
            if not set(person_ids) <= eligible:
                raise DraftError("승인 목록에 현재 16세인 최초 후보가 아닌 인물이 있습니다. 다시 확인해 주세요.")
            # A RESERVED write lock prevents changes between backup and updates;
            # the independent read-only backup connection sees the committed save.
            backup = backup_database(self.database.path, label="age16_to17")
            for person_id in person_ids:
                connection.execute("UPDATE idols SET age=17 WHERE person_id=? AND age=16", (person_id,))
                connection.execute("""INSERT INTO draft_age_corrections(person_id,old_age,new_age,backup_path)
                                      VALUES (?,16,17,?)""", (person_id, str(backup)))
            return AgeCorrectionResult(tuple(person_ids), backup)

    @staticmethod
    def _available(connection) -> list[BlindCandidate]:
        rows = connection.execute("""
            SELECT p.id,p.name,p.photo_path,i.age FROM initial_draft_candidates d
            JOIN idols i ON i.person_id=d.person_id JOIN people p ON p.id=d.person_id
            JOIN roster_memberships r ON r.person_id=d.person_id
            LEFT JOIN draft_picks k ON k.person_id=d.person_id
            WHERE k.person_id IS NULL AND i.status='candidate'
                AND r.career_status='unassigned' AND r.agency_id IS NULL
            ORDER BY p.name,p.id
        """).fetchall()
        return [BlindCandidate(**dict(row)) for row in rows]

    def available_candidates(self) -> list[BlindCandidate]:
        """The entire candidate payload available to either human or AI."""
        with closing(self.database.connect()) as connection:
            return self._available(connection)

    def start(self, *, rng: random.Random | None = None) -> DraftState:
        """Start once, or return the persisted state without reshuffling."""
        with closing(self.database.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            state = self._state(connection)
            if state.status != "not_started":
                return state
            if not connection.execute("SELECT 1 FROM game WHERE id=1").fetchone():
                raise DraftError("새 게임이 없어 드래프트를 시작할 수 없습니다.")
            issues = self._age_issues(connection)
            if issues:
                age_16 = sum(p.age == 16 for p in issues)
                raise DraftError(
                    f"후보 {len(issues)}명의 나이가 최초 드래프트 규칙(17~26세)을 벗어납니다. "
                    f"그중 16세는 {age_16}명입니다. 명시적 승인 후 나이 보정이 필요하며, 승인 전에는 기존 값을 유지합니다."
                )
            agencies = [row[0] for row in connection.execute("SELECT id FROM agencies ORDER BY id")]
            pool_count = connection.execute("SELECT COUNT(*) FROM initial_draft_candidates").fetchone()[0]
            if len(agencies) != AGENCY_COUNT or pool_count != POOL_SIZE or len(self._available(connection)) != POOL_SIZE:
                raise DraftError("최초 드래프트에는 기획사 10개와 미배정 후보 정확히 200명이 필요합니다.")
            if connection.execute("SELECT 1 FROM roster_memberships WHERE agency_id IS NOT NULL OR career_status!='unassigned' LIMIT 1").fetchone():
                raise DraftError("기존 소속 또는 경력 상태가 있어 초기 16명 편성을 보장할 수 없습니다.")
            (rng or random.Random()).shuffle(agencies)
            connection.execute("INSERT INTO draft_state(id,status) VALUES (1,'in_progress')")
            turns = []
            for round_number in range(1, ROUNDS + 1):
                order = agencies if round_number % 2 else list(reversed(agencies))
                for position, agency_id in enumerate(order, 1):
                    turns.append(((round_number - 1) * AGENCY_COUNT + position, round_number, position, agency_id))
            connection.executemany("""INSERT INTO draft_turns(pick_number,round_number,position,agency_id)
                                      VALUES (?,?,?,?)""", turns)
            return self._state(connection)

    def turn_order(self) -> list[DraftTurn]:
        with closing(self.database.connect()) as connection:
            return [_turn(row) for row in connection.execute("SELECT * FROM draft_turns ORDER BY pick_number")]

    def picks(self) -> list[DraftPick]:
        with closing(self.database.connect()) as connection:
            rows = connection.execute("""
                SELECT t.pick_number,t.round_number,t.position,t.agency_id,p.person_id
                FROM draft_picks p JOIN draft_turns t ON t.pick_number=p.pick_number ORDER BY p.pick_number
            """).fetchall()
            return [DraftPick(**dict(row)) for row in rows]

    @staticmethod
    def _check_memberships(connection):
        if connection.execute("""
            SELECT 1 FROM draft_picks p JOIN draft_turns t ON t.pick_number=p.pick_number
            LEFT JOIN roster_memberships r ON r.person_id=p.person_id
            WHERE r.person_id IS NULL OR r.agency_id IS NOT t.agency_id OR r.career_status!='pro_pending'
            LIMIT 1
        """).fetchone():
            raise DraftError("지명 결과와 임시 프로 소속이 일치하지 않습니다. 저장 데이터를 확인해 주세요.")

    def pick(self, agency_id: str, person_id: str, *, expected_pick_number: int) -> DraftPick:
        """Shared human/AI command. Turn number also rejects stale/replayed input.

        No evaluator or AI policy receives Database/abilities via this interface.
        Only candidate identity, public information, and turn state are needed.
        """
        if type(expected_pick_number) is not int:
            raise DraftError("현재 전체 지명 번호를 정수로 명시해 주세요.")
        try:
            with closing(self.database.connect()) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                state = self._state(connection)
                if state.status != "in_progress" or state.next_turn is None:
                    raise DraftError("드래프트가 진행 중이 아닙니다.")
                turn = state.next_turn
                if expected_pick_number != turn.pick_number:
                    raise DraftError(f"지명 순서가 변경됐거나 오래된 요청입니다. 현재 전체 {turn.pick_number}번 지명입니다.")
                if agency_id != turn.agency_id:
                    raise DraftError(f"현재는 {turn.agency_id} 기획사의 지명 차례입니다.")
                self._check_memberships(connection)
                # Selecting by ID never accesses abilities, average, health, or potential.
                if connection.execute("SELECT 1 FROM draft_picks WHERE person_id=?", (person_id,)).fetchone():
                    raise DraftError("이미 지명된 아이돌입니다.")
                if not any(person.id == person_id for person in self._available(connection)):
                    raise DraftError("지명 가능한 최초 후보가 아닙니다.")
                connection.execute("INSERT INTO draft_picks(pick_number,person_id) VALUES (?,?)", (turn.pick_number, person_id))
                # SQLite triggers atomically set pro_pending membership and the completion flag.
                self._check_memberships(connection)
                if turn.pick_number == TOTAL_PICKS:
                    counts = connection.execute("""
                        SELECT a.id,COUNT(r.person_id) FROM agencies a LEFT JOIN roster_memberships r
                        ON r.agency_id=a.id GROUP BY a.id
                    """).fetchall()
                    if len(counts) != AGENCY_COUNT or any(row[1] != ROUNDS for row in counts) or len(self._available(connection)) != 40:
                        raise DraftError("드래프트 완료 인원 검증에 실패했습니다. 마지막 지명은 저장하지 않았습니다.")
                    from .founding import start
                    start(connection)
                return DraftPick(turn.pick_number, turn.round_number, turn.position, agency_id, person_id)
        except sqlite3.IntegrityError as error:
            raise DraftError("지명 저장 제약을 위반했습니다. 후보 나이·중복·순서를 다시 확인해 주세요.") from error

    def undrafted_candidates(self) -> list[BlindCandidate]:
        """Only the final 40, for a later FA system; does not convert anyone to FA."""
        with closing(self.database.connect()) as connection, connection:
            connection.execute("BEGIN")
            if self._state(connection).status != "completed":
                raise DraftError("미지명 40명은 드래프트 완료 후에 확정됩니다.")
            rows = connection.execute("""
                SELECT p.id,p.name,p.photo_path,i.age FROM initial_draft_undrafted u
                JOIN people p ON p.id=u.person_id JOIN idols i ON i.person_id=u.person_id ORDER BY p.name,p.id
            """).fetchall()
            return [BlindCandidate(**dict(row)) for row in rows]
