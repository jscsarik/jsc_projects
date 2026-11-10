"""V16: annual intake/turn journals; existing founding draft stays untouched."""
V16_STATEMENTS=(
    'DROP TRIGGER immutable_draft_estimate',
    '''CREATE TABLE annual_estimates_upgrade(person_id TEXT NOT NULL REFERENCES idols(person_id) ON DELETE CASCADE,
        skill TEXT NOT NULL,low INTEGER NOT NULL CHECK(typeof(low)='integer' AND low BETWEEN 0 AND 96),
        high INTEGER NOT NULL CHECK(typeof(high)='integer' AND high=low+4),PRIMARY KEY(person_id,skill),
        FOREIGN KEY(person_id,skill) REFERENCES abilities(person_id,skill) ON DELETE CASCADE)''',
    'INSERT INTO annual_estimates_upgrade SELECT * FROM draft_estimates',
    'DROP TABLE draft_estimates',
    'ALTER TABLE annual_estimates_upgrade RENAME TO draft_estimates',
    '''CREATE TRIGGER immutable_draft_estimate BEFORE UPDATE ON draft_estimates
       BEGIN SELECT RAISE(ABORT,'Published draft estimates cannot be rewritten'); END''',
    '''CREATE TABLE annual_assets(photo_path TEXT PRIMARY KEY,person_id TEXT NOT NULL REFERENCES people(id),
       digest TEXT NOT NULL,file_size INTEGER NOT NULL,modified_ns INTEGER NOT NULL)''',
    'CREATE INDEX annual_assets_digest ON annual_assets(digest)',
    '''CREATE TABLE annual_runtime(game_id INTEGER PRIMARY KEY REFERENCES game(id) ON DELETE CASCADE,
       first_season INTEGER NOT NULL,rollout_day INTEGER NOT NULL)''',
    '''CREATE TABLE annual_intakes(season INTEGER PRIMARY KEY,game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
       status TEXT NOT NULL CHECK(status IN('shortage','completed')),seed TEXT NOT NULL,available INTEGER NOT NULL,
       appeared_day INTEGER,issue TEXT NOT NULL DEFAULT '')''',
    '''CREATE TABLE annual_entries(person_id TEXT PRIMARY KEY REFERENCES people(id),
       intake_season INTEGER NOT NULL REFERENCES annual_intakes(season) ON DELETE CASCADE,
       first_season INTEGER NOT NULL,appeared_day INTEGER NOT NULL,initial_age INTEGER NOT NULL)''',
    '''CREATE TABLE annual_secrets(person_id TEXT PRIMARY KEY REFERENCES annual_entries(person_id) ON DELETE CASCADE,
       special INTEGER NOT NULL CHECK(special=1))''',
    '''CREATE TABLE annual_sessions(season INTEGER PRIMARY KEY,game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
       target_season INTEGER NOT NULL,status TEXT NOT NULL CHECK(status IN('in_progress','completed')),
       order_json TEXT NOT NULL,started_day INTEGER NOT NULL,completed_day INTEGER)''',
    '''CREATE TABLE annual_turns(season INTEGER NOT NULL REFERENCES annual_sessions(season) ON DELETE CASCADE,
       pick_number INTEGER NOT NULL CHECK(pick_number BETWEEN 1 AND 30),round_number INTEGER NOT NULL CHECK(round_number BETWEEN 1 AND 3),
       agency_id TEXT NOT NULL REFERENCES agencies(id),pick_id TEXT NOT NULL UNIQUE,
       person_id TEXT REFERENCES people(id),prior_role TEXT,status TEXT NOT NULL DEFAULT 'scheduled'
       CHECK(status IN('scheduled','negotiating','signed','failed')),negotiation_id TEXT REFERENCES market_negotiations(id) ON DELETE SET NULL,
       picked_day INTEGER,completed_day INTEGER,was_public INTEGER,picked_age INTEGER,contract_kind TEXT,
       PRIMARY KEY(season,pick_number),UNIQUE(season,person_id),
       UNIQUE(season,round_number,agency_id))''',
    '''CREATE TABLE annual_pool(season INTEGER NOT NULL REFERENCES annual_sessions(season) ON DELETE CASCADE,
       person_id TEXT NOT NULL REFERENCES people(id),PRIMARY KEY(season,person_id))''',
)


def initialize_annual(c):
    from .game_clock import current_game_date
    day=current_game_date(c)
    if day is None or c.execute('SELECT 1 FROM annual_runtime').fetchone():return
    # A late legacy rollout must not rewind an existing FA market or picks.
    legacy=c.execute('SELECT 1 FROM market_draft_rights WHERE season=?',(day.season,)).fetchone()
    first=day.season+int(day.day_in_season>216 or legacy is not None)
    c.execute('INSERT INTO annual_runtime VALUES (1,?,?)',(first,day.absolute_day))
