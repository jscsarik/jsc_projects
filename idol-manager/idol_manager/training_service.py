"""Tuesday focus sheets; saved trial replay is read-only and never exposes PA."""
from contextlib import closing
import json
from .config import SKILLS
from .game_clock import current_game_date,GameDate
from .finance_service import FinanceService,journal

FOCUS_COST=150000
V22_STATEMENTS=(
'''CREATE TABLE training_sheets(game_id INTEGER NOT NULL REFERENCES game(id) ON DELETE CASCADE,
 week_start INTEGER NOT NULL,agency_id TEXT NOT NULL REFERENCES agencies(id),confirmed INTEGER NOT NULL DEFAULT 0,
 revision INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(game_id,week_start,agency_id))''',
'''CREATE TABLE training_choices(game_id INTEGER NOT NULL DEFAULT 1,week_start INTEGER NOT NULL,agency_id TEXT NOT NULL,
 person_id TEXT NOT NULL REFERENCES idols(person_id),skill TEXT,
 PRIMARY KEY(game_id,week_start,agency_id,person_id),
 FOREIGN KEY(game_id,week_start,agency_id) REFERENCES training_sheets(game_id,week_start,agency_id) ON DELETE CASCADE)''',
"UPDATE development_runtime SET rules_json=json_set(rules_json,'$.weekly_basic.second_team_skills',3,'$.version','development-2-training')",
"UPDATE finance_runtime SET rules_json=json_set(rules_json,'$.optional_focus_training','tuesday_confirmation_paid_once')",
)

def week_start(day):return day.absolute_day-day.weekday()

def focus_choices(c,start):
    return dict(c.execute('''SELECT p.person_id,p.skill FROM training_choices p JOIN training_sheets s
        USING(game_id,week_start,agency_id) WHERE p.week_start=? AND s.confirmed=1 AND p.skill IS NOT NULL''',(start,)))

def close_tuesday(c,day):
    d=GameDate(day)
    if d.is_founding or d.weekday()!=1:return
    pending=c.execute('''SELECT 1 FROM training_sheets s JOIN training_choices p USING(game_id,week_start,agency_id)
        WHERE s.week_start=? AND s.confirmed=0 AND p.skill IS NOT NULL LIMIT 1''',(week_start(d),)).fetchone()
    if pending:raise ValueError('훈련 탭에서 집중 훈련을 확정하거나 선택을 해제한 뒤 하루를 진행해 주세요.')

def public_trials(results):
    rows=[];final={}
    labels={'second_net':'기본 성장','first_up':'기본 성장','first_down':'기본 성장',
        'first_no_appearance':'기본 성장','trainee_up':'기본 성장','focus':'집중 훈련',
        'additional':'PA 격차 추가 성장','aging':'노화','second_leader':'2군 리더 추가 성장'}
    for result,trials in results:
        values=list(json.loads(result['ca_before_json']));held={};i=0
        while i<len(trials):
            t=trials[i];kind=t['kind'];skill=t.get('skill');prob=t.get('probability');change=t if 'applied' in t else None
            up=down=None;success=t.get('success');prevented=False
            if kind in ('second_up','second_down'):
                held[kind]=t;i+=1;continue
            if kind=='second_leader_roll':i+=1;continue
            if kind=='second_net':
                up=held.get('second_up',{}).get('probability');down=held.get('second_down',{}).get('probability')
                success=f"상승 {'성공' if held.get('second_up',{}).get('success') else '실패'} / 하락 {'성공' if held.get('second_down',{}).get('success') else '실패'}"
                prevented=t.get('down_prevented',False);held={}
            elif prob is not None:
                if kind in ('first_down',):down=prob
                elif kind!='additional':up=prob
                if success and i+1<len(trials) and trials[i+1]['kind']==kind and 'applied' in trials[i+1]:
                    i+=1;change=trials[i];skill=change['skill']
            if kind in labels:
                index=SKILLS.index(skill) if skill in SKILLS else None
                before=values[index] if index is not None else None
                delta=change.get('applied',0) if change else 0
                if index is not None:values[index]+=delta
                rows.append(dict(day=result['absolute_day'],skill=skill,kind=labels[kind],before=before,
                    up=up,down=down,success=success if success is not None else '확정',delta=delta,
                    prevented=prevented,after=values[index] if index is not None else None))
            i+=1
        final=dict(zip(SKILLS,json.loads(result['ca_after_json'])))
    for row in rows:row['final']=final.get(row['skill'])
    return rows

def save_sheet(c,agency,choices,*,confirm=False,expected_revision):
    """Shared player/AI writer; caller owns the transaction."""
    d=current_game_date(c)
    if not d or d.is_founding or d.weekday()!=1 or not(d.is_regular or d.is_postseason):raise ValueError('집중 훈련은 정규·포스트시즌 화요일에만 설정할 수 있습니다.')
    start=week_start(d)
    s=c.execute('SELECT * FROM training_sheets WHERE week_start=? AND agency_id=?',(start,agency)).fetchone()
    if s and s['confirmed']:
        saved=dict(c.execute('SELECT person_id,skill FROM training_choices WHERE week_start=? AND agency_id=? AND skill IS NOT NULL',(start,agency)))
        if saved!={p:v for p,v in choices.items() if v is not None}:raise ValueError('이미 확정한 이번 주 집중 훈련은 변경할 수 없습니다.')
        return
    if expected_revision!=(s['revision'] if s else 0):raise ValueError('훈련 설정이 변경되었습니다. 다시 불러와 주세요.')
    for person,skill in choices.items():
        if skill is not None and skill not in SKILLS:raise ValueError('훈련 능력치를 확인해 주세요.')
        if not c.execute("SELECT 1 FROM roster_memberships WHERE person_id=? AND agency_id=? AND career_status='second_team'",(person,agency)).fetchone():raise ValueError('현재 소속 2군 선수만 집중 훈련할 수 있습니다.')
    total=sum(skill is not None for skill in choices.values())*FOCUS_COST
    if total:FinanceService(None).validate_spend(agency,total,connection=c)
    c.execute('INSERT OR IGNORE INTO training_sheets VALUES (1,?,?,0,0)',(start,agency))
    c.execute('DELETE FROM training_choices WHERE week_start=? AND agency_id=?',(start,agency))
    c.executemany('INSERT INTO training_choices VALUES (1,?,?,?,?)',[(start,agency,p,s) for p,s in choices.items()])
    if confirm and total:
        identity=f'focus:{start}:{agency}'
        settlement=dict(id=identity,agency=agency,day=d.absolute_day,season=d.season,week=d.week)
        if not c.execute('SELECT 1 FROM finance_settlements WHERE id=?',(identity,)).fetchone():
            c.execute("INSERT INTO finance_settlements VALUES (?,1,?,?,?,?, 'market')",(identity,agency,d.season,d.week,d.absolute_day))
            for person,skill in choices.items():
                if skill is not None:journal(c,settlement,'focus_training',FOCUS_COST,cash_delta=-FOCUS_COST,person=person,description='주간 2군 집중 훈련 확정')
    c.execute('UPDATE training_sheets SET confirmed=?,revision=revision+1 WHERE week_start=? AND agency_id=?',(int(confirm),start,agency))

class TrainingService:
    def __init__(self,database):self.database=database

    def state(self,agency):
        with closing(self.database.connect()) as c:
            d=current_game_date(c)
            if not d:return dict(day=None,players=(),confirmed=False,revision=0)
            start=week_start(d)
            sheet=c.execute('SELECT * FROM training_sheets WHERE week_start=? AND agency_id=?',(start,agency)).fetchone()
            choices=dict(c.execute('SELECT person_id,skill FROM training_choices WHERE week_start=? AND agency_id=?',(start,agency)))
            players=[]
            for r in c.execute('''SELECT p.id,p.name,p.photo_path,r.career_status FROM people p JOIN roster_memberships r ON r.person_id=p.id
                WHERE r.agency_id=? AND r.career_status IN ('first_team','second_team') ORDER BY r.career_status,p.name''',(agency,)):
                skills=dict(c.execute('SELECT skill,value FROM abilities WHERE person_id=?',(r['id'],)))
                last=c.execute("SELECT MAX(s.absolute_day) FROM development_results r JOIN development_settlements s ON s.id=r.settlement_id WHERE r.person_id=? AND s.kind IN ('growth','aging')",(r['id'],)).fetchone()[0]
                delta=sum(sum(json.loads(x[0])) for x in c.execute("SELECT r.deltas_json FROM development_results r JOIN development_settlements s ON s.id=r.settlement_id WHERE r.person_id=? AND s.absolute_day=? AND s.kind IN ('growth','aging')",(r['id'],last))) if last is not None else None
                players.append(dict(r,skills=[skills[s] for s in SKILLS],focus=choices.get(r['id']),last_day=last,last_delta=delta))
            return dict(day=d,players=players,confirmed=bool(sheet and sheet['confirmed']),revision=sheet['revision'] if sheet else 0)

    def save(self,agency,choices,*,confirm=False,expected_revision):
        with closing(self.database.connect()) as c,c:
            c.execute('BEGIN IMMEDIATE')
            save_sheet(c,agency,choices,confirm=confirm,expected_revision=expected_revision)
        return self.state(agency)

    def details(self,agency,person):
        with closing(self.database.connect()) as c:
            if not c.execute("SELECT 1 FROM roster_memberships WHERE person_id=? AND agency_id=? AND career_status IN ('first_team','second_team')",(person,agency)).fetchone():raise ValueError('소속 프로 선수의 성장 기록만 볼 수 있습니다.')
            day=c.execute("SELECT MAX(s.absolute_day) FROM development_results r JOIN development_settlements s ON s.id=r.settlement_id WHERE r.person_id=? AND s.kind IN ('growth','aging')",(person,)).fetchone()[0]
            if day is None:return []
            records=[]
            for r in c.execute("SELECT r.*,s.absolute_day FROM development_results r JOIN development_settlements s ON s.id=r.settlement_id WHERE r.person_id=? AND s.absolute_day=? AND s.kind IN ('growth','aging') ORDER BY CASE s.kind WHEN 'growth' THEN 0 ELSE 1 END",(person,day)):
                trials=[json.loads(t[0]) for t in c.execute('SELECT trial_json FROM development_trials WHERE settlement_id=? AND person_id=? ORDER BY ordinal',(r['settlement_id'],person))]
                records.append((r,trials))
            return public_trials(records)
