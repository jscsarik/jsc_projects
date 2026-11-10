"""Forward-only age policy adoption and UI-only coach records."""
V24_STATEMENTS=(
"UPDATE development_runtime SET rules_json=json_set(rules_json,'$.annual_age_increase',2,'$.age_increase_regular_weeks',json('[12,24]'))",
"CREATE TABLE IF NOT EXISTS age_policy(game_id INTEGER PRIMARY KEY REFERENCES game(id) ON DELETE CASCADE,rollout_day INTEGER NOT NULL)",
"CREATE TABLE IF NOT EXISTS coach_runtime(game_id INTEGER PRIMARY KEY REFERENCES game(id) ON DELETE CASCADE,rollout_day INTEGER NOT NULL)",
"""CREATE TABLE IF NOT EXISTS coach_reports(game_id INTEGER NOT NULL REFERENCES game(id) ON DELETE CASCADE,
 report_key TEXT NOT NULL,absolute_day INTEGER NOT NULL,kind TEXT NOT NULL,body TEXT NOT NULL,
 targets_json TEXT NOT NULL,is_read INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(game_id,report_key))""",
"CREATE TABLE IF NOT EXISTS coach_seen(game_id INTEGER NOT NULL REFERENCES game(id) ON DELETE CASCADE,source_key TEXT NOT NULL,PRIMARY KEY(game_id,source_key))",
)

def initialize_age_policy(c):
    from .game_clock import current_game_date
    day=current_game_date(c)
    if day:c.execute('INSERT OR IGNORE INTO age_policy VALUES (1,?)',(day.absolute_day,))

def initialize_coach(c):
    from .game_clock import current_game_date
    day=current_game_date(c)
    if day and c.execute('INSERT OR IGNORE INTO coach_runtime VALUES (1,?)',(day.absolute_day,)).rowcount:
        count=c.execute('SELECT COUNT(*) FROM draft_picks').fetchone()[0]
        c.execute('INSERT OR IGNORE INTO coach_seen VALUES (1,?)',('initial:'+str(count),))
