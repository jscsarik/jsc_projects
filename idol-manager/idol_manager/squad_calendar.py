"""Calendar gates shared by setup and the new roster maintenance windows."""
from .game_clock import current_game_date

def initial_sunday(c):
    d=current_game_date(c)
    return bool(d and d.is_founding and d.weekday()==6)

def vacant_leader_allowed(c,agency,squad):
    d=current_game_date(c)
    if not d or squad not in ('first_team','second_team'):return False
    if not (initial_sunday(c) or d.is_maintenance or (d.is_preparation and not d.is_founding)):return False
    if not c.execute('SELECT 1 FROM squad_formations WHERE agency_id=?',(agency,)).fetchone():return False
    if c.execute('SELECT 1 FROM squad_leaders WHERE agency_id=? AND squad=?',(agency,squad)).fetchone():return False
    if c.execute("SELECT 1 FROM match_runs WHERE status!='completed' UNION ALL SELECT 1 FROM special_rounds WHERE status='prepared' UNION ALL SELECT 1 FROM final_contests WHERE status='prepared' OR (kind='tie' AND status!='completed') LIMIT 1").fetchone():return False
    return True

def install_vacancy_guard(c):
    row=c.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='squad_leader_insert_guard'").fetchone()
    original='(SELECT absolute_day%7 FROM game_clock WHERE game_id=1)=0 OR'
    if not row or original not in row[0]:raise RuntimeError('리더 지정 보호 규칙을 확인하지 못해 업데이트를 중단했습니다.')
    sql=row[0].replace(original,original+''' /* Vacant maintenance/preparation leader only */
        (EXISTS(SELECT 1 FROM game_clock WHERE game_id=1 AND
          (absolute_day%224 BETWEEN 91 AND 97 OR (absolute_day>=224 AND absolute_day%224<7)))
         AND EXISTS(SELECT 1 FROM squad_formations WHERE agency_id=NEW.agency_id)
         AND NOT EXISTS(SELECT 1 FROM squad_leaders WHERE agency_id=NEW.agency_id AND squad=NEW.squad)
         AND NOT EXISTS(SELECT 1 FROM match_runs WHERE status!='completed')
         AND NOT EXISTS(SELECT 1 FROM special_rounds WHERE status='prepared')
         AND NOT EXISTS(SELECT 1 FROM final_contests WHERE status='prepared')) OR''',1)
    c.execute('DROP TRIGGER squad_leader_insert_guard');c.execute(sql)

def ready_for_play(c):
    for agency, in c.execute('SELECT id FROM agencies').fetchall():
        counts=dict(c.execute('SELECT career_status,COUNT(*) FROM roster_memberships WHERE agency_id=? GROUP BY career_status',(agency,)))
        if counts.get('first_team',0)!=5 or counts.get('second_team',0)>11 or counts.get('pro_pending',0) or sum(counts.get(k,0) for k in ('first_team','second_team'))>16:
            raise ValueError('정비 완료 전에 각 기획사의 1군 5명·프로 최대 16명 편성을 완료해 주세요.')
        if c.execute('SELECT COUNT(*) FROM squad_leaders WHERE agency_id=?',(agency,)).fetchone()[0]!=2:raise ValueError('정비 완료 전에 1군·2군 리더를 지정해 주세요.')
