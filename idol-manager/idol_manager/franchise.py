"""Continuous ownership ledger and conservative, completed-season service credits."""
import json,sqlite3
from .game_clock import current_game_date,DAYS_PER_SEASON,regular_day

V26_STATEMENTS=(
'''CREATE TABLE franchise_stints(id INTEGER PRIMARY KEY,game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 person_id TEXT NOT NULL REFERENCES idols(person_id) ON DELETE CASCADE,agency_id TEXT NOT NULL REFERENCES agencies(id),
 started_day INTEGER NOT NULL,ended_day INTEGER,source TEXT NOT NULL)''',
'''CREATE UNIQUE INDEX franchise_current ON franchise_stints(person_id) WHERE ended_day IS NULL''',
'''CREATE TABLE franchise_seasons(stint_id INTEGER NOT NULL REFERENCES franchise_stints(id) ON DELETE CASCADE,
 season INTEGER NOT NULL,units INTEGER NOT NULL CHECK(units IN(0,1,2)),first_appearance INTEGER NOT NULL,
 completed_day INTEGER NOT NULL,PRIMARY KEY(stint_id,season))''',
'''CREATE TRIGGER franchise_join AFTER INSERT ON roster_memberships WHEN NEW.agency_id IS NOT NULL BEGIN
 INSERT INTO franchise_stints(person_id,agency_id,started_day,source)
 VALUES(NEW.person_id,NEW.agency_id,COALESCE((SELECT absolute_day FROM game_clock WHERE game_id=1),0),'observed'); END''',
'''CREATE TRIGGER franchise_move AFTER UPDATE OF agency_id ON roster_memberships WHEN OLD.agency_id IS NOT NEW.agency_id BEGIN
 UPDATE franchise_stints SET ended_day=COALESCE((SELECT absolute_day FROM game_clock WHERE game_id=1),0)
 WHERE person_id=NEW.person_id AND ended_day IS NULL;
 INSERT INTO franchise_stints(person_id,agency_id,started_day,source)
 SELECT NEW.person_id,NEW.agency_id,COALESCE((SELECT absolute_day FROM game_clock WHERE game_id=1),0),'observed' WHERE NEW.agency_id IS NOT NULL; END''',
)

def first_appearances(c,season):
    """Only actual first-team starts, including the frozen special-event squad."""
    result=set()
    for p,a in c.execute('''SELECT p.person_id,p.agency_id FROM match_player_stats p JOIN scheduled_matches m ON m.id=p.match_id
        WHERE m.season=?''',(season,)):result.add((p,a))
    for row in c.execute("SELECT kind,input_json,result_json FROM final_contests WHERE season=? AND kind='post' AND status='completed'",(season,)):
        for p in json.loads(row['result_json']).get('players',()):
            if p['base_attempts']:result.add((p['person_id'],p['agency_id']))
    for row in c.execute('''SELECT r.input_json,r.result_json FROM special_rounds r JOIN special_events e ON e.id=r.event_id
        WHERE e.season=? AND r.status='completed' ''',(season,)):
        squads=json.loads(row['input_json']).get('conditions',{}).get('squads',{})
        for p in json.loads(row['result_json']).get('players',()):
            if p['base_attempts'] and squads.get(p['person_id'])=='first_team':result.add((p['person_id'],p['agency_id']))
    return result

def settle(c,season):
    end=season*DAYS_PER_SEASON-1;start=end-DAYS_PER_SEASON+1
    played=first_appearances(c,season)
    for r in c.execute('SELECT * FROM franchise_stints WHERE started_day<=? AND (ended_day IS NULL OR ended_day>?)',(end,start)).fetchall():
        # A current stint earns at most one credit. Partial no-appearance seasons
        # are not assumed to have been spent entirely in a reserve/trainee role.
        appeared=(r['person_id'],r['agency_id']) in played
        if appeared:
            # A stint beginning mid-season must prove an appearance after joining.
            days=appearance_days(c,r['person_id'],r['agency_id'],season)
            appeared=any(r['started_day']<=d<(r['ended_day'] if r['ended_day'] is not None else end+1) for d in days)
        full=r['started_day']<=start and (r['ended_day'] is None or r['ended_day']>end)
        units=2 if appeared else 1 if full else 0
        c.execute('INSERT OR IGNORE INTO franchise_seasons VALUES (?,?,?,?,?)',(r['id'],season,units,int(appeared),end))

def appearance_days(c,person,agency,season):
    days=[regular_day(season,w,d) for w,d in c.execute('''SELECT m.week,m.weekday FROM match_player_stats p JOIN scheduled_matches m ON m.id=p.match_id
        WHERE p.person_id=? AND p.agency_id=? AND m.season=?''',(person,agency,season))]
    for day,raw in c.execute("SELECT absolute_day,result_json FROM final_contests WHERE season=? AND kind='post' AND status='completed'",(season,)):
        if any(p['person_id']==person and p['agency_id']==agency and p['base_attempts'] for p in json.loads(raw).get('players',())):days.append(day)
    for week,raw,summary in c.execute('''SELECT e.week,r.input_json,r.result_json FROM special_rounds r JOIN special_events e ON e.id=r.event_id
        WHERE e.season=? AND r.status='completed' ''',(season,)):
        if json.loads(raw).get('conditions',{}).get('squads',{}).get(person)=='first_team' and any(p['person_id']==person and p['agency_id']==agency and p['base_attempts'] for p in json.loads(summary).get('players',())):days.append(regular_day(season,week,6))
    return days

def eligible(c,agency=None):
    sql='''SELECT s.person_id FROM franchise_stints s JOIN roster_memberships r ON r.person_id=s.person_id AND r.agency_id=s.agency_id
        JOIN franchise_seasons y ON y.stint_id=s.id WHERE s.ended_day IS NULL'''
    args=()
    if agency is not None:sql+=' AND s.agency_id=?';args=(agency,)
    return {r[0] for r in c.execute(sql+' GROUP BY s.id HAVING SUM(y.units)>=6',args)}

def display_name(name,is_franchise):return name+' (프차)' if is_franchise else name

def restore(c):
    original=c.row_factory;c.row_factory=sqlite3.Row
    try:_restore(c)
    finally:c.row_factory=original

def _restore(c):
    day=current_game_date(c)
    if day is None:return
    # Daily facts prove only the uninterrupted suffix. Never infer missing years.
    for person,agency in c.execute('SELECT person_id,agency_id FROM roster_memberships WHERE agency_id IS NOT NULL').fetchall():
        since=day.absolute_day
        facts=c.execute('SELECT absolute_day,agency_id FROM development_days WHERE person_id=? AND absolute_day<? ORDER BY absolute_day DESC',(person,since)).fetchall()
        for d,a in facts:
            if d!=since-1 or a!=agency:break
            since=d
        changed=c.execute('SELECT MAX(absolute_day) FROM market_history WHERE person_id=? AND from_agency IS NOT to_agency',(person,)).fetchone()[0]
        if changed is not None:since=max(since,changed)
        c.execute("INSERT INTO franchise_stints(person_id,agency_id,started_day,source) VALUES (?,?,?,'proven_daily_suffix')",(person,agency,since))
    for season in range(1,day.season):settle(c,season)
