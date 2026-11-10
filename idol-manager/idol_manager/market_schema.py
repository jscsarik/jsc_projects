"""V13 preserves all rows, expands contract intervals and adds market journals."""
MARKET_TABLES=('market_draft_rights','market_draft_outcomes','market_installments','market_release_plans','market_history','market_trade_versions','market_trades',
 'market_bids','market_auctions','market_offers','market_negotiations','market_terms','market_careers','market_days','market_runtime')
V13_STATEMENTS=(
'''CREATE TABLE market_runtime(game_id INTEGER PRIMARY KEY REFERENCES game(id) ON DELETE CASCADE,rollout_day INTEGER NOT NULL)''',
'''CREATE TABLE market_terms(contract_id TEXT PRIMARY KEY REFERENCES finance_contracts(id) ON DELETE CASCADE,
 root_id TEXT NOT NULL,start_season INTEGER NOT NULL,end_season INTEGER,source TEXT NOT NULL)''',
'''CREATE TABLE market_careers(person_id TEXT PRIMARY KEY REFERENCES idols(person_id) ON DELETE CASCADE,
 debut_season INTEGER,last_agency TEXT REFERENCES agencies(id),unemployed_since INTEGER,retired_day INTEGER)''',
'''CREATE TABLE market_days(game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 absolute_day INTEGER NOT NULL,PRIMARY KEY(game_id,absolute_day))''',
'''CREATE TABLE market_negotiations(id TEXT PRIMARY KEY,game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 agency_id TEXT NOT NULL REFERENCES agencies(id),person_id TEXT NOT NULL REFERENCES idols(person_id) ON DELETE CASCADE,
 purpose TEXT NOT NULL,status TEXT NOT NULL,started_day INTEGER NOT NULL,context TEXT NOT NULL,
 UNIQUE(agency_id,person_id,purpose,context))''',
'''CREATE TABLE market_offers(id TEXT PRIMARY KEY,negotiation_id TEXT NOT NULL REFERENCES market_negotiations(id) ON DELETE CASCADE,
 ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 1 AND 3),annual INTEGER NOT NULL,duration INTEGER NOT NULL CHECK(duration IN (1,2)),
 probability REAL NOT NULL,seed TEXT NOT NULL,roll REAL NOT NULL,accepted INTEGER NOT NULL,absolute_day INTEGER NOT NULL,
 UNIQUE(negotiation_id,ordinal))''',
'''CREATE TABLE market_auctions(id TEXT PRIMARY KEY,game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 person_id TEXT NOT NULL REFERENCES idols(person_id) ON DELETE CASCADE,season INTEGER NOT NULL,original_agency TEXT,
 deadline INTEGER NOT NULL,market_close INTEGER NOT NULL,status TEXT NOT NULL,winner TEXT,seed TEXT,result_json TEXT NOT NULL DEFAULT '{}',
 UNIQUE(person_id,season))''',
'''CREATE TABLE market_bids(id TEXT PRIMARY KEY,auction_id TEXT NOT NULL REFERENCES market_auctions(id) ON DELETE CASCADE,
 agency_id TEXT NOT NULL REFERENCES agencies(id),annual INTEGER NOT NULL,duration INTEGER NOT NULL CHECK(duration IN (1,2)),absolute_day INTEGER NOT NULL)''',
'''CREATE TABLE market_trades(id TEXT PRIMARY KEY,game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 agency_a TEXT NOT NULL REFERENCES agencies(id),agency_b TEXT NOT NULL REFERENCES agencies(id),status TEXT NOT NULL,
 version INTEGER NOT NULL,proposer TEXT NOT NULL,created_day INTEGER NOT NULL,executed_day INTEGER,execution_json TEXT)''',
'''CREATE TABLE market_trade_versions(trade_id TEXT NOT NULL REFERENCES market_trades(id) ON DELETE CASCADE,
 version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 3),proposer TEXT NOT NULL,absolute_day INTEGER NOT NULL,
 terms_json TEXT NOT NULL,response TEXT,PRIMARY KEY(trade_id,version))''',
'''CREATE TABLE market_history(id TEXT PRIMARY KEY,game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 person_id TEXT NOT NULL REFERENCES people(id),from_agency TEXT,to_agency TEXT,absolute_day INTEGER NOT NULL,
 kind TEXT NOT NULL,contract_id TEXT,annual INTEGER,cash INTEGER NOT NULL DEFAULT 0,penalty INTEGER NOT NULL DEFAULT 0,
 related_id TEXT,details_json TEXT NOT NULL DEFAULT '{}')''',
'''CREATE TABLE market_release_plans(id TEXT PRIMARY KEY,game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 person_id TEXT NOT NULL REFERENCES people(id),agency_id TEXT NOT NULL REFERENCES agencies(id),absolute_day INTEGER NOT NULL,
 total INTEGER NOT NULL,method TEXT NOT NULL,debt_id INTEGER REFERENCES finance_debts(id),next_day INTEGER NOT NULL,paid_count INTEGER NOT NULL DEFAULT 0,UNIQUE(person_id,absolute_day))''',
'''CREATE TABLE market_installments(plan_id TEXT REFERENCES market_release_plans(id) ON DELETE CASCADE,ordinal INTEGER NOT NULL,
 settlement_id TEXT NOT NULL REFERENCES finance_settlements(id) ON DELETE CASCADE,amount INTEGER NOT NULL,PRIMARY KEY(plan_id,ordinal))''',
'''CREATE TABLE market_draft_rights(id TEXT PRIMARY KEY,game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 season INTEGER NOT NULL,agency_id TEXT NOT NULL REFERENCES agencies(id),person_id TEXT NOT NULL REFERENCES idols(person_id) ON DELETE CASCADE,
 consumed INTEGER NOT NULL DEFAULT 0,UNIQUE(season,person_id))''',
'''CREATE TABLE market_draft_outcomes(game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 season INTEGER NOT NULL,person_id TEXT NOT NULL REFERENCES idols(person_id) ON DELETE CASCADE,picked INTEGER NOT NULL,
 PRIMARY KEY(season,person_id))''',
'CREATE INDEX market_contract_person_period ON finance_contracts(person_id,start_day,end_day)',
'CREATE INDEX market_history_person ON market_history(person_id,absolute_day)',
'''CREATE TRIGGER market_no_pro_to_trainee BEFORE UPDATE OF career_status ON roster_memberships
 WHEN NEW.career_status='trainee' AND EXISTS(SELECT 1 FROM market_careers WHERE person_id=NEW.person_id AND debut_season IS NOT NULL)
 BEGIN SELECT RAISE(ABORT,'A professional cannot return to trainee status'); END''',
)

def rebuild_contracts(c):
    # Called with foreign_keys OFF before the migration transaction. Check every
    # FK before commit. No contract/payroll/debt/history row is discarded.
    for trigger in ('finance_contract_overlap','finance_contract_terms_immutable','finance_pro_debut'):
        c.execute('DROP TRIGGER IF EXISTS '+trigger)
    c.execute('''CREATE TABLE finance_contracts_new(id TEXT PRIMARY KEY,game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
        person_id TEXT NOT NULL REFERENCES idols(person_id) ON DELETE CASCADE,agency_id TEXT NOT NULL REFERENCES agencies(id),
        kind TEXT NOT NULL CHECK(kind IN ('pro','draft_trainee','free_trainee')),annual_krw INTEGER NOT NULL CHECK(typeof(annual_krw)='integer' AND annual_krw>=0),
        start_day INTEGER NOT NULL,end_day INTEGER CHECK(end_day IS NULL OR end_day>=start_day),source TEXT NOT NULL)''')
    c.execute('INSERT INTO finance_contracts_new SELECT * FROM finance_contracts');c.execute('DROP TABLE finance_contracts')
    c.execute('ALTER TABLE finance_contracts_new RENAME TO finance_contracts')
    from .finance_schema import V12_STATEMENTS
    for sql in V12_STATEMENTS:
        if any(sql.startswith('CREATE TRIGGER '+name) for name in ('finance_contract_overlap','finance_contract_terms_immutable','finance_pro_debut')):c.execute(sql)

    c.execute("CREATE TABLE finance_settlements_new(id TEXT PRIMARY KEY,game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,agency_id TEXT NOT NULL REFERENCES agencies(id),season INTEGER NOT NULL,week INTEGER NOT NULL,absolute_day INTEGER NOT NULL,kind TEXT NOT NULL CHECK(kind IN ('opening','weekly','bonus','market')))")
    c.execute('INSERT INTO finance_settlements_new SELECT * FROM finance_settlements')
    c.execute('DROP TABLE finance_settlements');c.execute('ALTER TABLE finance_settlements_new RENAME TO finance_settlements')
    c.execute("CREATE UNIQUE INDEX unique_periodic_finance ON finance_settlements(game_id,agency_id,season,week,kind) WHERE kind!='market'")
