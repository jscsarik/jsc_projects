"""Additive v18. Absence of a founding row identifies an unchanged legacy save."""
V18_STATEMENTS=(
'''CREATE TABLE founding_setup(game_id INTEGER PRIMARY KEY REFERENCES game(id) ON DELETE CASCADE,
 status TEXT NOT NULL CHECK(status IN ('pending','active','completed')),prep_day INTEGER NOT NULL DEFAULT 0 CHECK(prep_day BETWEEN 0 AND 6))''',
'''CREATE TABLE founding_contracts(game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 person_id TEXT PRIMARY KEY REFERENCES idols(person_id) ON DELETE CASCADE,agency_id TEXT NOT NULL REFERENCES agencies(id),
 round_number INTEGER NOT NULL CHECK(round_number BETWEEN 1 AND 3),status TEXT NOT NULL CHECK(status IN ('pending','signed','failed')),
 negotiation_id TEXT REFERENCES market_negotiations(id) ON DELETE SET NULL)''',
'''CREATE TABLE trainee_rng(game_id INTEGER PRIMARY KEY REFERENCES game(id) ON DELETE CASCADE,state_json TEXT NOT NULL)''',
'''CREATE TABLE trainee_weeks(game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 absolute_day INTEGER NOT NULL CHECK(absolute_day%7=0),status TEXT NOT NULL CHECK(status IN ('open','finalized')),
 rng_before TEXT,rng_after TEXT,PRIMARY KEY(game_id,absolute_day))''',
'''CREATE TABLE trainee_sheets(game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 absolute_day INTEGER NOT NULL,agency_id TEXT NOT NULL REFERENCES agencies(id),revision INTEGER NOT NULL DEFAULT 0,
 confirmed INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(game_id,absolute_day,agency_id),
 FOREIGN KEY(game_id,absolute_day) REFERENCES trainee_weeks(game_id,absolute_day) ON DELETE CASCADE)''',
'''CREATE TABLE trainee_applications(game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 absolute_day INTEGER NOT NULL,agency_id TEXT NOT NULL REFERENCES agencies(id),slot INTEGER NOT NULL CHECK(slot IN (0,1)),
 person_id TEXT NOT NULL REFERENCES idols(person_id) ON DELETE CASCADE,status TEXT NOT NULL DEFAULT 'pending',
 PRIMARY KEY(game_id,absolute_day,agency_id,slot),UNIQUE(game_id,absolute_day,agency_id,person_id),
 FOREIGN KEY(game_id,absolute_day,agency_id) REFERENCES trainee_sheets(game_id,absolute_day,agency_id) ON DELETE CASCADE)''',
'''CREATE TABLE trainee_results(game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 absolute_day INTEGER NOT NULL,person_id TEXT NOT NULL REFERENCES idols(person_id) ON DELETE CASCADE,
 winner TEXT REFERENCES agencies(id),status TEXT NOT NULL,applicants_json TEXT NOT NULL,draw_index INTEGER,
 PRIMARY KEY(game_id,absolute_day,person_id),FOREIGN KEY(game_id,absolute_day) REFERENCES trainee_weeks(game_id,absolute_day) ON DELETE CASCADE)''',
'''CREATE TABLE trainee_submission_keys(id TEXT PRIMARY KEY,game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 absolute_day INTEGER NOT NULL,agency_id TEXT NOT NULL REFERENCES agencies(id),person_id TEXT NOT NULL REFERENCES idols(person_id) ON DELETE CASCADE)''',
'''DROP TRIGGER finance_pro_debut''',
'''CREATE TRIGGER finance_pro_debut AFTER UPDATE OF career_status,agency_id ON roster_memberships
 WHEN NEW.career_status IN ('pro_pending','first_team','second_team')
 AND EXISTS(SELECT 1 FROM finance_runtime WHERE game_id=1)
 AND NOT EXISTS(SELECT 1 FROM founding_setup WHERE game_id=1 AND status IN ('pending','active'))
 AND NOT EXISTS(SELECT 1 FROM finance_contracts WHERE person_id=NEW.person_id)
 BEGIN INSERT INTO finance_contracts SELECT 'debut:'||NEW.person_id,1,NEW.person_id,NEW.agency_id,'pro',
 CAST(json_extract(rules_json,'$.first_contract_annual_krw') AS INTEGER),
 COALESCE((SELECT absolute_day FROM game_clock WHERE game_id=1),0),NULL,'master_first_pro_30m_forward_only'
 FROM finance_runtime WHERE game_id=1; END''',
)

V19_STATEMENTS=(
"ALTER TABLE founding_setup ADD COLUMN protocol INTEGER NOT NULL DEFAULT 1 CHECK(protocol IN (1,2))",
'''CREATE TABLE trainee_rounds(game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 round_key INTEGER NOT NULL,application_day INTEGER NOT NULL,draw_day INTEGER NOT NULL,
 round_number INTEGER NOT NULL,submitted INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(game_id,round_key),UNIQUE(game_id,application_day))''',
)
