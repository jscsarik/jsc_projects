from .game_clock import regular_day
"""Additional read-only condition facts; all probabilities reuse engine rules."""
import json
from .game_clock import GameDate,DAYS_PER_SEASON
from .conditions import public_condition,promotion_allowed
from .condition_rules import injury_probability


def extend_condition(c,person,day,health,agency,squad,condition,bounds):
    recent={r[0] for r in c.execute('SELECT absolute_day FROM appearance_days WHERE person_id=? AND absolute_day BETWEEN ? AND ?',(person,max(0,day-8),day))}
    start=day-day%7;known=condition['known_since']
    condition['week_appearance_days']=len([d for d in recent if d>=start])
    condition['recent_calendar']=[dict(day=d,played=d in recent,known=d>=known,closed=d<day) for d in range(max(0,day-6),day+1)]
    injuries=[dict(r) for r in c.execute("SELECT absolute_day,kind,details_json FROM condition_events WHERE person_id=? AND occurred=1 AND kind IN('match','first_rest','second') ORDER BY absolute_day DESC,rowid DESC",(person,))]
    fatigue=any(d>=start and d-1 in recent and d-2 in recent for d in recent)
    injured_week=any(start<=r['absolute_day']<=day for r in injuries)
    current=GameDate(day);active=current.is_regular or current.is_postseason
    condition['weekly_growth']=dict(active=active,three_consecutive_days=fatigue,injury_occurred=injured_week,
        rise_restricted=active and (fatigue or injured_week),conditional_first_team=True)
    condition['base_probabilities']={kind:injury_probability(health,1,kind) for kind in ('match','first_rest','second')}
    condition['today_effective_values']=tuple(a*(1-condition['preview_penalty']) if a is not None else None for a,b in bounds)
    condition['remaining_rest_weeks']=0 if condition['rest_complete'] else max(0,condition['required_rest_weeks']-condition['rest_weeks'])
    snapshots=[]
    for r in c.execute("SELECT details_json FROM condition_events WHERE person_id=?",(person,)):
        value=json.loads(r[0]).get('fatigue',{}).get('registration_weeks')
        if isinstance(value,int):snapshots.append(value)
    condition['recorded_peak_registration_weeks']=max(snapshots) if snapshots else None
    from .finals_service import roster_change_reason
    from .squads import SquadService
    blocked=roster_change_reason(c,agency) if agency else '현재 소속 기획사가 없습니다.'
    if squad=='first_team':reason='현재 이미 1군에 등록되어 있습니다.'
    elif squad!='second_team':reason='현재 2군 프로 선수가 아닙니다.'
    elif condition['injured']:reason='부상 회복 전에는 복귀할 수 없습니다.'
    elif not promotion_allowed(c,person,day):reason='저장된 1군 복귀 제한일 이전입니다.'
    elif person in SquadService._normal_changes_today(c):reason='오늘 이미 1군·2군을 변경했습니다. 같은 월요일 재변경은 불가합니다.'
    else:reason=blocked
    condition['can_return_now']=squad=='second_team' and not reason
    condition['return_reason']=reason or '기존 인원 제한을 지키는 이동·맞교환 절차로 복귀 가능'
    next_days=[]
    if agency and squad=='first_team':
        for r in c.execute('''SELECT m.season,m.week,m.weekday FROM scheduled_matches m JOIN match_participants p ON p.match_id=m.id
            WHERE p.agency_id=? AND m.status!='completed' ''',(agency,)):
            d=regular_day(r['season'],r['week'],r['weekday'])
            if d>=day:next_days.append((d,'정규 경기'))
        for r in c.execute("SELECT absolute_day,agencies_json,kind FROM final_contests WHERE status!='completed' AND absolute_day>=?",(day,)):
            if agency in json.loads(r['agencies_json']):next_days.append((r['absolute_day'],'포스트시즌' if r['kind']=='post' else '동률 결정전(피로 제외)'))
    if agency and squad in ('first_team','second_team'):
        for r in c.execute("SELECT season,week,weekday FROM special_events WHERE status!='completed'"):
            d=regular_day(r['season'],r['week'],r['weekday'])
            if d>=day:next_days.append((d,'특별전(선발 시)'))
    next_match=min(next_days,key=lambda r:r[0]) if next_days else None
    condition['next_match']=None if next_match is None else dict(day=next_match[0],kind=next_match[1],
        penalty=0 if next_match[1].startswith('동률') else public_condition(c,person,next_match[0]).penalty,
        conditional=True)
    for record in condition['injuries']:
        source=next((r for r in injuries if r['absolute_day']==record['day'] and r['kind']==record['kind']),None)
        membership=None;agency_at=None
        if source:
            details=json.loads(source['details_json']);identity=details.get('match_id')
            if source['kind']=='first_rest':membership='first_team'
            elif source['kind']=='second':membership='second_team'
            elif identity and identity.startswith('special:'):
                r=c.execute('SELECT input_json FROM special_rounds WHERE id=?',(identity.removeprefix('special:'),)).fetchone()
                if r:membership=json.loads(r[0])['conditions']['squads'].get(person)
                r=c.execute('SELECT agency_id FROM special_player_stats WHERE round_id=? AND person_id=?',(identity.removeprefix('special:'),person)).fetchone()
                if r:agency_at=r[0]
            elif (identity and identity.startswith('post:')) or details.get('contest_type')=='tie':membership='first_team'
            elif identity:
                r=c.execute('SELECT agency_id FROM match_player_stats WHERE match_id=? AND person_id=?',(identity,person)).fetchone()
                if r:membership='first_team';agency_at=r[0]
        record['squad']=membership;record['agency_id']=agency_at
    return condition
