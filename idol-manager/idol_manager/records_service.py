from .game_clock import regular_day
"""Read-only history over persisted facts. No gameplay calls, writes or RNG.

Appearances: player summary primary keys. Judgments: SQL-grouped saved events.
Never add event totals to summaries; summaries are a fallback if events are absent.
Finals JSON is expanded by SQLite, not replayed by an engine.
"""
from collections import Counter,defaultdict
from contextlib import closing,contextmanager
import json
from .config import SKILLS
from .profile_service import ProfileService
from .game_clock import current_game_date
from .season_schedule import load_schedule_rules

KINDS=('regular','special','postseason','tiebreak')
def rate(k,n):return k/n if n else None
def decode(value,default):return json.loads(value) if value else default

FACTS='''WITH appearances AS (
 SELECT 'regular' kind,m.season,m.id match_id,regular_day(m.season,m.week,m.weekday) day,
 m.content_id,m.content_name,p.person_id,p.agency_id,p.outcome,
 CASE WHEN EXISTS(SELECT 1 FROM award_match_selections s WHERE s.match_id=m.id AND s.kind='winning_idol')
 THEN EXISTS(SELECT 1 FROM award_match_selections s WHERE s.match_id=m.id AND s.kind='winning_idol' AND s.person_id=p.person_id) ELSE p.winning_idol END winning_idol,
 CASE WHEN EXISTS(SELECT 1 FROM award_match_selections s WHERE s.match_id=m.id AND s.kind='losing_idol')
 THEN EXISTS(SELECT 1 FROM award_match_selections s WHERE s.match_id=m.id AND s.kind='losing_idol' AND s.person_id=p.person_id) ELSE p.losing_idol END losing_idol,
 p.base_attempts,p.base_successes,p.leader_attempts,p.leader_successes,p.deathmatch_attempts,p.deathmatch_successes
 FROM match_player_stats p JOIN scheduled_matches m ON m.id=p.match_id JOIN match_results r ON r.match_id=m.id WHERE m.status='completed'
 UNION ALL
 SELECT 'special',e.season,r.id,regular_day(e.season,e.week,e.weekday),r.content_id,r.content_name,
 p.person_id,p.agency_id,NULL,0,0,p.base_attempts,p.base_successes,p.leader_attempts,p.leader_successes,p.deathmatch_attempts,p.deathmatch_successes
 FROM special_player_stats p JOIN special_rounds r ON r.id=p.round_id JOIN special_events e ON e.id=r.event_id WHERE r.status='completed'
 UNION ALL
 SELECT CASE f.kind WHEN 'post' THEN 'postseason' ELSE 'tiebreak' END,f.season,f.id,f.absolute_day,
 COALESCE(json_extract(f.content_json,'$.id'),json_extract(p.value,'$.content_id'),'unknown'),json_extract(f.content_json,'$.name'),
 json_extract(p.value,'$.person_id'),json_extract(p.value,'$.agency_id'),json_extract(p.value,'$.outcome'),0,0,
 json_extract(p.value,'$.base_attempts'),json_extract(p.value,'$.base_successes'),
 COALESCE(json_extract(p.value,'$.leader_attempts'),0),COALESCE(json_extract(p.value,'$.leader_successes'),0),
 COALESCE(json_extract(p.value,'$.deathmatch_attempts'),0),COALESCE(json_extract(p.value,'$.deathmatch_successes'),0)
 FROM final_contests f,json_each(f.result_json,'$.players') p WHERE f.status='completed'
), raw_regular AS MATERIALIZED (
 SELECT 'regular' kind,e.match_id,e.person_id,e.phase,e.skill,COUNT(*) attempts,SUM(e.success) successes
 FROM chosen x JOIN match_events e ON x.kind='regular' AND x.match_id=e.match_id AND x.person_id=e.person_id
 GROUP BY e.match_id,e.person_id,e.phase,e.skill
), raw_special AS MATERIALIZED (
 SELECT 'special' kind,e.round_id match_id,e.person_id,e.phase,e.skill,COUNT(*) attempts,SUM(e.success) successes
 FROM chosen x JOIN special_judgments e ON x.kind='special' AND x.match_id=e.round_id AND x.person_id=e.person_id
 GROUP BY e.round_id,e.person_id,e.phase,e.skill
), judgments AS (
 SELECT * FROM raw_regular
 UNION ALL
 SELECT 'regular',a.match_id,a.person_id,a.phase,a.skill,a.attempts,a.successes FROM chosen x
 JOIN match_ability_stats a ON x.kind='regular' AND x.match_id=a.match_id AND x.person_id=a.person_id
 WHERE NOT EXISTS(SELECT 1 FROM raw_regular e WHERE e.match_id=a.match_id AND e.person_id=a.person_id)
 UNION ALL
 SELECT * FROM raw_special
 UNION ALL
 SELECT 'special',a.round_id,a.person_id,a.phase,a.skill,a.attempts,a.successes FROM chosen x
 JOIN special_ability_stats a ON x.kind='special' AND x.match_id=a.round_id AND x.person_id=a.person_id
 WHERE NOT EXISTS(SELECT 1 FROM raw_special e WHERE e.match_id=a.round_id AND e.person_id=a.person_id)
 UNION ALL
 SELECT CASE f.kind WHEN 'post' THEN 'postseason' ELSE 'tiebreak' END,f.id,json_extract(e.value,'$.person_id'),
 json_extract(e.value,'$.phase'),json_extract(e.value,'$.skill'),COUNT(*),SUM(json_extract(e.value,'$.success'))
 FROM final_contests f,json_each(f.events_json) e WHERE f.status='completed'
 AND EXISTS(SELECT 1 FROM chosen x WHERE x.match_id=f.id AND x.kind=CASE f.kind WHEN 'post' THEN 'postseason' ELSE 'tiebreak' END)
 GROUP BY f.id,json_extract(e.value,'$.person_id'),json_extract(e.value,'$.phase'),json_extract(e.value,'$.skill')
), chosen AS (
 SELECT * FROM appearances WHERE (:season IS NULL OR season=:season) AND (:kind IS NULL OR kind=:kind)
 AND (:agency IS NULL OR agency_id=:agency) AND (:person IS NULL OR person_id=:person)
 AND (:people IS NULL OR person_id IN (SELECT value FROM json_each(:people)))
), counts AS (
 SELECT j.kind,j.match_id,j.person_id,SUM(j.attempts) event_count,
 SUM(CASE WHEN phase IN('main','support') THEN attempts ELSE 0 END) n,
 SUM(CASE WHEN phase IN('main','support') THEN successes ELSE 0 END) k,
 SUM(CASE WHEN phase='main' THEN attempts END) mn,SUM(CASE WHEN phase='main' THEN successes END) mk,
 SUM(CASE WHEN phase='support' THEN attempts END) sn,SUM(CASE WHEN phase='support' THEN successes END) sk,
 SUM(CASE WHEN phase='leader' THEN attempts END) ln,SUM(CASE WHEN phase='leader' THEN successes END) lk,
 SUM(CASE WHEN phase='deathmatch' THEN attempts END) dn,SUM(CASE WHEN phase='deathmatch' THEN successes END) dk
 FROM judgments j JOIN chosen a ON a.kind=j.kind AND a.match_id=j.match_id AND a.person_id=j.person_id
 GROUP BY j.kind,j.match_id,j.person_id
), facts AS (
 SELECT a.*,COALESCE(c.n,a.base_attempts,0) n,COALESCE(c.k,a.base_successes,0) k,
 c.mn,c.mk,c.sn,c.sk,
 COALESCE(c.ln,a.leader_attempts,0) ln,COALESCE(c.lk,a.leader_successes,0) lk,
 COALESCE(c.dn,a.deathmatch_attempts,0) dn,COALESCE(c.dk,a.deathmatch_successes,0) dk,
 CASE WHEN c.event_count IS NULL OR a.base_attempts IS NULL OR c.n!=a.base_attempts THEN 1 ELSE 0 END partial
 FROM chosen a LEFT JOIN counts c ON c.kind=a.kind AND c.match_id=a.match_id AND c.person_id=a.person_id
) '''


class RecordsService:
    def __init__(self,database):self.database=database
    def player_choices(self):
        with self.read() as c:
            public=ProfileService.public_ids(c)
            return [p for p in ProfileService.identities(c) if p['status']!='unseen' or p['id'] in public or p['career_status'] in ('fa','retired')]

    @contextmanager
    def read(self):
        with closing(self.database.connect()) as c:
            from .records_read import attach_cancellation
            attach_cancellation(c)
            c.execute('PRAGMA query_only=ON');c.execute('BEGIN');yield c

    @staticmethod
    def params(season=None,kind='regular',agency=None,person=None):
        if kind not in (*KINDS,None):raise ValueError('지원하지 않는 경기 구간입니다.')
        return dict(season=season,kind=kind,agency=agency,person=person,people=None)

    def seasons(self):
        with self.read() as c:
            day=current_game_date(c)
            return sorted({day.season if day else 1,*[r[0] for r in c.execute('SELECT season FROM season_schedules UNION SELECT season FROM season_finals UNION SELECT season FROM season_awards UNION SELECT season FROM season_honors')]},reverse=True)

    @staticmethod
    def _totals(c,params,groups='person_id'):
        return [dict(r) for r in c.execute(FACTS+f'''SELECT {groups},COUNT(*) appearances,
            SUM(kind='regular') regular_appearances,SUM(outcome='win') wins,SUM(outcome='loss') losses,
            SUM(kind='special') special_appearances,SUM(kind='postseason') postseason_appearances,SUM(kind='tiebreak') tiebreak_appearances,
            SUM(winning_idol) winning_idol,SUM(losing_idol) losing_idol,
            SUM(n) attempts,SUM(k) successes,SUM(ln) leader_attempts,SUM(lk) leader_successes,
            CASE WHEN COUNT(mn)=COUNT(*) THEN SUM(mn) END main_attempts,CASE WHEN COUNT(mk)=COUNT(*) THEN SUM(mk) END main_successes,
            CASE WHEN COUNT(sn)=COUNT(*) THEN SUM(sn) END support_attempts,CASE WHEN COUNT(sk)=COUNT(*) THEN SUM(sk) END support_successes,
            SUM(dn) deathmatch_attempts,SUM(dk) deathmatch_successes,SUM(partial) partial
            FROM facts GROUP BY {groups}''',params)]

    @staticmethod
    def _abilities(c,params):
        return [dict(r) for r in c.execute(FACTS+'''SELECT a.person_id,j.phase,j.skill,SUM(j.attempts) attempts,SUM(j.successes) successes
            FROM chosen a JOIN judgments j ON j.kind=a.kind AND j.match_id=a.match_id AND j.person_id=a.person_id
            GROUP BY a.person_id,j.phase,j.skill''',params)]

    @staticmethod
    def _player_facts(c,params):
        # Both consumers share one materialized judgments CTE in one statement.
        totals='''SELECT person_id,COUNT(*) appearances,SUM(kind='regular') regular_appearances,
            SUM(outcome='win') wins,SUM(outcome='loss') losses,SUM(kind='special') special_appearances,
            SUM(kind='postseason') postseason_appearances,SUM(kind='tiebreak') tiebreak_appearances,
            SUM(winning_idol) winning_idol,SUM(losing_idol) losing_idol,SUM(n) attempts,SUM(k) successes,
            SUM(ln) leader_attempts,SUM(lk) leader_successes,
            CASE WHEN COUNT(mn)=COUNT(*) THEN SUM(mn) END main_attempts,
            CASE WHEN COUNT(mk)=COUNT(*) THEN SUM(mk) END main_successes,
            CASE WHEN COUNT(sn)=COUNT(*) THEN SUM(sn) END support_attempts,
            CASE WHEN COUNT(sk)=COUNT(*) THEN SUM(sk) END support_successes,
            SUM(dn) deathmatch_attempts,SUM(dk) deathmatch_successes,SUM(partial) partial FROM facts GROUP BY person_id'''
        columns=('person_id','appearances','regular_appearances','wins','losses','special_appearances','postseason_appearances','tiebreak_appearances','winning_idol','losing_idol','attempts','successes','leader_attempts','leader_successes','main_attempts','main_successes','support_attempts','support_successes','deathmatch_attempts','deathmatch_successes','partial')
        payload=','.join("'"+k+"',"+k for k in columns)
        sql=FACTS+''', pt AS ('''+totals+'''), ps AS (
            SELECT a.person_id,j.phase,j.skill,SUM(j.attempts) attempts,SUM(j.successes) successes
            FROM chosen a JOIN judgments j ON j.kind=a.kind AND j.match_id=a.match_id AND j.person_id=a.person_id
            GROUP BY a.person_id,j.phase,j.skill)
            SELECT 'total',json_object('''+payload+''') FROM pt UNION ALL
            SELECT 'skill',json_object('person_id',person_id,'phase',phase,'skill',skill,'attempts',attempts,'successes',successes) FROM ps'''
        rows=c.execute(sql,params).fetchall()
        return ([json.loads(r[1]) for r in rows if r[0]=='total'],[json.loads(r[1]) for r in rows if r[0]=='skill'])

    def players(self,*,season=None,kind='regular',agency=None,name='',minimum=0,role=None,person_ids=None):
        params=self.params(season,kind,agency)
        if person_ids is not None:params['people']=json.dumps(list(person_ids))
        with self.read() as c:
            public=ProfileService.public_ids(c)
            total_rows,skill_rows=self._player_facts(c,params)
            totals={r['person_id']:r for r in total_rows}
            skills=defaultdict(lambda:defaultdict(lambda:[0,0]))
            for r in skill_rows:
                if r['phase'] in ('main','support'):
                    v=skills[r['person_id']][r['skill']];v[0]+=r['attempts'];v[1]+=r['successes']
            awards=Counter(r[0] for r in c.execute('''SELECT person_id FROM individual_awards WHERE (? IS NULL OR season=?)
                AND (? IS NULL OR awarded_agency_id=?)''',(season,season,agency,agency)))
            debut=dict(c.execute('SELECT person_id,debut_season FROM market_careers'))
            founders={r[0] for r in c.execute('SELECT person_id FROM draft_picks')}
            result=[]
            for p in ProfileService.identities(c):
                if person_ids is not None and p['id'] not in person_ids:continue
                if p['status']=='unseen' and p['id'] not in public and p['career_status'] not in ('fa','retired'):continue
                if name.casefold() not in p['name'].casefold() or (role and p['career_status']!=role):continue
                t=totals.get(p['id'])
                if agency and not t and p['agency_id']!=agency:continue
                t=t or dict(appearances=0,regular_appearances=0,special_appearances=0,postseason_appearances=0,tiebreak_appearances=0,wins=0,losses=0,winning_idol=0,losing_idol=0,attempts=0,successes=0,main_attempts=0,main_successes=0,support_attempts=0,support_successes=0,leader_attempts=0,leader_successes=0,deathmatch_attempts=0,deathmatch_successes=0,partial=0)
                if t['attempts']<minimum:continue
                s={skill:dict(attempts=skills[p['id']][skill][0],successes=skills[p['id']][skill][1],failures=skills[p['id']][skill][0]-skills[p['id']][skill][1],rate=rate(skills[p['id']][skill][1],skills[p['id']][skill][0])) for skill in SKILLS}
                result.append(dict(p,**{k:v for k,v in t.items() if k!='person_id'},rate=rate(t['successes'],t['attempts']),skills=s,
                    awards=awards[p['id']],debut=debut.get(p['id']) or (1 if p['id'] in founders else None)))
            return result

    def content_players(self,*,season=None,kind='regular',agency=None,person=None):
        with self.read() as c:
            rows=self._totals(c,self.params(season,kind,agency,person),'person_id,kind,content_id,content_name')
            for r in rows:r['rate']=rate(r['successes'],r['attempts'])
            return rows

    def player_seasons(self,person,*,kind='regular'):
        """Year/team rows, optional year subtotals, and one weighted career row."""
        params=self.params(None,kind,None,person)
        with self.read() as c:
            if person not in ProfileService.public_ids(c):return []
            names=dict(c.execute('SELECT id,name FROM agencies'))
            rows=self._totals(c,params,'season,agency_id')
            years={r['season'] for r in rows}
            # Only dates with historical membership evidence, never today's team.
            roles=defaultdict(set)
            for r in c.execute('SELECT absolute_day,agency_id,role FROM development_days WHERE person_id=?',(person,)):
                year=r['absolute_day']//224+1;years.add(year);roles[(year,r['agency_id'])].add(r['role'])
            for year,agency in roles:
                if not any(r['season']==year and r['agency_id']==agency for r in rows):
                    rows.append(dict(season=year,agency_id=agency,appearances=0,wins=0,losses=0,winning_idol=0,losing_idol=0,
                        attempts=0,successes=0,main_attempts=0,main_successes=0,support_attempts=0,support_successes=0,
                        leader_attempts=0,leader_successes=0,deathmatch_attempts=0,deathmatch_successes=0,partial=0))
            result=[]
            numeric=('appearances','wins','losses','winning_idol','losing_idol','attempts','successes','main_attempts','main_successes','support_attempts','support_successes','leader_attempts','leader_successes','deathmatch_attempts','deathmatch_successes','partial')
            for year in sorted(years):
                entries=sorted((r for r in rows if r['season']==year),key=lambda r:r['agency_id'] or '')
                for r in entries:
                    r.update(label=f'시즌 {year}',team=names.get(r['agency_id'],'기록 없음'),row_type='team',roles=sorted(roles.get((year,r['agency_id']),set())),rate=rate(r['successes'],r['attempts']))
                    result.append(r)
                if len(entries)>1:
                    subtotal={k:sum(r[k] or 0 for r in entries) if all(r.get(k) is not None for r in entries) else None for k in numeric}
                    subtotal.update(season=year,label=f'시즌 {year} 합계',team='전체 소속',row_type='subtotal',roles=[],rate=rate(subtotal['successes'],subtotal['attempts']))
                    result.append(subtotal)
            total=self._totals(c,params)
            if total:
                total=total[0];total.update(label=f'통산 ({len(years)}시즌)',team='전체 소속',row_type='career',roles=[],rate=rate(total['successes'],total['attempts']))
                result.append(total)
            elif years:
                total={k:0 for k in numeric};total.update(label=f'통산 ({len(years)}시즌)',team='전체 소속',row_type='career',roles=[],rate=None);result.append(total)
            return result

    def content_catalog(self):
        # Only static design catalog, never future fixture assignments.
        return [dict(id=v.id,name=v.name,main=v.main_abilities,minimum=v.participants_min,maximum=v.participants_max) for v in load_schedule_rules().contents]

    def contents(self,*,season=None,kind='regular',agency=None):
        self.params(season,kind,agency)
        with self.read() as c:
            # Team rows also include forfeits, which have no player appearances.
            team_sql='''SELECT 'regular' kind,m.season,m.id match_id,m.content_id,m.content_name,t.agency_id,t.outcome
                FROM match_team_stats t JOIN scheduled_matches m ON m.id=t.match_id WHERE m.status='completed'
                UNION ALL SELECT 'special',e.season,r.id,r.content_id,r.content_name,t.agency_id,NULL FROM special_team_results t
                JOIN special_rounds r ON r.id=t.round_id JOIN special_events e ON e.id=r.event_id WHERE r.status='completed'
                UNION ALL SELECT CASE f.kind WHEN 'post' THEN 'postseason' ELSE 'tiebreak' END,f.season,f.id,
                COALESCE(json_extract(f.content_json,'$.id'),'unknown'),json_extract(f.content_json,'$.name'),json_extract(t.value,'$.agency_id'),json_extract(t.value,'$.outcome')
                FROM final_contests f,json_each(f.result_json,'$.teams') t WHERE f.status='completed' '''
            rows=[dict(r) for r in c.execute('WITH teams AS ('+team_sql+''') SELECT kind,content_id,content_name,COUNT(DISTINCT match_id) played,
                SUM(outcome='win') wins,SUM(outcome='loss') losses FROM teams WHERE (:season IS NULL OR season=:season)
                AND (:kind IS NULL OR kind=:kind) AND (:agency IS NULL OR agency_id=:agency) GROUP BY kind,content_id,content_name''',self.params(season,kind,agency))]
            lifetime={}
            for r in c.execute('WITH teams AS ('+team_sql+''') SELECT kind,content_id,COUNT(DISTINCT match_id) played FROM teams
                WHERE (:kind IS NULL OR kind=:kind) AND (:agency IS NULL OR agency_id=:agency) GROUP BY kind,content_id''',self.params(None,kind,agency)):lifetime[(r['kind'],r['content_id'])]=r['played']
            totals=self._totals(c,self.params(season,kind,agency),'kind,content_id,content_name')
            ts={(r['kind'],r['content_id']):r for r in totals}
            for r in rows:
                r.update({k:v for k,v in ts.get((r['kind'],r['content_id']),{}).items() if k in ('appearances','attempts','successes','main_successes','support_successes','leader_attempts','leader_successes','deathmatch_attempts','deathmatch_successes','partial')})
                for key in ('attempts','successes','appearances','main_successes','support_successes'):r.setdefault(key,0)
                r['lifetime_played']=lifetime[(r['kind'],r['content_id'])];r['rate']=rate(r['successes'],r['attempts'])
                r['win_rate']=rate(r['wins'] or 0,(r['wins'] or 0)+(r['losses'] or 0))
            if kind=='regular':
                present={r['content_id'] for r in rows}
                for v in self.content_catalog():
                    if v['id'] not in present:rows.append(dict(kind='regular',content_id=v['id'],content_name=v['name'],played=0,wins=0,losses=0,attempts=0,successes=0,main_successes=0,support_successes=0,appearances=0,lifetime_played=lifetime.get(('regular',v['id']),0),rate=None,win_rate=None))
            return rows

    @staticmethod
    def _league(c,season):
        from .league import standings
        saved=c.execute('SELECT * FROM season_finals WHERE season=?',(season,)).fetchone()
        order=decode(saved['final_order_json'],[]) if saved else []
        frozen=decode(saved['standings_json'],[]) if saved and order else []
        source={r['agency_id']:r for r in (frozen or standings(c,season))}
        champion=saved['champion_id'] if saved else None
        if not champion:
            a=c.execute('SELECT champion FROM season_awards WHERE season=?',(season,)).fetchone();champion=a[0] if a else None
        honors=[dict(r) for r in c.execute('SELECT agency_id,kind FROM season_honors WHERE season=?',(season,))]
        if not champion:champion=next((r['agency_id'] for r in honors if r['kind']=='champion'),None)
        first=next((r['agency_id'] for r in honors if r['kind']=='regular_first'),None)
        qualified={r['agency_id'] for r in honors if r['kind']=='qualification'}
        logos=dict(c.execute('SELECT id,logo_path FROM agencies'));names=dict(c.execute('SELECT id,name FROM agencies'))
        penalties=dict(c.execute('SELECT agency_id,SUM(delta) FROM finance_points WHERE season=? GROUP BY agency_id',(season,)))
        rows=[]
        for agency in (order or sorted(names,key=lambda a:(-source.get(a,{}).get('points',0),a))):
            r=dict(source.get(agency,{}));r.update(agency_id=agency,name=names[agency],logo_path=logos[agency],season=season,
                rank=order.index(agency)+1 if agency in order else 1 if agency==first else None,champion=agency==champion,qualified=agency in order[:4] if order else True if agency in qualified else None)
            for k in ('played','wins','losses','regular_points','special_points','points'):r.setdefault(k,0)
            r['penalty']=r['points']-r['regular_points']-r['special_points'] if frozen else penalties.get(agency,0)
            r['win_rate']=rate(r['wins'],r['played']);rows.append(r)
        return rows

    def league(self,season):
        with self.read() as c:return self._league(c,season)

    def champions(self,season=None):
        with self.read() as c:
            rows=[];counts=Counter()
            years=[r[0] for r in c.execute('SELECT season FROM season_finals UNION SELECT season FROM season_awards UNION SELECT season FROM season_honors ORDER BY season')]
            for year in years:
                league=self._league(c,year);winner=next((r for r in league if r['champion']),None)
                if not winner:continue
                counts[winner['agency_id']]+=1
                series=[dict(r) for r in c.execute('SELECT * FROM final_series WHERE season=? ORDER BY round_number',(year,))]
                for s in series:
                    wins=Counter(decode(r[0],{}).get('order',[None])[0] for r in c.execute("SELECT result_json FROM final_contests WHERE season=? AND kind='post' AND round_number=? AND status='completed'",(year,s['round_number'])))
                    s['wins_a']=wins[s['agency_a']] if wins else None;s['wins_b']=wins[s['agency_b']] if wins else None
                if season is None or year==season:rows.append(dict(winner,cumulative=counts[winner['agency_id']],series=series))
            return rows

    def postseason(self,season):
        with self.read() as c:
            series=[dict(r) for r in c.execute('SELECT * FROM final_series WHERE season=? ORDER BY round_number',(season,))]
            games=[]
            for r in c.execute("SELECT id,round_number,game_number,absolute_day,content_json,result_json FROM final_contests WHERE season=? AND kind='post' AND status='completed' ORDER BY round_number,game_number",(season,)):
                result=decode(r['result_json'],{});games.append(dict(r,content=decode(r['content_json'],{}).get('name'),winner=(result.get('order') or [None])[0],teams=result.get('teams',[])))
            return dict(series=series,games=games)

    def agencies(self,season=None):
        with self.read() as c:
            years=sorted({r[0] for r in c.execute('SELECT season FROM season_schedules UNION SELECT season FROM season_finals UNION SELECT season FROM season_awards UNION SELECT season FROM season_honors')})
            if season is not None:years=[season]
            histories=defaultdict(list)
            for year in years:
                for r in self._league(c,year):histories[r['agency_id']].append(r)
            awards=Counter(r[0] for r in c.execute('SELECT awarded_agency_id FROM individual_awards WHERE (? IS NULL OR season=?)',(season,season)))
            rows=[]
            for a in c.execute('SELECT * FROM agencies'):
                h=histories[a['id']];wins=sum(r['wins'] for r in h);played=sum(r['played'] for r in h)
                rows.append(dict(a,history=h,played=played,wins=wins,losses=sum(r['losses'] for r in h),rate=rate(wins,played),
                    points=sum(r['points'] for r in h),regular_points=sum(r['regular_points'] for r in h),
                    special_points=sum(r['special_points'] for r in h),penalty=sum(r['penalty'] for r in h),
                    champions=sum(r['champion'] for r in h),regular_first=sum(r['rank']==1 for r in h),
                    qualifications=sum(r['qualified'] is True for r in h),best_rank=min((r['rank'] for r in h if r['rank']),default=None),awards=awards[a['id']],
                    debt=c.execute('SELECT COALESCE(SUM(outstanding_krw),0) FROM finance_debts WHERE agency_id=?',(a['id'],)).fetchone()[0]))
            return rows

    def player_history(self,person):
        with self.read() as c:
            rows=self._totals(c,self.params(None,None,None,person),'season,agency_id,kind')
            for r in rows:r['rate']=rate(r['successes'],r['attempts'])
            awards=[dict(r) for r in c.execute('SELECT season,award_type,awarded_agency_id FROM individual_awards WHERE person_id=? ORDER BY season',(person,))]
            moves=[dict(r) for r in c.execute('SELECT absolute_day,from_agency,to_agency,kind FROM market_history WHERE person_id=? ORDER BY absolute_day',(person,))]
            roles=[dict(r) for r in c.execute('SELECT (absolute_day/224)+1 season,agency_id,role,COUNT(*) days FROM development_days WHERE person_id=? GROUP BY season,agency_id,role',(person,))]
            growth=[]
            if person in ProfileService.public_ids(c):
                for season in sorted({r['season'] for r in rows}|{r[0]//224+1 for r in c.execute('SELECT s.absolute_day FROM development_results r JOIN development_settlements s ON s.id=r.settlement_id WHERE r.person_id=?',(person,))}):
                    changes=ProfileService.growth(c,person,season)
                    growth.append(dict(season=season,start_ca=None,end_ca=None,changes=changes))
            return dict(seasons=rows,awards=awards,moves=moves,roles=roles,growth=growth)

    def agency_history(self,agency,season):
        with self.read() as c:
            ledger=[dict(r) for r in c.execute('SELECT * FROM finance_ledger WHERE agency_id=? AND season=? ORDER BY absolute_day,id',(agency,season))]
            first=ledger[0] if ledger else None
            finances=dict(start=first['cash_before'] if first and first['absolute_day']==(season-1)*224 else None,
                income=sum(max(0,r['cash_delta']) for r in ledger) if ledger else None,expense=-sum(min(0,r['cash_delta']) for r in ledger) if ledger else None,
                last_recorded_cash=ledger[-1]['cash_after'] if ledger else None,end=None,end_debt=None)
            # Contract intervals / day logs are evidence. Current roster is not history.
            people=[dict(r) for r in c.execute('''SELECT DISTINCT p.id,p.name,x.kind,x.start_day,x.end_day,x.annual_krw FROM finance_contracts x JOIN people p ON p.id=x.person_id
                WHERE x.agency_id=? AND x.start_day<? AND (x.end_day IS NULL OR x.end_day>?)''',(agency,season*224,(season-1)*224))]
            roles=[dict(r) for r in c.execute('SELECT DISTINCT p.id,p.name,d.role FROM development_days d JOIN people p ON p.id=d.person_id WHERE d.agency_id=? AND d.absolute_day>=? AND d.absolute_day<?',(agency,(season-1)*224,season*224))]
            moves=[dict(r) for r in c.execute('SELECT person_id,absolute_day,kind,from_agency,to_agency FROM market_history WHERE (from_agency=? OR to_agency=?) AND absolute_day>=? AND absolute_day<?',(agency,agency,(season-1)*224,season*224))]
            awards=[dict(r) for r in c.execute('SELECT person_id,award_type FROM individual_awards WHERE awarded_agency_id=? AND season=?',(agency,season))]
            special=[dict(r) for r in c.execute('SELECT e.week,r.stage,r.content_name,t.rank FROM special_team_results t JOIN special_rounds r ON r.id=t.round_id JOIN special_events e ON e.id=r.event_id WHERE e.season=? AND t.agency_id=? AND r.status=\'completed\'',(season,agency))]
            post=[dict(r) for r in c.execute('SELECT round_number,agency_a,agency_b,winner_id FROM final_series WHERE season=? AND (agency_a=? OR agency_b=?) ORDER BY round_number',(season,agency,agency))]
            return dict(finances=finances,contracts=people,roles=roles,moves=moves,awards=awards,special=special,postseason=post)

    def compare_players(self,left,right,*,season=None,kind='regular'):
        table={r['id']:r for r in self.players(season=season,kind=kind)}
        result=[]
        with self.read() as c:
            public=ProfileService.public_ids(c);day=current_game_date(c)
            for person in (left,right):
                if person not in table:raise ValueError('공개된 아이돌을 선택해 주세요.')
                p=dict(table[person]);p['exact']=person in public;p['bounds']=ProfileService.abilities(c,person,p['exact'])
                p['average_bounds']=tuple(sum(b[i] for b in p['bounds'])/8 for i in (0,1)) if all(b[0] is not None for b in p['bounds']) else (None,None)
                p['health']=c.execute('SELECT health FROM idols WHERE person_id=?',(person,)).fetchone()[0] if p['exact'] else None
                salary=c.execute('SELECT annual_krw FROM finance_contracts WHERE person_id=? AND start_day<=? AND (end_day IS NULL OR end_day>?) ORDER BY start_day DESC LIMIT 1',(person,day.absolute_day,day.absolute_day)).fetchone() if p['exact'] and day else None
                p['salary']=salary[0] if salary else None;result.append(p)
        return result

    def compare_agencies(self,left,right,*,season=None):
        table={r['id']:r for r in self.agencies(season)};result=[]
        with self.read() as c:
            for agency in (left,right):
                if agency not in table:raise ValueError('기획사를 선택해 주세요.')
                p=dict(table[agency]);values=c.execute('''SELECT AVG(i.average),AVG(i.health),COUNT(*) FROM roster_memberships r JOIN idols i ON i.person_id=r.person_id
                    WHERE r.agency_id=? AND r.career_status IN('first_team','second_team','pro_pending')''',(agency,)).fetchone()
                p.update(current_pro_ca=values[0],current_pro_health=values[1],current_pro_count=values[2]);result.append(p)
        return result

    def leaders(self,season=None):
        players=self.players(season=season);agencies=self.agencies(season);records=[]
        for field in ('champions','regular_first','wins','qualifications'):
            best=max((r[field] for r in agencies),default=0)
            if best:records.extend(dict(kind='agency',metric=field,id=r['id'],name=r['name'],value=best) for r in agencies if r[field]==best)
        for field in ('awards','appearances','winning_idol','successes'):
            best=max((r[field] for r in players),default=0)
            if best:records.extend(dict(kind='player',metric=field,id=r['id'],name=r['name'],value=best) for r in players if r[field]==best)
        with self.read() as c:
            mvp=[dict(r) for r in c.execute("SELECT p.id,p.name,COUNT(*) value FROM individual_awards a JOIN people p ON p.id=a.person_id WHERE a.award_type='mvp' AND (? IS NULL OR a.season=?) GROUP BY p.id",(season,season))]
        best=max((r['value'] for r in mvp),default=0)
        records.extend(dict(r,kind='player',metric='mvp') for r in mvp if r['value']==best)
        return records
