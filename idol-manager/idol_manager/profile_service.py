from .game_clock import regular_day
"""Read-only, ID-based public analysis. No RNG, PA, or gameplay writes."""
from collections import Counter, defaultdict
from contextlib import closing, contextmanager
import json
from .config import SKILLS
from .game_clock import current_game_date, GameDate, DAYS_PER_SEASON
from .conditions import public_condition
from .condition_rules import fatigue_penalty, registration_multiplier, injury_probability, required_rest_weeks
from .profile_condition import extend_condition


def fraction(successes, attempts):
    return successes/attempts if attempts else None


class ProfileService:
    def __init__(self, database):self.database=database

    def content_statistics(self,person,*,season=None,kind=None):
        from .records_service import RecordsService
        return RecordsService(self.database).content_players(season=season,kind=kind,person=person)

    @contextmanager
    def read(self):
        with closing(self.database.connect()) as c:
            c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
            yield c

    @staticmethod
    def public_ids(c):
        ids={r[0] for r in c.execute('''SELECT person_id FROM professional_history UNION SELECT person_id FROM draft_picks
            UNION SELECT person_id FROM roster_memberships WHERE agency_id IS NOT NULL
            UNION SELECT person_id FROM development_days WHERE agency_id IS NOT NULL
            UNION SELECT person_id FROM match_player_stats UNION SELECT person_id FROM special_player_stats
            UNION SELECT person_id FROM market_draft_rights''')}
        for r in c.execute("SELECT person_id,details_json FROM condition_events WHERE kind='roster'"):
            details=json.loads(r['details_json'])
            if any(details.get(k) in ('first_team','second_team','trainee','pro_pending') for k in ('from','to')):ids.add(r['person_id'])
        return ids

    @staticmethod
    def identities(c):
        return [dict(r) for r in c.execute('''SELECT p.id,p.name,p.photo_path,i.age,i.status,r.agency_id,r.career_status,
            a.name AS agency_name FROM people p JOIN idols i ON i.person_id=p.id
            LEFT JOIN roster_memberships r ON r.person_id=p.id LEFT JOIN agencies a ON a.id=r.agency_id ORDER BY p.name,p.id''')]

    @staticmethod
    def abilities(c, person, exact):
        if exact:
            values={r[0]:r[1] for r in c.execute('SELECT skill,value FROM abilities WHERE person_id=?',(person,))}
            return tuple((values[s],values[s]) if s in values else (None,None) for s in SKILLS)
        estimates={r[0]:(r[1],r[2]) for r in c.execute('SELECT skill,low,high FROM draft_estimates WHERE person_id=?',(person,))}
        return tuple(estimates.get(s,(None,None)) for s in SKILLS)

    def search(self, *, name='', agency=None, role=None, injured=None):
        with self.read() as c:
            public=self.public_ids(c);result=[];day=current_game_date(c)
            injury_days=dict(c.execute('SELECT person_id,injury_day FROM player_conditions'))
            for row in self.identities(c):
                exact=row['id'] in public
                if not exact and row['status']=='unseen' and row['career_status'] not in ('fa','retired'):continue
                status=row['career_status'] if row['career_status'] not in (None,'unassigned') else 'candidate'
                if name.casefold() not in row['name'].casefold() or (agency and row['agency_id']!=agency) or (role and status!=role):continue
                bounds=self.abilities(c,row['id'],exact)
                condition=public_condition(c,row['id'],day.absolute_day) if exact and day else None
                injury_day=injury_days.get(row['id'])
                resting=bool(condition and ((condition.injured and injury_day is not None and injury_day<day.absolute_day-day.weekday()) or
                    (status=='second_team' and condition.return_not_before is not None and day.absolute_day<condition.return_not_before)))
                if injured is not None and (condition is None or bool(condition.injured or resting)!=injured):continue
                health=c.execute('SELECT health FROM idols WHERE person_id=?',(row['id'],)).fetchone()[0] if exact else None
                result.append(dict(row,role=status,exact=exact,bounds=bounds,health=health,
                    average=sum((a+b)/2 for a,b in bounds)/8 if all(a is not None for a,b in bounds) else None,
                    injured=condition.injured if condition else None,injury_rest=resting,streak=condition.streak if condition else None,
                    risk_multiplier=registration_multiplier(condition.registration_weeks) if condition else None,
                    registration_weeks=condition.registration_weeks if condition else None))
            return tuple(result)

    def get(self,person,*,season=None):
        with self.read() as c:
            identity=next((r for r in self.identities(c) if r['id']==person),None)
            if identity is None:raise ValueError('해당 아이돌의 저장 기록을 찾을 수 없습니다.')
            from .franchise import eligible,display_name
            identity['franchise']=person in eligible(c,identity['agency_id']) if identity['agency_id'] else False
            identity['display_name']=display_name(identity['name'],identity['franchise'])
            date=current_game_date(c);season=season or (date.season if date else 1)
            exact=person in self.public_ids(c);bounds=self.abilities(c,person,exact)
            leader=[dict(r) for r in c.execute('SELECT squad FROM squad_leaders WHERE person_id=?',(person,))]
            draft=c.execute('''SELECT t.agency_id,a.name AS agency_name,t.round_number,k.pick_number FROM draft_picks k
                JOIN draft_turns t ON t.pick_number=k.pick_number JOIN agencies a ON a.id=t.agency_id WHERE k.person_id=?''',(person,)).fetchone()
            health=c.execute('SELECT health FROM idols WHERE person_id=?',(person,)).fetchone()[0] if exact else None
            condition=self.condition(c,person,date.absolute_day,season,health) if exact and date else None
            if condition is not None:condition=extend_condition(c,person,date.absolute_day,health,identity['agency_id'],identity['career_status'],condition,bounds)
            matches=self.matches(c,person,season) if exact else ()
            growth=self.growth(c,person,season) if exact else ()
            periods=[tuple(r) for r in c.execute('''SELECT s.period_start,s.period_end,r.role FROM development_results r
                JOIN development_settlements s ON s.id=r.settlement_id WHERE r.person_id=? AND s.kind='growth' ''',(person,))] if exact else []
            for match in matches:
                selected=next((role for start,end,role in periods if start<=match['day']<=end),None)
                match['growth_status']=('excluded' if not match['growth_eligible'] or (selected is not None and selected!='first_team')
                    else 'confirmed' if selected=='first_team' else 'unsettled')
            valid=all(a is not None for a,b in bounds)
            average=(sum(a for a,b in bounds)/8,sum(b for a,b in bounds)/8) if valid else (None,None)
            financial_contract=c.execute('''SELECT x.annual_krw,x.start_day,x.end_day,x.source,t.start_season,t.end_season FROM finance_contracts x LEFT JOIN market_terms t ON t.contract_id=x.id
                WHERE x.person_id=? AND start_day<=? AND (end_day IS NULL OR end_day>?) ORDER BY start_day DESC LIMIT 1''',
                (person,date.absolute_day,date.absolute_day)).fetchone() if exact and date and identity['agency_id'] else None
            from .awards import history
            personal_awards=history(c,person)
            annual_drafts=[dict(r) for r in c.execute('''SELECT t.season,s.target_season,t.round_number,t.pick_number,t.agency_id,t.status,t.contract_kind,t.picked_age
                FROM annual_turns t JOIN annual_sessions s ON s.season=t.season WHERE t.person_id=? ORDER BY t.season''',(person,))]
            debut=c.execute("SELECT absolute_day FROM market_history WHERE person_id=? AND kind='debut' ORDER BY absolute_day,rowid LIMIT 1",(person,)).fetchone()
            trainee_debut_season=GameDate(debut[0]).season if debut else None
            return dict(identity=identity,exact=exact,bounds=bounds,average=average,health=health,leaders=leader,
                annual_drafts=annual_drafts,trainee_debut_season=trainee_debut_season,
                awards=personal_awards,award_totals=dict(Counter(a['award_type'] for a in personal_awards)),
                draft=dict(draft) if draft else None,season=season,date=str(date) if date else '게임 시작 전',
                condition=condition,matches=matches,statistics=self.statistics(matches),growth=growth,
                contract=dict(status='미계약' if not exact else '회계 계약 등록' if financial_contract else '소속·경력 공개 · 계약 세부 기록 없음',
                    start=financial_contract['start_day'] if financial_contract else None,
                    end=financial_contract['end_day'] if financial_contract else None,
                    salary=financial_contract['annual_krw'] if financial_contract else None,
                    start_season=financial_contract['start_season'] if financial_contract else None,
                    end_season=financial_contract['end_season'] if financial_contract else None,
                    market_salary=None,market_value=None,renewed=None),
                seasons=tuple(sorted({season,*[r[0] for r in c.execute('SELECT season FROM season_schedules')]},reverse=True)))

    @staticmethod
    def condition(c,person,day,season,health):
        state=public_condition(c,person,day)
        row=c.execute('SELECT * FROM player_conditions WHERE person_id=?',(person,)).fetchone()
        events=[dict(r) for r in c.execute('''SELECT absolute_day,kind,occurred,details_json FROM condition_events
            WHERE person_id=? AND occurred=1 ORDER BY absolute_day DESC,rowid DESC''',(person,))]
        # Only proven daily registrations and logged transitions are counted.
        start=(season-1)*DAYS_PER_SEASON;end=min(day,season*DAYS_PER_SEASON-1)
        proven={r['absolute_day']:r['role'] for r in c.execute('SELECT absolute_day,role FROM development_days WHERE person_id=? AND absolute_day BETWEEN ? AND ?',(person,start,end))}
        known=row['history_known_since'] if row else day
        for d in range(max(start,known),end+1):
            if d in proven:continue
            role=row['squad'] if row else None
            for e in events:
                if e['kind']=='roster' and e['absolute_day']>d:role=json.loads(e['details_json']).get('from')
            proven[d]=role
        dates=[r[0] for r in c.execute('SELECT absolute_day FROM appearance_days WHERE person_id=? AND absolute_day BETWEEN ? AND ? ORDER BY absolute_day DESC',(person,start,end))]
        moves=[dict(day=e['absolute_day'],**json.loads(e['details_json'])) for e in events if e['kind']=='roster']
        required=required_rest_weeks(state.registration_weeks)
        rest=row['complete_rest_weeks'] if row else 0
        rest_day=None
        if row and row['squad']=='second_team':
            first=(day//7+1)*7
            if row['squad_since']>first-7:first+=7
            rest_day=day if rest>=required or state.registration_weeks==0 else first+max(0,required-rest-1)*7
        injuries=[dict(day=e['absolute_day'],kind=e['kind']) for e in events if e['kind'] in ('match','first_rest','second')]
        return dict(streak=state.streak,projected_days=state.projected_days,last_day=state.last_day,
            current_penalty=fatigue_penalty(state.streak),preview_penalty=state.penalty,
            today_played=bool(c.execute('SELECT 1 FROM appearance_days WHERE person_id=? AND absolute_day=?',(person,day)).fetchone()),
            reset=state.last_day is not None and state.last_day<day-1,registration_weeks=state.registration_weeks,
            multiplier=registration_multiplier(state.registration_weeks),season_registration_weeks=len({d//7 for d,r in proven.items() if r=='first_team'}),
            appearance_weeks=len({d//7 for d in dates}),appearance_dates=dates,known_since=known,moves=moves,
            promotion=next((e['day'] for e in moves if e.get('to')=='first_team'),None),
            demotion=next((e['day'] for e in moves if e.get('to')=='second_team' and e.get('from')=='first_team'),None),
            rest_weeks=rest,required_rest_weeks=required,rest_complete=rest>=required or state.registration_weeks==0,reset_expected=rest_day,
            injured=state.injured,injury_day=row['injury_day'] if row else None,recovery_day=state.recovery_day,
            return_not_before=state.return_not_before,injuries=injuries,
            season_injuries=sum(start<=e['day']<=end for e in injuries),
            probabilities={kind:injury_probability(health,state.registration_weeks,kind) for kind in ('match','first_rest','second')})

    @staticmethod
    def matches(c,person,season):
        names=dict(c.execute('SELECT id,name FROM agencies'));records=[]
        for r in c.execute('''SELECT p.match_id,p.agency_id,p.outcome,m.season,m.week,m.weekday,m.content_name,m.day_order,
            CASE WHEN EXISTS(SELECT 1 FROM award_match_selections s WHERE s.match_id=m.id AND s.kind='winning_idol')
            THEN EXISTS(SELECT 1 FROM award_match_selections s WHERE s.match_id=m.id AND s.kind='winning_idol' AND s.person_id=p.person_id) ELSE p.winning_idol END winning_idol,
            CASE WHEN EXISTS(SELECT 1 FROM award_match_selections s WHERE s.match_id=m.id AND s.kind='losing_idol')
            THEN EXISTS(SELECT 1 FROM award_match_selections s WHERE s.match_id=m.id AND s.kind='losing_idol' AND s.person_id=p.person_id) ELSE p.losing_idol END losing_idol
            FROM match_player_stats p JOIN scheduled_matches m ON m.id=p.match_id WHERE p.person_id=? AND m.season=?''',(person,season)):
            agencies=[a[0] for a in c.execute('SELECT agency_id FROM match_participants WHERE match_id=?',(r['match_id'],))]
            events=[dict(e) for e in c.execute('SELECT phase,skill,success FROM match_events WHERE match_id=? AND person_id=?',(r['match_id'],person))]
            records.append(dict(id=r['match_id'],kind='regular',day_order=r['day_order'],day=regular_day(season,r['week'],r['weekday']),
                content=r['content_name'],agency_id=r['agency_id'],opponents=[names[a] for a in agencies if a!=r['agency_id']],outcome=r['outcome'],events=events,growth_eligible=True,
                winning_idol=bool(r['winning_idol']),losing_idol=bool(r['losing_idol'])))
        for r in c.execute('''SELECT p.round_id,p.agency_id,r.content_name,r.input_json,e.week,e.weekday,t.rank,r.event_id
            FROM special_player_stats p JOIN special_rounds r ON r.id=p.round_id JOIN special_events e ON e.id=r.event_id
            JOIN special_team_results t ON t.round_id=r.id AND t.agency_id=p.agency_id WHERE p.person_id=? AND e.season=?''',(person,season)):
            teams=[a[0] for a in c.execute('SELECT agency_id FROM special_team_results WHERE round_id=?',(r['round_id'],))]
            events=[dict(e) for e in c.execute('SELECT phase,skill,success FROM special_judgments WHERE round_id=? AND person_id=?',(r['round_id'],person))]
            inputs=json.loads(r['input_json'] or '{}');squad=inputs.get('conditions',{}).get('squads',{}).get(person)
            records.append(dict(id=r['round_id'],kind='special',event_id=r['event_id'],day=regular_day(season,r['week'],r['weekday']),content=r['content_name'],
                agency_id=r['agency_id'],opponents=[names[a] for a in teams if a!=r['agency_id']],outcome=f'{r["rank"]}위',events=events,growth_eligible=squad=='first_team'))
        for r in c.execute("SELECT id,kind,absolute_day,content_json,result_json,events_json FROM final_contests WHERE status='completed' AND season=?",(season,)):
            summary=json.loads(r['result_json']);player=next((p for p in summary.get('players',[]) if p['person_id']==person),None)
            if not player:continue
            events=[dict(phase=e['phase'],skill=e['skill'],success=e['success']) for e in json.loads(r['events_json']) if e['person_id']==person]
            content=json.loads(r['content_json']);order=summary.get('order',[]);agency=player['agency_id']
            records.append(dict(id=r['id'],kind='postseason' if r['kind']=='post' else 'tiebreak',day=r['absolute_day'],
                content=content.get('name','기록 없음'),agency_id=agency,opponents=[names[a] for a in order if a!=agency],
                outcome=player.get('outcome',f'{order.index(agency)+1}위' if agency in order else '기록 없음'),events=events,growth_eligible=r['kind']=='post'))
        for record in records:
            events=record.pop('events');counts=defaultdict(lambda:[0,0])
            for e in events:
                counts[(e['phase'],e['skill'])][0]+=1;counts[(e['phase'],e['skill'])][1]+=int(e['success'])
            record['judgments']=[dict(phase=p,skill=s,attempts=n,successes=k) for (p,s),(n,k) in counts.items()]
            record['injured_after']=bool(c.execute('''SELECT 1 FROM condition_events WHERE person_id=? AND occurred=1 AND kind='match'
                AND (json_extract(details_json,'$.match_id') IN (?,?,?) OR json_extract(details_json,'$.contest_id')=?)''',
                (person,record['id'],'special:'+record['id'],'post:'+record['id'],record['id'])).fetchone())
        return tuple(sorted(records,key=lambda r:(r['day'],r.get('day_order',0),r['id']),reverse=True))

    @staticmethod
    def statistics(records):
        counts=defaultdict(lambda:[0,0,0,0]);appearances=Counter();outcomes=Counter();contents=defaultdict(lambda:[0,0])
        for r in records:
            appearances[r['kind']]+=1
            if r['outcome'] in ('win','loss'):outcomes[r['outcome']]+=1
            for e in r['judgments']:
                key=(e['phase'],e['skill']);counts[key][0]+=e['attempts'];counts[key][1]+=e['successes']
                if e['phase'] in ('main','support'):
                    contents[r['content']][0]+=e['attempts'];contents[r['content']][1]+=e['successes']
                    if r['growth_eligible']:
                        status=r.get('growth_status','unsettled')
                        if status=='confirmed':counts[key][2]+=e['attempts']
                        elif status=='unsettled':counts[key][3]+=e['attempts']
        skill_totals=[]
        for skill in SKILLS:
            main=counts.get(('main',skill),(0,0,0,0));support=counts.get(('support',skill),(0,0,0,0))
            n=main[0]+support[0];k=main[1]+support[1]
            skill_totals.append(dict(skill=skill,main_attempts=main[0],random_attempts=support[0],attempts=n,successes=k,failures=n-k,
                growth_attempts=main[2]+support[2],pending_growth_attempts=main[3]+support[3]))
        return dict(appearances=dict(appearances),wins=outcomes['win'],losses=outcomes['loss'],skill_totals=skill_totals,
            abilities=[dict(phase=p,skill=s,attempts=n,successes=k,failures=n-k,growth_attempts=g,pending_growth_attempts=u) for (p,s),(n,k,g,u) in sorted(counts.items())],
            contents=[dict(name=n,attempts=v[0],successes=v[1]) for n,v in sorted(contents.items())])

    @staticmethod
    def growth(c,person,season):
        rows=[]
        for r in c.execute('''SELECT r.settlement_id,s.absolute_day,s.kind,r.role,r.deltas_json,r.reasons_json,r.age_before,r.age_after
            FROM development_results r JOIN development_settlements s ON s.id=r.settlement_id
            WHERE r.person_id=? AND s.absolute_day>=? AND s.absolute_day<?
            AND s.absolute_day>COALESCE((SELECT appeared_day FROM annual_entries WHERE person_id=r.person_id),-1)
            ORDER BY s.absolute_day DESC,s.kind''',
            (person,(season-1)*DAYS_PER_SEASON,season*DAYS_PER_SEASON)):
            # Only applied public changes; never return trial probabilities, rolls or eligibility derived from PA.
            changes=[dict(kind=t[0],skill=t[1],applied=t[2]) for t in c.execute('''SELECT json_extract(trial_json,'$.kind'),
                json_extract(trial_json,'$.skill'),json_extract(trial_json,'$.applied') FROM development_trials
                WHERE settlement_id=? AND person_id=? AND json_extract(trial_json,'$.applied')!=0 ORDER BY ordinal''',(r['settlement_id'],person))]
            rows.append(dict(day=r['absolute_day'],kind=r['kind'],role=r['role'],deltas=json.loads(r['deltas_json']),
                reasons=json.loads(r['reasons_json']),age_before=r['age_before'],age_after=r['age_after'],changes=changes))
        return tuple(rows)
