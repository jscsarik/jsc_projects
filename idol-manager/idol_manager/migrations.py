"""Versioned, transactional SQLite migration with a pre-upgrade backup."""
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sqlite3

from .agencies import AGENCY_SEEDS, INITIAL_FUNDS_KRW

from .match_schema import V6_STATEMENTS
from .condition_schema import V7_STATEMENTS
from .special_schema import V8_STATEMENTS
from .draft_estimates import V9_STATEMENTS,initialize_estimates

from .finals_schema import V10_STATEMENTS,migrate_calendar,leader_guards

from .development_schema import V11_STATEMENTS
from .finance_schema import V12_STATEMENTS
from .market_schema import V13_STATEMENTS,rebuild_contracts

from .awards import V14_STATEMENTS,V17_STATEMENTS
from .health_rules import V15_STATEMENTS
from .annual_schema import V16_STATEMENTS,initialize_annual
from .founding_schema import V18_STATEMENTS,V19_STATEMENTS
from .ai_trade_schema import V20_STATEMENTS
from .trade_policy import V21_STATEMENTS
from .training_service import V22_STATEMENTS
from .recruitment_philosophy import V23_STATEMENTS
from .coach_schema import V24_STATEMENTS,initialize_age_policy,initialize_coach
from .season32_schema import V25_STATEMENTS
SCHEMA_VERSION = 28

# Keep the original tables/columns intact: old save values are never regenerated.
V1_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS people (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE, photo_path TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS game (
        id INTEGER PRIMARY KEY CHECK(id = 1), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS idols (
        person_id TEXT PRIMARY KEY REFERENCES people(id),
        age INTEGER NOT NULL CHECK(age BETWEEN 0 AND 100),
        health INTEGER NOT NULL CHECK(health BETWEEN 0 AND 100), archetype TEXT NOT NULL,
        average REAL NOT NULL CHECK(average BETWEEN 0 AND 100),
        status TEXT NOT NULL CHECK(status IN ('candidate','unseen')))""",
    """CREATE TABLE IF NOT EXISTS abilities (
        person_id TEXT NOT NULL REFERENCES idols(person_id) ON DELETE CASCADE, skill TEXT NOT NULL,
        value INTEGER NOT NULL CHECK(value BETWEEN 0 AND 100),
        potential INTEGER NOT NULL CHECK(potential BETWEEN value AND 100), PRIMARY KEY(person_id, skill))""",
    "CREATE INDEX IF NOT EXISTS idx_idols_status ON idols(status)",
)

V2_STATEMENTS = (
    """CREATE TABLE agencies (
        id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, logo_path TEXT NOT NULL,
        funds_krw INTEGER NOT NULL DEFAULT 1000000000 CHECK(typeof(funds_krw)='integer' AND funds_krw >= 0))""",
    """CREATE TABLE roster_memberships (
        person_id TEXT PRIMARY KEY REFERENCES idols(person_id) ON DELETE CASCADE,
        agency_id TEXT REFERENCES agencies(id),
        career_status TEXT NOT NULL CHECK(career_status IN
            ('unassigned','first_team','second_team','fa','retired','trainee')),
        CHECK((career_status IN ('first_team','second_team','trainee') AND agency_id IS NOT NULL)
            OR (career_status IN ('unassigned','fa','retired') AND agency_id IS NULL)))""",
    "CREATE INDEX idx_roster_agency_status ON roster_memberships(agency_id, career_status)",
    """CREATE TABLE initial_draft_candidates (
        person_id TEXT PRIMARY KEY REFERENCES idols(person_id) ON DELETE CASCADE)""",
)

V3_STATEMENTS = (
    # SQLite cannot extend an existing CHECK constraint in place. Copy every
    # membership, then swap the table in the same transaction.
    """CREATE TABLE roster_memberships_v3 (
        person_id TEXT PRIMARY KEY REFERENCES idols(person_id) ON DELETE CASCADE,
        agency_id TEXT REFERENCES agencies(id),
        career_status TEXT NOT NULL CHECK(career_status IN
            ('unassigned','pro_pending','first_team','second_team','fa','retired','trainee')),
        CHECK((career_status IN ('pro_pending','first_team','second_team','trainee') AND agency_id IS NOT NULL)
            OR (career_status IN ('unassigned','fa','retired') AND agency_id IS NULL)))""",
    "INSERT INTO roster_memberships_v3 SELECT person_id,agency_id,career_status FROM roster_memberships",
    "DROP TABLE roster_memberships",
    "ALTER TABLE roster_memberships_v3 RENAME TO roster_memberships",
    "CREATE INDEX idx_roster_agency_status ON roster_memberships(agency_id,career_status)",
    """CREATE TABLE draft_state (
        id INTEGER PRIMARY KEY CHECK(id=1) REFERENCES game(id) ON DELETE CASCADE,
        status TEXT NOT NULL CHECK(status IN ('in_progress','completed')),
        started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE draft_turns (
        pick_number INTEGER PRIMARY KEY CHECK(pick_number BETWEEN 1 AND 160),
        draft_id INTEGER NOT NULL DEFAULT 1 REFERENCES draft_state(id) ON DELETE CASCADE CHECK(draft_id=1),
        round_number INTEGER NOT NULL CHECK(round_number BETWEEN 1 AND 16),
        position INTEGER NOT NULL CHECK(position BETWEEN 1 AND 10),
        agency_id TEXT NOT NULL REFERENCES agencies(id),
        CHECK(pick_number=(round_number-1)*10+position),
        UNIQUE(round_number,position), UNIQUE(round_number,agency_id))""",
    """CREATE TABLE draft_picks (
        pick_number INTEGER PRIMARY KEY REFERENCES draft_turns(pick_number) ON DELETE CASCADE,
        person_id TEXT NOT NULL UNIQUE REFERENCES initial_draft_candidates(person_id),
        picked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE draft_age_corrections (
        person_id TEXT PRIMARY KEY REFERENCES idols(person_id) ON DELETE CASCADE,
        old_age INTEGER NOT NULL CHECK(old_age=16), new_age INTEGER NOT NULL CHECK(new_age=17),
        approved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        backup_path TEXT NOT NULL)""",
    """CREATE TRIGGER draft_pick_guard BEFORE INSERT ON draft_picks BEGIN
        SELECT CASE WHEN COALESCE((SELECT status FROM draft_state WHERE id=1),'') != 'in_progress'
            THEN RAISE(ABORT,'Draft is not in progress') END;
        SELECT CASE WHEN NEW.pick_number != (SELECT COUNT(*)+1 FROM draft_picks)
            THEN RAISE(ABORT,'Draft picks must follow turn order') END;
        SELECT CASE WHEN NOT EXISTS (
            SELECT 1 FROM initial_draft_candidates d JOIN idols i ON i.person_id=d.person_id
            JOIN roster_memberships r ON r.person_id=d.person_id
            WHERE d.person_id=NEW.person_id AND i.age BETWEEN 17 AND 26 AND i.status='candidate'
                AND r.agency_id IS NULL AND r.career_status='unassigned')
            THEN RAISE(ABORT,'Person is not an eligible blind draft candidate') END;
    END""",
    """CREATE TRIGGER draft_pick_membership AFTER INSERT ON draft_picks BEGIN
        UPDATE roster_memberships SET career_status='pro_pending',
            agency_id=(SELECT agency_id FROM draft_turns WHERE pick_number=NEW.pick_number)
            WHERE person_id=NEW.person_id;
        UPDATE draft_state SET status='completed' WHERE id=1 AND (SELECT COUNT(*) FROM draft_picks)=160;
    END""",
    """CREATE VIEW initial_draft_undrafted AS
        SELECT d.person_id FROM initial_draft_candidates d
        JOIN draft_state s ON s.id=1 AND s.status='completed'
        LEFT JOIN draft_picks p ON p.person_id=d.person_id WHERE p.person_id IS NULL""",
)

# Additive UI extension: keep user_version=3 and preserve every existing row.
V3_PLAYER_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS player_settings (
        game_id INTEGER PRIMARY KEY CHECK(game_id=1) REFERENCES game(id) ON DELETE CASCADE,
        agency_id TEXT NOT NULL REFERENCES agencies(id),
        selected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TRIGGER IF NOT EXISTS player_agency_insert_guard BEFORE INSERT ON player_settings
        WHEN EXISTS(SELECT 1 FROM draft_state)
        BEGIN SELECT RAISE(ABORT,'Player agency is locked after draft start'); END""",
    """CREATE TRIGGER IF NOT EXISTS player_agency_update_guard BEFORE UPDATE ON player_settings
        WHEN NEW.agency_id IS NOT OLD.agency_id AND EXISTS(SELECT 1 FROM draft_state)
        BEGIN SELECT RAISE(ABORT,'Player agency is locked after draft start'); END""",
    """CREATE TRIGGER IF NOT EXISTS player_agency_delete_guard BEFORE DELETE ON player_settings
        WHEN EXISTS(SELECT 1 FROM draft_state)
        BEGIN SELECT RAISE(ABORT,'Player agency is locked after draft start'); END""",
)

V4_STATEMENTS = (
    """CREATE TABLE game_clock (
        game_id INTEGER PRIMARY KEY CHECK(game_id=1) REFERENCES game(id) ON DELETE CASCADE,
        management_date TEXT NOT NULL)""",
    """CREATE TABLE squad_formations (
        agency_id TEXT PRIMARY KEY REFERENCES agencies(id),
        game_id INTEGER NOT NULL DEFAULT 1 CHECK(game_id=1) REFERENCES game(id) ON DELETE CASCADE,
        revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>=1),
        initialized_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE professional_history (
        person_id TEXT PRIMARY KEY REFERENCES idols(person_id) ON DELETE CASCADE)""",
    """INSERT INTO professional_history SELECT person_id FROM roster_memberships
        WHERE career_status IN ('pro_pending','first_team','second_team','fa','retired')""",
    """CREATE TABLE squad_leaders (
        agency_id TEXT NOT NULL REFERENCES agencies(id),
        squad TEXT NOT NULL CHECK(squad IN ('first_team','second_team')),
        person_id TEXT NOT NULL UNIQUE REFERENCES roster_memberships(person_id) ON DELETE CASCADE,
        PRIMARY KEY(agency_id,squad))""",
    """CREATE TRIGGER professional_cannot_be_trainee BEFORE UPDATE ON roster_memberships
        WHEN NEW.career_status='trainee' AND (OLD.career_status IN
            ('pro_pending','first_team','second_team','fa','retired') OR
            EXISTS(SELECT 1 FROM professional_history WHERE person_id=NEW.person_id))
        BEGIN SELECT RAISE(ABORT,'A professional cannot return to the trainee squad'); END""",
    """CREATE TRIGGER professional_history_insert AFTER INSERT ON roster_memberships
        WHEN NEW.career_status IN ('pro_pending','first_team','second_team','fa','retired')
        BEGIN INSERT OR IGNORE INTO professional_history VALUES (NEW.person_id); END""",
    """CREATE TRIGGER professional_history_update AFTER UPDATE ON roster_memberships
        WHEN NEW.career_status IN ('pro_pending','first_team','second_team','fa','retired')
        BEGIN INSERT OR IGNORE INTO professional_history VALUES (NEW.person_id); END""",
    """CREATE TRIGGER squad_leader_insert_guard BEFORE INSERT ON squad_leaders BEGIN
        SELECT CASE WHEN COALESCE((SELECT strftime('%w',management_date) FROM game_clock WHERE game_id=1),'')!='1'
            THEN RAISE(ABORT,'Leaders can only be assigned on Monday') END;
        SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM roster_memberships WHERE person_id=NEW.person_id
            AND agency_id=NEW.agency_id AND career_status=NEW.squad)
            THEN RAISE(ABORT,'Leader must belong to the matching agency squad') END;
    END""",
    """CREATE TRIGGER squad_leader_update_guard BEFORE UPDATE ON squad_leaders BEGIN
        SELECT CASE WHEN COALESCE((SELECT strftime('%w',management_date) FROM game_clock WHERE game_id=1),'')!='1'
            THEN RAISE(ABORT,'Leaders can only be assigned on Monday') END;
        SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM roster_memberships WHERE person_id=NEW.person_id
            AND agency_id=NEW.agency_id AND career_status=NEW.squad)
            THEN RAISE(ABORT,'Leader must belong to the matching agency squad') END;
    END""",
    """CREATE TRIGGER clear_departed_squad_leader AFTER UPDATE OF agency_id,career_status ON roster_memberships
        BEGIN DELETE FROM squad_leaders WHERE person_id=NEW.person_id
            AND (agency_id IS NOT NEW.agency_id OR squad IS NOT NEW.career_status); END""",
)


V5_STATEMENTS = (
    "DROP TRIGGER squad_leader_insert_guard",
    "DROP TRIGGER squad_leader_update_guard",
    """CREATE TABLE legacy_game_clock (
        game_id INTEGER PRIMARY KEY REFERENCES game(id) ON DELETE CASCADE,
        legacy_management_date TEXT NOT NULL, mapped_absolute_day INTEGER NOT NULL)""",
    """CREATE TABLE game_clock_v5 (
        game_id INTEGER PRIMARY KEY CHECK(game_id=1) REFERENCES game(id) ON DELETE CASCADE,
        absolute_day INTEGER NOT NULL DEFAULT 0 CHECK(typeof(absolute_day)='integer' AND absolute_day>=0),
        revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>=1))""",
    """CREATE TABLE season_schedules (
        season INTEGER PRIMARY KEY CHECK(season>=1),
        game_id INTEGER NOT NULL DEFAULT 1 CHECK(game_id=1) REFERENCES game(id) ON DELETE CASCADE,
        rules_digest TEXT NOT NULL, rules_json TEXT NOT NULL,
        regular_count INTEGER NOT NULL CHECK(regular_count=585),
        special_count INTEGER NOT NULL CHECK(special_count=6),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE scheduled_matches (
        id TEXT PRIMARY KEY NOT NULL, season INTEGER NOT NULL REFERENCES season_schedules(season) ON DELETE CASCADE,
        week INTEGER NOT NULL CHECK(week BETWEEN 1 AND 24), weekday INTEGER NOT NULL CHECK(weekday BETWEEN 2 AND 6),
        day_order INTEGER NOT NULL CHECK(day_order IN (1,2)),
        match_order INTEGER NOT NULL CHECK(match_order BETWEEN 1 AND 585),
        content_id TEXT NOT NULL, content_name TEXT NOT NULL, main_abilities_json TEXT NOT NULL,
        participants_min INTEGER NOT NULL CHECK(participants_min>=1),
        participants_max INTEGER NOT NULL CHECK(participants_max>=participants_min),
        required_participants INTEGER CHECK(required_participants BETWEEN participants_min AND participants_max),
        match_type TEXT NOT NULL DEFAULT 'regular' CHECK(match_type='regular'),
        status TEXT NOT NULL DEFAULT 'scheduled' CHECK(status IN ('scheduled','in_progress','completed')),
        UNIQUE(season,match_order), UNIQUE(id,season,week,weekday,day_order))""",
    """CREATE TABLE match_participants (
        match_id TEXT NOT NULL, agency_id TEXT NOT NULL REFERENCES agencies(id),
        season INTEGER NOT NULL, week INTEGER NOT NULL, weekday INTEGER NOT NULL, day_order INTEGER NOT NULL,
        PRIMARY KEY(match_id,agency_id), UNIQUE(season,week,weekday,day_order,agency_id),
        FOREIGN KEY(match_id,season,week,weekday,day_order)
            REFERENCES scheduled_matches(id,season,week,weekday,day_order) ON DELETE CASCADE)""",
    """CREATE TABLE special_events (
        id TEXT PRIMARY KEY NOT NULL, season INTEGER NOT NULL REFERENCES season_schedules(season) ON DELETE CASCADE,
        week INTEGER NOT NULL CHECK(week IN (4,8,12,16,20,24)), weekday INTEGER NOT NULL DEFAULT 6 CHECK(weekday=6),
        event_type TEXT NOT NULL CHECK(event_type IN ('대학축제','K-POP 페스티벌','아이돌 체육대회')),
        status TEXT NOT NULL DEFAULT 'scheduled' CHECK(status IN ('scheduled','in_progress','completed')),
        UNIQUE(season,week))""",
    "CREATE INDEX idx_matches_day ON scheduled_matches(season,week,weekday,day_order)",
    """CREATE TRIGGER immutable_match_schedule BEFORE UPDATE OF season,week,weekday,day_order,match_order,
        content_id,content_name,main_abilities_json,participants_min,participants_max,match_type ON scheduled_matches
        BEGIN SELECT RAISE(ABORT,'Persisted season schedule cannot be rewritten'); END""",
    """CREATE TRIGGER immutable_required_participants BEFORE UPDATE OF required_participants ON scheduled_matches
        WHEN OLD.required_participants IS NOT NULL AND NEW.required_participants IS NOT OLD.required_participants
        BEGIN SELECT RAISE(ABORT,'Matchday participant count is already fixed'); END""",
    """CREATE TRIGGER immutable_special_schedule BEFORE UPDATE OF season,week,weekday,event_type ON special_events
        BEGIN SELECT RAISE(ABORT,'Persisted special event cannot be rewritten'); END""",
)


def _migrate_game_clock_v5(connection):
    old_rows = connection.execute("SELECT game_id,management_date FROM game_clock").fetchall()
    mapped = [(row[0],row[1],date.fromisoformat(row[1]).weekday()) for row in old_rows]
    connection.executemany("INSERT INTO legacy_game_clock VALUES (?,?,?)",mapped)
    connection.executemany("INSERT INTO game_clock_v5(game_id,absolute_day) VALUES (?,?)",[(r[0],r[2]) for r in mapped])
    connection.execute("INSERT OR IGNORE INTO game_clock_v5(game_id,absolute_day) SELECT id,0 FROM game")
    connection.execute("DROP TABLE game_clock")
    connection.execute("ALTER TABLE game_clock_v5 RENAME TO game_clock")
    for operation in ("INSERT","UPDATE"):
        connection.execute(f"""CREATE TRIGGER squad_leader_{operation.lower()}_guard BEFORE {operation} ON squad_leaders BEGIN
            SELECT CASE WHEN COALESCE((SELECT absolute_day%7 FROM game_clock WHERE game_id=1),-1)!=0
                THEN RAISE(ABORT,'Leaders can only be assigned on Monday') END;
            SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM roster_memberships WHERE person_id=NEW.person_id
                AND agency_id=NEW.agency_id AND career_status=NEW.squad)
                THEN RAISE(ABORT,'Leader must belong to the matching agency squad') END;
        END""")


def _capacity_trigger(operation: str) -> str:
    return f"""CREATE TRIGGER squad_capacity_{operation.lower()} BEFORE {operation} ON roster_memberships
        WHEN NEW.career_status IN ('pro_pending','first_team','second_team') BEGIN
        SELECT CASE WHEN (SELECT COUNT(*) FROM roster_memberships WHERE agency_id=NEW.agency_id
            AND person_id!=NEW.person_id AND career_status IN ('pro_pending','first_team','second_team'))>=16
            THEN RAISE(ABORT,'Professional squad capacity is 16') END;
        SELECT CASE WHEN NEW.career_status='first_team' AND (SELECT COUNT(*) FROM roster_memberships
            WHERE agency_id=NEW.agency_id AND person_id!=NEW.person_id AND career_status='first_team')>=5
            THEN RAISE(ABORT,'First team capacity is 5') END;
        SELECT CASE WHEN NEW.career_status='second_team' AND (SELECT COUNT(*) FROM roster_memberships
            WHERE agency_id=NEW.agency_id AND person_id!=NEW.person_id AND career_status='second_team')>=11
            THEN RAISE(ABORT,'Second team capacity is 11') END;
    END"""


def _has_player_extension(connection) -> bool:
    names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
    return {"player_settings", "player_agency_insert_guard", "player_agency_update_guard",
            "player_agency_delete_guard"} <= names


def initialize_rosters(connection):
    connection.execute("""INSERT OR IGNORE INTO roster_memberships(person_id, agency_id, career_status)
                          SELECT person_id, NULL, 'unassigned' FROM idols""")
    connection.execute("""INSERT OR IGNORE INTO initial_draft_candidates(person_id)
                          SELECT person_id FROM idols WHERE status='candidate'""")


def backup_database(path: Path, *, label: str | None = None) -> Path:
    folder = path.parent / "backups"
    folder.mkdir(exist_ok=True)
    stamp = datetime.now(timezone(timedelta(hours=9))).strftime("%Y%m%d_%H%M%S_%f_KST")
    target = folder / f"{path.stem}_before_{label or f'v{SCHEMA_VERSION}'}_{stamp}.sqlite3"
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(target)) as destination:
            source.backup(destination)
            if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("마이그레이션 전 DB 백업 무결성 검사에 실패했습니다.")
    return target


def migrate_database(path: Path) -> Path | None:
    backup = None
    with closing(sqlite3.connect(path, timeout=15)) as connection:
        from .game_clock import regular_day
        connection.create_function('regular_day',3,regular_day,deterministic=True)
        connection.execute("PRAGMA foreign_keys = ON")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError("이 프로그램보다 최신 버전의 저장 파일입니다. 최신 프로그램으로 열어 주세요.")
        if version == SCHEMA_VERSION and _has_player_extension(connection):
            if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='development_results_person_period'").fetchone():
                backup=backup_database(path,label='v17_development_index')
                connection.execute('BEGIN IMMEDIATE')
                connection.execute('CREATE INDEX IF NOT EXISTS development_results_person_period ON development_results(person_id,settlement_id)')
                connection.commit()
                return backup
            if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='market_contract_person_period'").fetchone():
                backup=backup_database(path,label='v13_market_index')
                connection.execute('BEGIN IMMEDIATE')
                connection.execute('CREATE INDEX IF NOT EXISTS market_contract_person_period ON finance_contracts(person_id,start_day,end_day)')
                connection.commit()
                return backup
            return None
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
            backup = backup_database(path)
        # Parent tables need constraint widening, with all dependent rows kept.
        # FK enforcement resumes on every normal connection; validate before commit.
        connection.execute('PRAGMA foreign_keys=OFF')
        try:
            connection.execute("BEGIN IMMEDIATE")
            # Another application instance may have completed migration while we waited.
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError("이 프로그램보다 최신 버전의 저장 파일입니다.")
            if version < 1:
                for statement in V1_STATEMENTS:
                    connection.execute(statement)
            if version < 2:
                for statement in V2_STATEMENTS:
                    connection.execute(statement)
                connection.executemany("INSERT INTO agencies VALUES (?,?,?,?)",
                                       [(*row, INITIAL_FUNDS_KRW) for row in AGENCY_SEEDS])
                initialize_rosters(connection)
            if version < 3:
                for statement in V3_STATEMENTS:
                    connection.execute(statement)
            for statement in V3_PLAYER_STATEMENTS:
                connection.execute(statement)
            if version < 4:
                for statement in V4_STATEMENTS:
                    connection.execute(statement)
                for operation in ("INSERT","UPDATE"):
                    connection.execute(_capacity_trigger(operation))
            if version < 5:
                for statement in V5_STATEMENTS:
                    connection.execute(statement)
                _migrate_game_clock_v5(connection)
            if version < 6:
                for statement in V6_STATEMENTS:
                    connection.execute(statement)
            if version < 7:
                for statement in V7_STATEMENTS:
                    connection.execute(statement)
                from .conditions import initialize_conditions
                initialize_conditions(connection,days_per_season=196)
            if version < 8:
                for statement in V8_STATEMENTS:
                    connection.execute(statement)
            if version < 9:
                for statement in V9_STATEMENTS:
                    connection.execute(statement)
                initialize_estimates(connection)
            if version < 10:
                for statement in V10_STATEMENTS:connection.execute(statement)
                migrate_calendar(connection)
                leader_guards(connection)
            if version < 11:
                for statement in V11_STATEMENTS:connection.execute(statement)
                from .development_service import initialize_development
                initialize_development(connection)
            if version < 12:
                for statement in V12_STATEMENTS:connection.execute(statement)
                from .finance_service import initialize_finance
                initialize_finance(connection)
            if version < 13:
                rebuild_contracts(connection)
                for statement in V13_STATEMENTS:connection.execute(statement)
                from .market_service import initialize_market
                initialize_market(connection)
            if version < 14:
                for statement in V14_STATEMENTS:connection.execute(statement)
                connection.execute('CREATE INDEX IF NOT EXISTS market_contract_person_period ON finance_contracts(person_id,start_day,end_day)')
            if version < 15:
                for statement in V15_STATEMENTS:connection.execute(statement)
            if version < 16:
                for statement in V16_STATEMENTS:connection.execute(statement)
                initialize_annual(connection)
            if version < 17:
                for statement in V17_STATEMENTS:connection.execute(statement)
                connection.execute('CREATE INDEX IF NOT EXISTS development_results_person_period ON development_results(person_id,settlement_id)')
            if version < 18:
                for statement in V18_STATEMENTS:connection.execute(statement)
                from .trainee_recruitment import initialize_rng
                initialize_rng(connection)
            if version < 19:
                for statement in V19_STATEMENTS:connection.execute(statement)
            if version < 20:
                for statement in V20_STATEMENTS:connection.execute(statement)
            if version < 21:
                for statement in V21_STATEMENTS:connection.execute(statement)
            if version < 22:
                for statement in V22_STATEMENTS:connection.execute(statement)
            if version < 23:
                for statement in V23_STATEMENTS:connection.execute(statement)
                from .recruitment_philosophy import ensure
                ensure(connection)
            if version < 24:
                for statement in V24_STATEMENTS:connection.execute(statement)
                initialize_age_policy(connection)
                initialize_coach(connection)
            if version < 25:
                for statement in V25_STATEMENTS:
                    if statement.startswith('ALTER TABLE annual_turns') and any(r[1]=='registration' for r in connection.execute('PRAGMA table_info(annual_turns)')):continue
                    connection.execute(statement)
                from .season32_schema import migrate as migrate_season32
                migrate_season32(connection)
            if version < 26:
                from .franchise import V26_STATEMENTS,restore
                for statement in V26_STATEMENTS:connection.execute(statement)
                restore(connection)
            if version < 27:
                from .squad_calendar import install_vacancy_guard
                install_vacancy_guard(connection)
            if version < 28:
                from .maintenance_conditions import V28_STATEMENTS,adopt
                for statement in V28_STATEMENTS:connection.execute(statement)
                adopt(connection)
            if connection.execute("PRAGMA foreign_key_check").fetchone():
                raise RuntimeError("마이그레이션 후 DB 참조 무결성 검사에 실패했습니다.")
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return backup
