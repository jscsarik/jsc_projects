from contextlib import closing
from pathlib import Path
import random
import sqlite3

from .config import SKILLS
from .agencies import Agency, INITIAL_FUNDS_KRW
from .domain import Person, PublicIdol, generate_attributes
from .migrations import initialize_rosters, migrate_database
from .game_clock import initialize_game_clock


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.last_backup_path = migrate_database(path)

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        from .game_clock import regular_day
        connection.create_function('regular_day',3,regular_day,deterministic=True)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _upsert_people(connection, people: tuple[Person, ...]):
        # Annual photo identities are persistent UUIDs. A scanner's legacy
        # name-derived ID must never replace an already registered identity.
        canonical=[]
        has_assets=connection.execute("SELECT 1 FROM sqlite_master WHERE name='annual_assets'").fetchone()
        for person in people:
            asset=connection.execute('SELECT person_id FROM annual_assets WHERE photo_path=?',(person.photo_path,)).fetchone() if has_assets else None
            if asset:
                row=connection.execute('SELECT id,name,name_key,photo_path FROM people WHERE id=?',(asset[0],)).fetchone()
                canonical.append(Person(*row));continue
            connection.execute('''INSERT INTO people(id,name,name_key,photo_path) VALUES (?,?,?,?)
                ON CONFLICT(name_key) DO UPDATE SET name=excluded.name,photo_path=excluded.photo_path''',
                (person.id,person.name,person.name_key,person.photo_path))
            row=connection.execute('SELECT id,name,name_key,photo_path FROM people WHERE name_key=?',(person.name_key,)).fetchone()
            canonical.append(Person(*row))
        return tuple({p.id:p for p in canonical}.values())

    def register(self, people: tuple[Person, ...]):
        with closing(self.connect()) as connection, connection:
            self._upsert_people(connection, people)

    def has_game(self) -> bool:
        with closing(self.connect()) as connection:
            return connection.execute("SELECT 1 FROM game WHERE id=1").fetchone() is not None

    def create_game(self, people: tuple[Person, ...], settings: dict, rng: random.Random | None = None,*,founding_protocol=2):
        if not people:
            raise ValueError("등록할 사진이 없습니다. assets/idols 폴더에 사진을 넣어 주세요.")
        rng = rng or random.Random()
        # One transaction: failures preserve the previous game in its entirety.
        with closing(self.connect()) as connection, connection:
            people=self._upsert_people(connection, people)
            candidates = {p.id for p in rng.sample(list(people), min(settings["initial_candidates"], len(people)))}
            # Remove the explicitly replaced game's draft before its candidate
            # rows, respecting pick/candidate references. Failure rolls it back.
            connection.execute("DELETE FROM draft_state")
            connection.execute("DELETE FROM idols")
            connection.execute("DELETE FROM game")
            connection.execute("UPDATE agencies SET funds_krw=?", (INITIAL_FUNDS_KRW,))
            for person in people:
                attributes = generate_attributes(rng, settings, age_context="initial_draft")
                connection.execute("INSERT INTO idols VALUES (?, ?, ?, ?, ?, ?)", (
                    person.id, attributes["age"], attributes["health"], attributes["archetype"],
                    attributes["average"], "candidate" if person.id in candidates else "unseen",
                ))
                connection.executemany("INSERT INTO abilities VALUES (?, ?, ?, ?)", [
                    (person.id, skill, attributes["skills"][skill], attributes["potentials"][skill])
                    for skill in SKILLS
                ])
            connection.execute("INSERT INTO game(id) VALUES (1)")
            connection.execute("INSERT INTO founding_setup(game_id,status,protocol) VALUES (1,'pending',?)",(founding_protocol,))
            from .trainee_recruitment import initialize_rng
            initialize_rng(connection,rng.getrandbits(256))
            initialize_game_clock(connection)
            initialize_rosters(connection)
            from .conditions import initialize_conditions
            initialize_conditions(connection)
            from .draft_estimates import initialize_estimates
            initialize_estimates(connection)
            from .development_service import initialize_development
            initialize_development(connection)
            from .coach_schema import initialize_age_policy,initialize_coach
            initialize_age_policy(connection)
            initialize_coach(connection)
            from .finance_service import initialize_finance
            initialize_finance(connection,new_game=True)
            from .market_service import initialize_market
            initialize_market(connection)
            from .annual_schema import initialize_annual
            initialize_annual(connection)

    def public_roster(self) -> list[PublicIdol]:
        return self.initial_draft_candidates()

    def initial_draft_candidates(self) -> list[PublicIdol]:
        with closing(self.connect()) as connection:
            rows = connection.execute("""
                SELECT p.id, p.name, p.photo_path, i.age, i.status
                FROM idols i JOIN people p ON p.id=i.person_id
                JOIN initial_draft_candidates d ON d.person_id=i.person_id
                JOIN roster_memberships r ON r.person_id=i.person_id
                WHERE i.status='candidate' AND r.career_status='unassigned' AND r.agency_id IS NULL
                ORDER BY p.name COLLATE NOCASE
            """).fetchall()
        return [PublicIdol(**dict(row)) for row in rows]

    def agencies(self) -> list[Agency]:
        with closing(self.connect()) as connection:
            rows = connection.execute("SELECT id,name,logo_path,funds_krw FROM agencies ORDER BY name").fetchall()
        return [Agency(**dict(row)) for row in rows]

    def agency_roster(self, agency_id: str) -> list[PublicIdol]:
        with closing(self.connect()) as connection:
            if connection.execute("SELECT 1 FROM agencies WHERE id=?", (agency_id,)).fetchone() is None:
                raise ValueError("존재하지 않는 기획사입니다.")
            rows = connection.execute("""
                SELECT p.id,p.name,p.photo_path,i.age,r.career_status AS status
                FROM roster_memberships r JOIN idols i ON i.person_id=r.person_id
                JOIN people p ON p.id=i.person_id
                WHERE r.agency_id=? AND r.career_status IN ('pro_pending','first_team','second_team','trainee')
                ORDER BY p.name COLLATE NOCASE
            """, (agency_id,)).fetchall()
        return [PublicIdol(**dict(row)) for row in rows]

    def counts(self) -> tuple[int, int]:
        with closing(self.connect()) as connection:
            row = connection.execute("SELECT COUNT(*), COALESCE(SUM(status='candidate'),0) FROM idols").fetchone()
        return row[0], row[1]
