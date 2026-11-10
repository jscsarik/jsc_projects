from .game_clock import regular_day
"""Persisted coach notices projected from committed game facts only."""
from contextlib import closing
import json
from .game_clock import current_game_date,GameDate

def tasks(c,day,agency):
    out=[]
    def add(text,target,done=False):out.append(dict(text=text,target=target,done=bool(done)))
    draft=c.execute('SELECT status FROM draft_state WHERE id=1').fetchone()
    if not draft or draft[0]!='completed':
        add('창단 드래프트를 완료해 주세요.','draft');return out
    if day.is_founding:
        from .founding import stage_hint
        add(stage_hint(day),'draft' if day.weekday()==0 else 'market:1' if day.weekday()==1 else 'market:5' if day.weekday() in (2,4) else 'schedule' if day.weekday()==6 else 'market:0',day.weekday()==0)
    if not day.is_founding and day.weekday()==0 and (day.is_regular or day.is_postseason):
        growth=c.execute("SELECT 1 FROM development_settlements WHERE absolute_day=? AND kind='growth'",(day.absolute_day,)).fetchone()
        if growth:add('지난주 성장 정산 결과를 확인해 주세요.','growth',True)
        first=c.execute("SELECT COUNT(*) FROM roster_memberships WHERE agency_id=? AND career_status='first_team'",(agency,)).fetchone()[0]
        leaders=c.execute('SELECT COUNT(*) FROM squad_leaders WHERE agency_id=?',(agency,)).fetchone()[0]
        formed=c.execute('SELECT 1 FROM squad_formations WHERE agency_id=?',(agency,)).fetchone()
        add('1군·2군 편성과 두 리더를 확인해 주세요.','squads',formed and first==5 and leaders==2)
    if not day.is_founding and day.weekday()==1 and (day.is_regular or day.is_postseason):
        sheet=c.execute('SELECT confirmed FROM training_sheets WHERE week_start=? AND agency_id=?',(day.absolute_day-1,agency)).fetchone()
        add('2군 집중 훈련을 설정·확정해 주세요.','training',sheet and sheet[0])
    regular=c.execute("SELECT COUNT(*),SUM(status='completed') FROM scheduled_matches WHERE season=? AND week=? AND weekday=?",(day.season,day.week,day.weekday())).fetchone() if day.is_regular else (0,0)
    if regular[0]:add('오늘 정규 경기의 출전 선수를 확인하고 경기를 진행해 주세요.','matches',regular[0]==regular[1])
    special=c.execute("SELECT COUNT(*),SUM(status='completed') FROM special_events WHERE season=? AND week=?",(day.season,day.week)).fetchone() if day.is_regular and day.weekday()==6 else (0,0)
    if special[0]:add('오늘 특별전이 진행됩니다.','specials',special[0]==special[1])
    final=c.execute("SELECT COUNT(*),SUM(status='completed') FROM final_contests WHERE absolute_day=?",(day.absolute_day,)).fetchone()
    if final[0]:add('오늘 동률 결정전·포스트시즌 경기를 확인해 주세요.','finals',final[0]==final[1])
    from .trainee_recruitment import round_info,sheet
    info=round_info(c)
    if day.absolute_day==info['application_day']:
        current=sheet(c,agency)
        add('연습생 신청을 선택해 주세요. 신청 없이 마감할 수도 있습니다.','market:5',current['submitted'] or current['closed'])
    if day.is_offseason and day.week==2:
        annual=c.execute('SELECT status FROM annual_sessions WHERE season=?',(day.season,)).fetchone()
        add('연간 통합 드래프트를 진행해 주세요.','annual',annual and annual[0]=='completed')
    from .market_service import _entry_day
    for purpose,text,target in (('founding','상위 지명자 계약 협상을 완료해 주세요.','market:1'),('fa','FA 계약 및 결원 보충을 확인해 주세요.','market:0'),('renew','비시즌 재계약을 확인해 주세요.','market:3'),('debut','17세 이상 연습생의 프로 데뷔를 검토해 주세요.','market:5')):
        try:_entry_day(c,agency,purpose)
        except ValueError:continue
        if purpose=='founding':
            pending=c.execute("SELECT 1 FROM founding_contracts WHERE agency_id=? AND status='pending'",(agency,)).fetchone()
            add(text,target,not pending)
        elif purpose=='debut':
            if c.execute("SELECT 1 FROM roster_memberships r JOIN idols i ON i.person_id=r.person_id WHERE r.agency_id=? AND r.career_status='trainee' AND i.age>=17",(agency,)).fetchone():add(text,target)
        elif purpose=='renew':add(text,target)
        elif day.is_founding or not(day.is_regular or day.is_postseason):add(text,target)
    if day.weekday()==0 and not(day.is_regular or day.is_postseason) and c.execute("SELECT 1 FROM development_settlements WHERE absolute_day=? AND kind='growth'",(day.absolute_day,)).fetchone():add('직전 활동 주간의 성장 정산 결과를 확인해 주세요.','growth',True)
    if day.is_maintenance or (day.is_preparation and not day.is_founding):add('17세 이상 연습생 데뷔·계약 승계와 개막 선수단을 정리해 주세요.','squads')
    if not out:add('오늘은 별도의 필수 업무가 없습니다.','schedule',True)
    return out

class CoachService:
    def __init__(self,database):self.database=database

    def refresh(self):
        with closing(self.database.connect()) as c,c:
            c.execute('BEGIN IMMEDIATE');day=current_game_date(c)
            player=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
            if not day or not player:return []
            agency=player[0]
            from .coach_schema import initialize_coach
            initialize_coach(c)
            rollout=c.execute('SELECT rollout_day FROM coach_runtime WHERE game_id=1').fetchone()[0]
            def report(key,kind,body,targets,date=day.absolute_day):
                c.execute('INSERT OR IGNORE INTO coach_reports(game_id,report_key,absolute_day,kind,body,targets_json) VALUES (1,?,?,?,?,?)',(key,date,kind,body,json.dumps(targets,ensure_ascii=False)))
            today=tasks(c,day,agency)
            key=f'daily:{day.absolute_day}'
            report(key,'daily','오늘의 업무',today)
            c.execute('UPDATE coach_reports SET targets_json=? WHERE game_id=1 AND report_key=?',(json.dumps(today,ensure_ascii=False),key))
            def event(source,kind,date,body,target):
                if not rollout<=date<=day.absolute_day:return
                if c.execute('INSERT OR IGNORE INTO coach_seen VALUES (1,?)',(source,)).rowcount:
                    key=f'result:{kind}:{date}'
                    report(key,kind,body,[dict(text='결과 확인',target=target,done=True)],date)
                    c.execute('UPDATE coach_reports SET is_read=0 WHERE game_id=1 AND report_key=?',(key,))
            for r in c.execute("SELECT r.match_id,s.season,s.week,s.weekday FROM match_results r JOIN scheduled_matches s ON s.id=r.match_id WHERE regular_day(s.season,s.week,s.weekday) BETWEEN ? AND ?",(rollout,day.absolute_day)).fetchall():
                event('match:'+r[0],'match',regular_day(r[1],r[2],r[3]),'정규 경기 결과가 확정되었습니다.','matches')
            for r in c.execute("SELECT id,season,week FROM special_events WHERE status='completed' AND regular_day(season,week,6) BETWEEN ? AND ?",(rollout,day.absolute_day)).fetchall():
                event('special:'+r[0],'special',regular_day(r[1],r[2],6),'특별전 결과가 확정되었습니다.','specials')
            for r in c.execute("SELECT id,absolute_day FROM final_contests WHERE status='completed' AND absolute_day BETWEEN ? AND ?",(rollout,day.absolute_day)).fetchall():
                event('final:'+r[0],'final',r[1],'동률 결정전·포스트시즌 결과가 확정되었습니다.','finals')
            for r in c.execute("SELECT id,status,COALESCE((SELECT MAX(absolute_day) FROM market_offers WHERE negotiation_id=n.id),started_day) AS result_day FROM market_negotiations n WHERE agency_id=? AND status IN ('accepted','failed')",(agency,)).fetchall():
                event('contract:'+r[0]+':'+r[1],'contract',r[2],'계약·재계약 협상 결과를 확인해 주세요.','market:1')
            for r in c.execute("SELECT w.absolute_day,COALESCE(r.draw_day,w.absolute_day) AS draw FROM trainee_weeks w LEFT JOIN trainee_rounds r ON r.round_key=w.absolute_day WHERE w.status='finalized'").fetchall():
                event('trainee:'+str(r[0]),'trainee',r[1],'연습생 모집 추첨 결과가 발표되었습니다.','market:5')
            count=c.execute('SELECT COUNT(*) FROM draft_picks').fetchone()[0]
            if count:event('initial:'+str(count),'draft',day.absolute_day,'창단 드래프트 지명 결과를 확인해 주세요.','draft')
            for r in c.execute("SELECT season,pick_number,completed_day FROM annual_turns WHERE agency_id=? AND status='signed' AND completed_day IS NOT NULL",(agency,)).fetchall():
                event(f'annual:{r[0]}:{r[1]}','annual',r[2],'통합 드래프트 지명·계약 결과를 확인해 주세요.','annual')
            # Only applied additional-growth entries: no PA, gap or probability reads.
            for s in c.execute("SELECT id,absolute_day FROM development_settlements WHERE kind='growth' AND absolute_day BETWEEN ? AND ?",(rollout,day.absolute_day)).fetchall():
                winner=c.execute("""SELECT p.id,p.name,SUM(MAX(0,COALESCE(json_extract(t.trial_json,'$.applied'),0))) AS gained
                    FROM development_trials t JOIN people p ON p.id=t.person_id JOIN roster_memberships r ON r.person_id=p.id
                    WHERE t.settlement_id=? AND r.agency_id=? AND r.career_status IN ('first_team','second_team','trainee')
                    AND json_extract(t.trial_json,'$.kind')='additional' GROUP BY p.id,p.name HAVING gained>0
                    ORDER BY gained DESC,p.name,p.id LIMIT 1""",(s[0],agency)).fetchone()
                if winner:
                    source='growth:'+s[0]
                    if c.execute('INSERT OR IGNORE INTO coach_seen VALUES (1,?)',(source,)).rowcount:
                        report(source,'growth',winner['name']+' 선수가 이번 주 잠재력 격차 추가 성장에서 가장 좋은 성과를 보였습니다.',[dict(text=winner['name'],target='profile:'+winner['id'],done=True)],s[1])
            # Keep the archive intact; the coach conversation is today's task list.
            return [dict(r,targets=json.loads(r['targets_json'])) for r in c.execute("SELECT * FROM coach_reports WHERE game_id=1 AND absolute_day=? AND kind='daily' ORDER BY report_key",(day.absolute_day,))]

    def read(self,key=None):
        with closing(self.database.connect()) as c,c:
            if key is None:c.execute('UPDATE coach_reports SET is_read=1 WHERE game_id=1')
            else:c.execute('UPDATE coach_reports SET is_read=1 WHERE game_id=1 AND report_key=?',(key,))

    def announcements(self,day=None):
        with closing(self.database.connect()) as c:
            if day is None:
                day=current_game_date(c)
            player=c.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
            if not day or not player:
                return []
            agency=player[0]
            return announcements(c,day,agency)


def announcements(c,day,agency):
    items=[]
    # 1. 성장/정산 결과
    growth=c.execute("SELECT id,absolute_day FROM development_settlements WHERE kind='growth' AND absolute_day<=? ORDER BY absolute_day DESC LIMIT 1",(day.absolute_day,)).fetchone()
    if growth and (day.absolute_day-growth[1])<=7:
        sid=growth[0]
        winner=c.execute("""SELECT p.name,SUM(MAX(0,COALESCE(json_extract(t.trial_json,'$.applied'),0))) AS gained
            FROM development_trials t JOIN people p ON p.id=t.person_id JOIN roster_memberships r ON r.person_id=p.id
            WHERE t.settlement_id=? AND r.agency_id=? AND r.career_status IN ('first_team','second_team','trainee')
            AND json_extract(t.trial_json,'$.kind')='additional' GROUP BY p.id,p.name HAVING gained>0
            ORDER BY gained DESC,p.name,p.id LIMIT 1""",(sid,agency)).fetchone()
        if winner:items.append(f"잠재력 추가 성장 주목: {winner['name']}")
        rows=c.execute("SELECT role,deltas_json FROM development_results WHERE settlement_id=? AND agency_id=?",(sid,agency)).fetchall()
        counts={'first_team':0,'second_team':0,'trainee':0}
        for r in rows:
            try:
                deltas=json.loads(r['deltas_json']) if r['deltas_json'] else []
                if sum(deltas)>0 and r['role'] in counts:counts[r['role']]+=1
            except Exception:pass
        if sum(counts.values())>0:
            subs=[]
            if counts['first_team']:subs.append(f"1군 {counts['first_team']}명")
            if counts['second_team']:subs.append(f"2군 {counts['second_team']}명")
            if counts['trainee']:subs.append(f"연습생 {counts['trainee']}명")
            items.append(f"주간 성장 완료: {', '.join(subs)} 상승")

    # 2. 경기 결과 요약
    recent_matches=c.execute("""SELECT mp.match_id,
               ts_our.total_score AS our_score, ts_opp.total_score AS opp_score,
               opp_a.name AS opp_name, ts_our.outcome AS outcome,
               regular_day(mp.season,mp.week,mp.weekday) AS match_day
        FROM match_participants mp
        JOIN match_results mr ON mr.match_id=mp.match_id
        JOIN match_team_stats ts_our ON ts_our.match_id=mp.match_id AND ts_our.agency_id=mp.agency_id
        JOIN match_team_stats ts_opp ON ts_opp.match_id=mp.match_id AND ts_opp.agency_id!=mp.agency_id
        JOIN agencies opp_a ON opp_a.id=ts_opp.agency_id
        WHERE mp.agency_id=? AND regular_day(mp.season,mp.week,mp.weekday)<=?
        ORDER BY mp.season DESC,mp.week DESC,mp.weekday DESC,mp.day_order DESC
        LIMIT 4""",(agency,day.absolute_day)).fetchall()
    if recent_matches and (day.absolute_day-recent_matches[0]['match_day'])<=3:
        latest_day=recent_matches[0]['match_day']
        day_matches=[m for m in recent_matches if m['match_day']==latest_day]
        if len(day_matches)==1:
            m=day_matches[0]
            our_s=m['our_score']
            opp_s=m['opp_score']
            opp_n=m['opp_name']
            res_str="승리" if our_s>opp_s else ("패배" if our_s<opp_s else "무승부")
            items.append(f"전날 경기 결과: {opp_n}전 {res_str} ({our_s}:{opp_s})")
        else:
            wins=sum(1 for m in day_matches if m['our_score']>m['opp_score'])
            losses=sum(1 for m in day_matches if m['our_score']<m['opp_score'])
            items.append(f"전날 경기 결과: {wins}승 {losses}패")

    # 3. 특별전 결과 요약
    recent_special=c.execute("""SELECT e.id,e.season,e.week,e.event_type,regular_day(e.season,e.week,6) AS special_day
        FROM special_events e WHERE e.status='completed' AND regular_day(e.season,e.week,6)<=?
        ORDER BY e.season DESC,e.week DESC LIMIT 1""",(day.absolute_day,)).fetchone()
    if recent_special and (day.absolute_day-recent_special['special_day'])<=7:
        theme_names={'festival':'대학축제','kpop':'K-POP 페스티벌','sports':'아이돌 체육대회'}
        theme_n=theme_names.get(recent_special['event_type'],'특별전')
        pts=c.execute("SELECT SUM(delta) FROM special_points WHERE event_id=? AND agency_id=?",(recent_special['id'],agency)).fetchone()
        if pts and pts[0] is not None:
            pts_val=pts[0]
            pts_str=f"+{pts_val}" if pts_val>0 else str(pts_val)
            items.append(f"특별전 결과: {theme_n} (승점 {pts_str}점)")

    # 4. 포스트시즌 / 동률 결정전 결과
    recent_final=c.execute("""SELECT id,kind,round_number,game_number,result_json,absolute_day FROM final_contests
        WHERE status='completed' AND absolute_day<=?
        ORDER BY absolute_day DESC LIMIT 1""",(day.absolute_day,)).fetchone()
    if recent_final and (day.absolute_day-recent_final['absolute_day'])<=7:
        try:
            res_d=json.loads(recent_final['result_json']) if recent_final['result_json'] else {}
            teams=res_d.get('teams',[])
            our_t=next((t for t in teams if t.get('agency_id')==agency),None)
            if our_t:
                opp_t=next((t for t in teams if t.get('agency_id')!=agency),None)
                round_names={1:'준플레이오프',2:'플레이오프',3:'한국시리즈'}
                if recent_final['kind']=='tie':title_name='순위 동률 결정전'
                else:
                    r_name=round_names.get(recent_final['round_number'],'포스트시즌')
                    title_name=f"{r_name} {recent_final['game_number']}차전"
                if opp_t:
                    is_win=our_t.get('total_score',0)>opp_t.get('total_score',0)
                    items.append(f"포스트시즌 결과: {title_name} {'승리' if is_win else '패배'}")
        except Exception:pass

    # 5. 부상 발생
    injuries=c.execute("""SELECT p.name FROM condition_events e
        JOIN people p ON p.id=e.person_id JOIN roster_memberships r ON r.person_id=e.person_id
        WHERE r.agency_id=? AND e.occurred=1 AND e.kind IN ('match','first_rest','second')
          AND e.absolute_day BETWEEN ? AND ? ORDER BY e.absolute_day DESC LIMIT 2""",(agency,max(0,day.absolute_day-3),day.absolute_day)).fetchall()
    for inj in injuries:items.append(f"부상 발생: {inj[0]}")

    # 6. 계약 체결
    contracts=c.execute("""SELECT p.name FROM market_negotiations n
        JOIN people p ON p.id=n.person_id WHERE n.agency_id=? AND n.status='accepted'
          AND n.started_day BETWEEN ? AND ? ORDER BY n.started_day DESC LIMIT 2""",(agency,max(0,day.absolute_day-3),day.absolute_day)).fetchall()
    for con in contracts:items.append(f"계약 체결: {con[0]} 영입 완료")

    return items[:6]
