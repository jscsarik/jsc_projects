"""Transactional, backed-up conversion of stored 31-week dates to 32 weeks."""
import json,re

V25_STATEMENTS=(
"CREATE TABLE IF NOT EXISTS season32_adoption(game_id INTEGER PRIMARY KEY REFERENCES game(id) ON DELETE CASCADE,source_day INTEGER NOT NULL)",
"CREATE TABLE IF NOT EXISTS age_milestones(game_id INTEGER NOT NULL REFERENCES game(id) ON DELETE CASCADE,season INTEGER NOT NULL,regular_week INTEGER NOT NULL,completed_day INTEGER NOT NULL,PRIMARY KEY(game_id,season,regular_week))",
"CREATE TABLE IF NOT EXISTS paid_draft_contracts(contract_id TEXT PRIMARY KEY REFERENCES finance_contracts(id) ON DELETE CASCADE,game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,negotiated INTEGER NOT NULL)",
"ALTER TABLE annual_turns ADD COLUMN registration TEXT NOT NULL DEFAULT 'pro' CHECK(registration IN ('pro','trainee'))",
)

def map_day(day):
    if day is None:return None
    if day<-7:return day  # Founding recruitment round identifiers, not dates.
    if day<0:return day+7
    season,offset=divmod(day,217)
    return season*224+offset+(7 if offset<84 else 14)

DATE_COLUMNS={'absolute_day','rollout_day','last_appearance_day','squad_since','injury_day','recovery_day','forced_down_day','history_known_since','start_day','end_day','retired_day','started_day','deadline','market_close','closes','created_day','executed_day','next_day','finalized_day','appeared_day','completed_day','picked_day','application_day','draw_day','deadline_day','period_start','period_end','week_start'}
JSON_DATES=DATE_COLUMNS|{'aging_anchor_day','cycle_day','day','date','since','last_appearance','last_day'}

def json_dates(value,key=''):
    if isinstance(value,dict):return {k:json_dates(v,k) for k,v in value.items()}
    if isinstance(value,list):return [json_dates(v,'absolute_day' if key in ('appearance_dates','dates') else '') for v in value]
    if type(value) is int and key in JSON_DATES:return map_day(value)
    return value

def install_sunday_guards(c):
    row=c.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='squad_leader_insert_guard'").fetchone()
    if row and 'Founding Sunday' not in row[0]:
        c.execute('DROP TRIGGER squad_leader_insert_guard')
        sql=row[0].replace('(SELECT absolute_day%7 FROM game_clock WHERE game_id=1)=0 OR', """(SELECT absolute_day%7 FROM game_clock WHERE game_id=1)=0 OR
                /* Founding Sunday: first leader only */
                ((SELECT absolute_day FROM game_clock WHERE game_id=1)=6 AND NOT EXISTS(SELECT 1 FROM squad_leaders WHERE agency_id=NEW.agency_id AND squad=NEW.squad)) OR""")
        c.execute(sql)

def migrate(c):
    install_sunday_guards(c)
    if not c.execute('SELECT 1 FROM game WHERE id=1').fetchone():return
    # Prepared event payload hashes cannot safely change mid-calculation.
    if c.execute("SELECT 1 FROM match_runs WHERE status!='completed' UNION ALL SELECT 1 FROM special_rounds WHERE status='prepared' UNION ALL SELECT 1 FROM final_contests WHERE status='prepared' LIMIT 1").fetchone():
        raise RuntimeError('진행 중이거나 준비된 경기가 있어 32주 변환을 중단했습니다. 기존 버전에서 해당 경기를 완료한 뒤 다시 여세요. 원본 세이브는 유지됩니다.')
    source=c.execute('SELECT absolute_day FROM game_clock WHERE game_id=1').fetchone()[0]
    installments=[tuple(r) for r in c.execute("SELECT id,next_day FROM market_release_plans WHERE method='installments' AND paid_count<10 AND next_day>=?",(source,))]
    for row in c.execute('SELECT injury_day,recovery_day FROM player_conditions WHERE injured=1 AND injury_day IS NOT NULL AND recovery_day IS NOT NULL'):
        if map_day(row[1])-map_day(row[0])!=row[1]-row[0]:raise RuntimeError('부상 회복 구간이 새 중간 정비 주와 겹쳐 자동 변환을 중단했습니다. 기존 버전에서 회복 후 다시 열어 주세요. 원본은 보존됩니다.')
    birthday=[tuple(r) for r in c.execute("SELECT absolute_day FROM development_settlements WHERE kind='birthday'")]
    triggers=[tuple(r) for r in c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'")]
    for name,_ in triggers:c.execute('DROP TRIGGER "'+name+'"')
    c.execute('PRAGMA defer_foreign_keys=ON')
    protected={t:[tuple(r) for r in c.execute('SELECT '+cols+' FROM '+t+' ORDER BY 1')] for t,cols in (('abilities','*'),('idols','*'),('agencies','*'),('roster_memberships','*'),('draft_picks','*'))}
    c.create_function('season32_day',1,map_day)
    skip={'legacy_game_clock','season32_adoption','age_milestones'}
    tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    columns={t:[r[1] for r in c.execute('PRAGMA table_info("'+t+'")')] for t in tables}
    for t in tables:
        if t in skip:continue
        dates=[n for n in columns[t] if n in DATE_COLUMNS]
        if dates:
            c.execute('UPDATE "'+t+'" SET '+','.join('"'+n+'"=CASE WHEN "'+n+'" IS NULL THEN NULL ELSE season32_day("'+n+'")+7000000000 END' for n in dates))
    for t in tables:
        if t in skip:continue
        dates=[n for n in columns[t] if n in DATE_COLUMNS]
        if dates:c.execute('UPDATE "'+t+'" SET '+','.join('"'+n+'"="'+n+'"-7000000000' for n in dates))
        for n in columns[t]:
            if not n.endswith('_json'):continue
            for row in c.execute('SELECT rowid,"'+n+'" FROM "'+t+'" WHERE "'+n+'" IS NOT NULL').fetchall():
                try:
                    before=json.loads(row[1]);after=json_dates(before)
                    if before!=after:c.execute('UPDATE "'+t+'" SET "'+n+'"=? WHERE rowid=?',(json.dumps(after,ensure_ascii=False),row[0]))
                except (ValueError,TypeError):continue
    # These presentation/idempotency keys embed dates; entity UUIDs stay intact.
    for table,column in (('coach_reports','report_key'),('coach_seen','source_key')):
        for rowid,key in c.execute('SELECT rowid,'+column+' FROM '+table).fetchall():
            match=re.fullmatch(r'(daily:|result:[^:]+:|trainee:)(-?\d+)',key)
            if match:c.execute('UPDATE '+table+' SET '+column+'=? WHERE rowid=?',(match[1]+str(map_day(int(match[2]))),rowid))
    setup=c.execute("SELECT prep_day FROM founding_setup WHERE game_id=1 AND status IN ('pending','active')").fetchone()
    if setup:c.execute('UPDATE game_clock SET absolute_day=?',(setup[0],))
    for (old,) in birthday:
        offset=old%217
        if offset in (77,161):c.execute('INSERT OR IGNORE INTO age_milestones VALUES (1,?,?,?)',(old//217+1,12 if offset==77 else 24,map_day(old)))
    for rowid,context in c.execute('SELECT rowid,context FROM market_negotiations').fetchall():
        match=re.fullmatch(r'(\d+):(\d+)',context)
        if match:
            mapped=map_day((int(match[1])-1)*217+int(match[2])*7)
            c.execute('UPDATE market_negotiations SET context=? WHERE rowid=?',(f'{mapped//224+1}:{mapped%224//7}',rowid))
    c.execute("UPDATE ai_trade_windows SET deadline_day=(SELECT created_day+7 FROM market_trades WHERE id=trade_id) WHERE trade_id IN (SELECT id FROM market_trades WHERE status IN ('proposed','countered','accepted_pending'))")
    # Weekly repayments must not skip the newly inserted maintenance Monday.
    for identity,due in installments:
        c.execute('UPDATE market_release_plans SET next_day=? WHERE id=?',(map_day(due-7)+7,identity))
    c.execute('INSERT INTO season32_adoption VALUES (1,?)',(source,))
    for name,sql in triggers:c.execute(sql)
    for t,cols in (('abilities','*'),('idols','*'),('agencies','*'),('roster_memberships','*'),('draft_picks','*')):
        if protected[t]!=[tuple(r) for r in c.execute('SELECT '+cols+' FROM '+t+' ORDER BY 1')]:raise RuntimeError('32주 변환 보존 검사 실패: '+t)
    if c.execute('PRAGMA foreign_key_check').fetchone():raise RuntimeError('32주 변환 참조 검사 실패. 원본은 유지됩니다.')
