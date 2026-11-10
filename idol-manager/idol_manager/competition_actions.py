"""Explicit day-button automation for today's non-player tournaments only."""
from contextlib import closing
import json
from .game_clock import current_game_date,regular_day

def pending_ai(service):
    with closing(service.database.connect()) as c:
        day=current_game_date(c)
        if day is None:return ()
        player=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
        if player is None:return ()
        tasks=[]
        if day.is_postseason:
            rows=c.execute("SELECT id,agencies_json FROM final_contests WHERE absolute_day=? AND status IN ('scheduled','prepared') ORDER BY kind,round_number,game_number",(day.absolute_day,))
            tasks.extend(('finals',r['id']) for r in rows if player[0] not in json.loads(r['agencies_json']))
        if day.is_regular:
            rows=c.execute("SELECT r.id,r.agencies_json,e.season,e.week FROM special_rounds r JOIN special_events e ON e.id=r.event_id WHERE e.season=? AND e.week=? AND r.status IN ('scheduled','prepared') ORDER BY CASE r.stage WHEN 'upper' THEN 0 WHEN 'lower' THEN 1 ELSE 2 END",(day.season,day.week))
            tasks.extend(('specials',r['id']) for r in rows if regular_day(r['season'],r['week'],6)==day.absolute_day and player[0] not in json.loads(r['agencies_json']))
        return tuple(tasks)

def play_pending_ai(service):
    completed=[]
    while True:
        tasks=pending_ai(service)
        if not tasks:return tuple(completed)
        kind,identity=tasks[0]
        getattr(service,kind).play(identity)
        completed.append(identity)
