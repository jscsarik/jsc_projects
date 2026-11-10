"""Version 12: forward-only finance, effective contracts and immutable journals."""
FINANCE_TABLES=('finance_points','finance_debts','finance_payroll','finance_ledger','finance_settlements','finance_contracts','finance_runtime')
V12_STATEMENTS=(
'''CREATE TABLE finance_runtime(game_id INTEGER PRIMARY KEY REFERENCES game(id) ON DELETE CASCADE,
 rollout_day INTEGER NOT NULL,closed_seasons_json TEXT NOT NULL,rules_json TEXT NOT NULL)''',
'''CREATE TABLE finance_contracts(id TEXT PRIMARY KEY,game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 person_id TEXT NOT NULL REFERENCES idols(person_id) ON DELETE CASCADE,agency_id TEXT NOT NULL REFERENCES agencies(id),
 kind TEXT NOT NULL CHECK(kind IN ('pro','draft_trainee','free_trainee')),annual_krw INTEGER NOT NULL CHECK(typeof(annual_krw)='integer' AND annual_krw>=0),
 start_day INTEGER NOT NULL,end_day INTEGER CHECK(end_day IS NULL OR end_day>start_day),source TEXT NOT NULL,
 UNIQUE(person_id,start_day))''',
'''CREATE TABLE finance_settlements(id TEXT PRIMARY KEY,game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 agency_id TEXT NOT NULL REFERENCES agencies(id),season INTEGER NOT NULL,week INTEGER NOT NULL,absolute_day INTEGER NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('opening','weekly','bonus')),UNIQUE(game_id,agency_id,season,week,kind))''',
'''CREATE TABLE finance_ledger(id INTEGER PRIMARY KEY,game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 settlement_id TEXT NOT NULL REFERENCES finance_settlements(id) ON DELETE CASCADE,agency_id TEXT NOT NULL REFERENCES agencies(id),
 season INTEGER NOT NULL,week INTEGER NOT NULL,absolute_day INTEGER NOT NULL,kind TEXT NOT NULL,amount INTEGER NOT NULL,
 cash_delta INTEGER NOT NULL,debt_delta INTEGER NOT NULL,cash_before INTEGER NOT NULL CHECK(cash_before>=0),
 cash_after INTEGER NOT NULL CHECK(cash_after>=0),person_id TEXT REFERENCES people(id),description TEXT NOT NULL,
 CHECK(cash_after=cash_before+cash_delta))''',
'''CREATE TABLE finance_payroll(id TEXT PRIMARY KEY,game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 settlement_id TEXT NOT NULL REFERENCES finance_settlements(id) ON DELETE CASCADE,contract_id TEXT NOT NULL REFERENCES finance_contracts(id) ON DELETE CASCADE,
 person_id TEXT NOT NULL REFERENCES people(id),agency_id TEXT NOT NULL REFERENCES agencies(id),season INTEGER NOT NULL,cycle INTEGER NOT NULL,
 annual_krw INTEGER NOT NULL,base_krw INTEGER NOT NULL,first_weeks INTEGER NOT NULL,second_weeks INTEGER NOT NULL,
 bonus_krw INTEGER NOT NULL,reduction_krw INTEGER NOT NULL,due_krw INTEGER NOT NULL CHECK(due_krw>=0),
 paid_krw INTEGER NOT NULL CHECK(paid_krw>=0 AND paid_krw<=due_krw),facts_json TEXT NOT NULL,UNIQUE(contract_id,season,cycle))''',
'''CREATE TABLE finance_debts(id INTEGER PRIMARY KEY,game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 settlement_id TEXT NOT NULL REFERENCES finance_settlements(id) ON DELETE CASCADE,agency_id TEXT NOT NULL REFERENCES agencies(id),
 person_id TEXT REFERENCES people(id),payroll_id TEXT REFERENCES finance_payroll(id) ON DELETE CASCADE,kind TEXT NOT NULL,
 original_krw INTEGER NOT NULL CHECK(original_krw>0),outstanding_krw INTEGER NOT NULL CHECK(outstanding_krw>=0 AND outstanding_krw<=original_krw))''',
'''CREATE TABLE finance_points(settlement_id TEXT PRIMARY KEY REFERENCES finance_settlements(id) ON DELETE CASCADE,
 game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,season INTEGER NOT NULL,
 agency_id TEXT NOT NULL REFERENCES agencies(id),delta INTEGER NOT NULL CHECK(delta=-2),reason TEXT NOT NULL)''',
'''CREATE TRIGGER finance_pro_debut AFTER UPDATE OF career_status,agency_id ON roster_memberships
 WHEN NEW.career_status IN ('pro_pending','first_team','second_team')
 AND EXISTS(SELECT 1 FROM finance_runtime WHERE game_id=1)
 AND NOT EXISTS(SELECT 1 FROM finance_contracts WHERE person_id=NEW.person_id)
 BEGIN INSERT INTO finance_contracts
 SELECT 'debut:'||NEW.person_id,1,NEW.person_id,NEW.agency_id,'pro',
 CAST(json_extract(rules_json,'$.first_contract_annual_krw') AS INTEGER),
 COALESCE((SELECT absolute_day FROM game_clock WHERE game_id=1),0),NULL,'master_first_pro_30m_forward_only'
 FROM finance_runtime WHERE game_id=1; END''',
'CREATE INDEX finance_ledger_agency ON finance_ledger(agency_id,season,absolute_day,id)',
'CREATE INDEX finance_roles_period ON development_days(agency_id,absolute_day,role)',
'''CREATE TRIGGER finance_contract_overlap BEFORE INSERT ON finance_contracts BEGIN
 SELECT CASE WHEN EXISTS(SELECT 1 FROM finance_contracts WHERE person_id=NEW.person_id
 AND COALESCE(end_day,9223372036854775807)>NEW.start_day AND COALESCE(NEW.end_day,9223372036854775807)>start_day)
 THEN RAISE(ABORT,'Contract periods must not overlap') END; END''',
'''CREATE TRIGGER finance_contract_terms_immutable BEFORE UPDATE OF person_id,agency_id,annual_krw,start_day,kind ON finance_contracts
 BEGIN SELECT RAISE(ABORT,'Append a new effective contract; do not rewrite past terms'); END''',
'''CREATE TRIGGER finance_journal_immutable BEFORE UPDATE ON finance_ledger
 BEGIN SELECT RAISE(ABORT,'Finance journal is append-only'); END''',
)
