"""Once-per-season registration/rest reset and seven extra recovery days."""
import json
from .game_clock import GameDate,current_game_date

V28_STATEMENTS=('''CREATE TABLE maintenance_condition_resets(game_id INTEGER NOT NULL REFERENCES game(id) ON DELETE CASCADE,
 season INTEGER NOT NULL,absolute_day INTEGER NOT NULL,summary_json TEXT NOT NULL,PRIMARY KEY(game_id,season))''',)

def apply_reset(c,day):
    date=GameDate(day)
    if not date.is_maintenance:return False
    if c.execute('SELECT 1 FROM maintenance_condition_resets WHERE game_id=1 AND season=?',(date.season,)).fetchone():return False
    before=[tuple(r) for r in c.execute('''SELECT p.person_id,p.registration_weeks,p.complete_rest_weeks,p.squad_since
        FROM player_conditions p JOIN roster_memberships r ON r.person_id=p.person_id
        WHERE r.career_status IN ('first_team','second_team','pro_pending')''')]
    c.execute('''UPDATE player_conditions SET registration_weeks=0,complete_rest_weeks=0,registration_week=?,squad_since=?
        WHERE person_id IN (SELECT person_id FROM roster_memberships WHERE career_status IN ('first_team','second_team','pro_pending'))''',(day//7,day))
    recoveries=[]
    for person,injury,old in c.execute('SELECT person_id,injury_day,recovery_day FROM player_conditions WHERE injured=1 AND recovery_day IS NOT NULL').fetchall():
        new=max(day,old-7);recovered=new<=day
        c.execute('UPDATE player_conditions SET recovery_day=?,injured=? WHERE person_id=?',(new,int(not recovered),person))
        if recovered:
            c.execute('''INSERT OR IGNORE INTO condition_events(event_key,person_id,absolute_day,kind,occurred,details_json)
                VALUES (?,?,?,'recovery',1,?)''',(f'recovery:{person}:{injury}',person,day,json.dumps({'reason':'maintenance_extra_week','previous_recovery_day':old})))
        recoveries.append(dict(person_id=person,before=old,after=new,recovered=recovered))
    c.execute('INSERT INTO maintenance_condition_resets VALUES (1,?,?,?)',(date.season,day,json.dumps(dict(registration_before=before,recoveries=recoveries),ensure_ascii=False)))
    return True

def adopt(c):
    date=current_game_date(c)
    if date:apply_reset(c,date.absolute_day)
