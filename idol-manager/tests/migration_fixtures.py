"""Remove only the new extension when reconstructing old schemas in temp DBs."""
from contextlib import contextmanager,closing

@contextmanager
def fail_new_game(db):
    with closing(db.connect()) as c,c:c.execute("CREATE TRIGGER qa_replace_failure BEFORE INSERT ON idols BEGIN SELECT RAISE(ABORT,'injected');END")
    try:yield
    finally:
        with closing(db.connect()) as c,c:c.execute('DROP TRIGGER qa_replace_failure')
def drop_development(c):
    drop_finance(c)
    for table in ('development_trials','development_results','development_days','development_settlements','development_runtime'):c.execute(f'DROP TABLE IF EXISTS {table}')


def drop_finance(c):
    drop_market(c)
    from idol_manager.finance_schema import FINANCE_TABLES
    c.execute('DROP TRIGGER IF EXISTS finance_pro_debut')
    c.execute('DROP INDEX IF EXISTS finance_roles_period')
    for table in FINANCE_TABLES:c.execute(f'DROP TABLE IF EXISTS {table}')

def drop_founding(c):
    for table in ('ai_trade_messages','ai_trade_windows','ai_trade_checks'):c.execute(f'DROP TABLE IF EXISTS {table}')
    row=c.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='finance_pro_debut'").fetchone()
    if row and 'founding_setup' in row[0]:
        c.execute('DROP TRIGGER finance_pro_debut')
        c.execute(row[0].replace("AND NOT EXISTS(SELECT 1 FROM founding_setup WHERE game_id=1 AND status IN ('pending','active'))",''))
    for table in ('trainee_rounds','trainee_submission_keys','trainee_results','trainee_applications','trainee_sheets','trainee_weeks','trainee_rng','founding_contracts','founding_setup'):
        c.execute(f'DROP TABLE IF EXISTS {table}')

def drop_market(c):
    drop_founding(c)
    for table in ('annual_turns','annual_pool','annual_sessions','annual_secrets','annual_entries','annual_intakes','annual_runtime','annual_assets'):
        c.execute(f'DROP TABLE IF EXISTS {table}')
    for trigger in ('health_range_insert','health_range_update'):c.execute(f'DROP TRIGGER IF EXISTS {trigger}')
    for table in ('award_outcomes','individual_awards','season_awards','award_regular_rosters','award_match_selections'):
        c.execute(f'DROP TABLE IF EXISTS {table}')
    from idol_manager.market_schema import MARKET_TABLES
    c.execute('DROP TRIGGER IF EXISTS market_no_pro_to_trainee')
    c.execute('DROP INDEX IF EXISTS unique_periodic_finance')
    c.execute('DROP INDEX IF EXISTS market_contract_person_period')
    for table in MARKET_TABLES:c.execute(f'DROP TABLE IF EXISTS {table}')


def current_rows(table,rows):
    """Only the explicitly approved v15 health cap changes legacy idol rows."""
    if table=='idols':return sorted((r[0],r[1],min(90,r[2]),*r[3:]) for r in rows)
    return rows


def drop_finals(c):
    drop_development(c)
    for operation in ('insert','update'):c.execute(f'DROP TRIGGER IF EXISTS squad_leader_{operation}_guard')
    # Restore the old Monday guard, since legacy migration fixtures may keep v5.
    for operation in ('INSERT','UPDATE'):
        c.execute(f'''CREATE TRIGGER squad_leader_{operation.lower()}_guard BEFORE {operation} ON squad_leaders BEGIN
            SELECT CASE WHEN (SELECT absolute_day%7 FROM game_clock WHERE game_id=1)!=0 THEN RAISE(ABORT,'Monday only') END;
            SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM roster_memberships WHERE person_id=NEW.person_id AND agency_id=NEW.agency_id AND career_status=NEW.squad)
                THEN RAISE(ABORT,'Invalid leader') END; END''')
    for table in ('final_contests','final_series','season_honors','season_finals','calendar_v9_archive'):c.execute(f'DROP TABLE IF EXISTS {table}')
