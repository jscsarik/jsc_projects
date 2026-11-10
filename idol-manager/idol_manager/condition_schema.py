"""Additive version 7 schema, preserving all existing match results/events."""
V7_STATEMENTS=(
    'ALTER TABLE match_runs ADD COLUMN condition_json TEXT',
    '''CREATE TABLE condition_runtime (
        game_id INTEGER PRIMARY KEY REFERENCES game(id) ON DELETE CASCADE CHECK(game_id=1),
        rollout_day INTEGER NOT NULL CHECK(rollout_day>=0),seed TEXT NOT NULL)''',
    '''CREATE TABLE player_conditions (
        person_id TEXT PRIMARY KEY REFERENCES idols(person_id) ON DELETE CASCADE,
        last_appearance_day INTEGER,consecutive_days INTEGER NOT NULL DEFAULT 0 CHECK(consecutive_days>=0),
        registration_weeks INTEGER NOT NULL DEFAULT 0 CHECK(registration_weeks>=0),
        registration_week INTEGER NOT NULL DEFAULT -1,squad TEXT NOT NULL,squad_since INTEGER NOT NULL,
        complete_rest_weeks INTEGER NOT NULL DEFAULT 0 CHECK(complete_rest_weeks>=0),
        injured INTEGER NOT NULL DEFAULT 0 CHECK(injured IN(0,1)),injury_day INTEGER,recovery_day INTEGER,
        forced_down_day INTEGER,return_not_before INTEGER,history_known_since INTEGER NOT NULL)''',
    '''CREATE TABLE appearance_days (
        person_id TEXT NOT NULL REFERENCES idols(person_id) ON DELETE CASCADE,
        absolute_day INTEGER NOT NULL CHECK(absolute_day>=0),PRIMARY KEY(person_id,absolute_day))''',
    '''CREATE TABLE condition_events (
        event_key TEXT PRIMARY KEY,game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
        person_id TEXT NOT NULL REFERENCES idols(person_id) ON DELETE CASCADE,absolute_day INTEGER NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN('match','first_rest','second','recovery','roster')),
        probability REAL CHECK(probability BETWEEN 0 AND 1),roll REAL CHECK(roll>=0 AND roll<1),
        occurred INTEGER NOT NULL CHECK(occurred IN(0,1)),details_json TEXT NOT NULL)''',
    '''CREATE TABLE condition_day_runs (
        absolute_day INTEGER PRIMARY KEY CHECK(absolute_day>=0),
        game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
        seed TEXT NOT NULL,summary_json TEXT NOT NULL)''',
    'CREATE INDEX idx_condition_events_day ON condition_events(absolute_day,kind)',
)

CONDITION_TABLES=('condition_events','appearance_days','player_conditions','condition_day_runs','condition_runtime')
