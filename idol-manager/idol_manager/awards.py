from .game_clock import regular_day
"""Regular-season individual awards. Never rolls a match or reads CA/PA."""
from collections import Counter,defaultdict
from contextlib import closing
from fractions import Fraction
import json,random,secrets
from .config import SKILLS
from .game_clock import current_game_date
from .match_policy import choose_award

LABELS=dict(zip(SKILLS,('보컬','댄스','랩','예능','외모','신체','지성','리더십')))
AWARDS={'mvp':'MVP','rookie':'신인왕','leader':'리더상',**{s:LABELS[s]+' 매력상' for s in SKILLS}}
class AwardError(ValueError):pass
def dump(v):return json.dumps(v,ensure_ascii=False,sort_keys=True)

V14_STATEMENTS=(
'''CREATE TABLE award_regular_rosters(game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 season INTEGER NOT NULL,person_id TEXT NOT NULL REFERENCES people(id),agency_id TEXT REFERENCES agencies(id),
 debut_season INTEGER,source TEXT NOT NULL,PRIMARY KEY(season,person_id))''',
'''CREATE TABLE award_match_selections(match_id TEXT NOT NULL REFERENCES match_results(match_id) ON DELETE CASCADE,
 kind TEXT NOT NULL CHECK(kind IN('winning_idol','losing_idol')),person_id TEXT NOT NULL REFERENCES people(id),
 source TEXT NOT NULL,PRIMARY KEY(match_id,kind))''',
'''CREATE TABLE season_awards(season INTEGER PRIMARY KEY,game_id INTEGER NOT NULL DEFAULT 1 REFERENCES game(id) ON DELETE CASCADE,
 seed TEXT NOT NULL,finalized_day INTEGER NOT NULL,regular_first TEXT NOT NULL REFERENCES agencies(id),
 champion TEXT NOT NULL REFERENCES agencies(id),records_json TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''',
'''CREATE TABLE individual_awards(season INTEGER NOT NULL REFERENCES season_awards(season) ON DELETE CASCADE,
 award_type TEXT NOT NULL CHECK(award_type IN('mvp','rookie','leader','vocal','dance','rap','entertainment','appearance','physique','intelligence','leadership')),
 person_id TEXT NOT NULL REFERENCES people(id),awarded_agency_id TEXT REFERENCES agencies(id),
 regular_agency_id TEXT NOT NULL REFERENCES agencies(id),regular_rank INTEGER NOT NULL,
 stats_json TEXT NOT NULL,candidates_json TEXT NOT NULL,draws_json TEXT NOT NULL,
 PRIMARY KEY(season,award_type))''',
'CREATE INDEX individual_awards_person ON individual_awards(person_id,season)',
)

# Keep historical winner rows unchanged. A separate completion ledger can
# represent a legitimate vacancy without inventing a person or a trophy.
V17_STATEMENTS=(
'''CREATE TABLE IF NOT EXISTS award_outcomes(season INTEGER NOT NULL REFERENCES season_awards(season) ON DELETE CASCADE,
 award_type TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN('AWARDED','NO_ELIGIBLE_CANDIDATE')),
 person_id TEXT REFERENCES people(id),PRIMARY KEY(season,award_type),
 CHECK((status='AWARDED' AND person_id IS NOT NULL) OR
 (status='NO_ELIGIBLE_CANDIDATE' AND award_type='rookie' AND person_id IS NULL)))''',
"INSERT OR IGNORE INTO award_outcomes SELECT season,award_type,'AWARDED',person_id FROM individual_awards",
)

def regular_identity(c,person,season):
    saved=c.execute('SELECT * FROM award_regular_rosters WHERE season=? AND person_id=?',(season,person)).fetchone()
    if saved:return dict(saved)
    end=regular_day(season,24,6);day=current_game_date(c)
    agency=None;source=None
    if day and day.absolute_day<=end:
        r=c.execute('SELECT agency_id FROM roster_memberships WHERE person_id=?',(person,)).fetchone()
        if r:agency,source=r[0],'regular_end_live'
    else:
        r=c.execute('SELECT agency_id FROM development_days WHERE person_id=? AND absolute_day=?',(person,end)).fetchone()
        if r:agency,source=r[0],'daily_registration'
        if source is None:
            r=c.execute('SELECT from_agency FROM market_history WHERE person_id=? AND absolute_day>? ORDER BY absolute_day,rowid LIMIT 1',(person,end)).fetchone()
            if r:agency,source=r[0],'first_later_transfer'
        if source is None:
            r=c.execute('SELECT to_agency FROM market_history WHERE person_id=? AND absolute_day<=? ORDER BY absolute_day DESC,rowid DESC LIMIT 1',(person,end)).fetchone()
            if r:agency,source=r[0],'last_regular_transfer'
        if source is None:
            rollout=c.execute('SELECT rollout_day FROM market_runtime WHERE game_id=1').fetchone()
            if rollout and rollout[0]<=end:
                r=c.execute('SELECT agency_id FROM roster_memberships WHERE person_id=?',(person,)).fetchone()
                if r:agency,source=r[0],'complete_market_history'
        if source is None:
            frozen=c.execute('SELECT frozen_json FROM season_finals WHERE season=?',(season,)).fetchone()
            for a,team in json.loads(frozen[0] if frozen else '{}').items():
                if any(p['id']==person for p in team['players']):agency,source=a,'frozen_regular_first_team';break
    if source is None:raise AwardError('정규 종료 소속 기록이 없습니다: '+person)
    if agency is None:
        r=c.execute('''SELECT p.agency_id FROM match_player_stats p JOIN scheduled_matches m ON m.id=p.match_id
            WHERE p.person_id=? AND m.season=? AND m.status='completed' ORDER BY m.week DESC,m.weekday DESC,m.day_order DESC LIMIT 1''',(person,season)).fetchone()
        if r:agency=r[0];source+=':last_regular_appearance'
    debut=c.execute('SELECT debut_season FROM market_careers WHERE person_id=?',(person,)).fetchone()
    debut=debut[0] if debut else None
    if debut is None and c.execute('SELECT 1 FROM draft_picks WHERE person_id=?',(person,)).fetchone():debut=1
    return dict(person_id=person,agency_id=agency,debut_season=debut,source=source)

def capture_regular_rosters(c,season):
    for r in c.execute('SELECT person_id FROM professional_history').fetchall():
        if not c.execute('SELECT 1 FROM award_regular_rosters WHERE season=? AND person_id=?',(season,r[0])).fetchone():
            v=regular_identity(c,r[0],season)
            c.execute('INSERT INTO award_regular_rosters VALUES (1,?,?,?,?,?)',(season,r[0],v['agency_id'],v['debut_season'],v['source']))

def aggregate(c,season,*,recover=False,rng=None):
    """Read persisted events once. Recovery adds selections in a separate ledger only."""
    matches={r['id']:dict(r) for r in c.execute('''SELECT m.*,r.resolution,r.winner_id,r.loser_id FROM scheduled_matches m
        JOIN match_results r ON r.match_id=m.id WHERE m.season=? AND m.status='completed' ''',(season,))}
    players=[dict(r) for r in c.execute('''SELECT p.* FROM match_player_stats p JOIN scheduled_matches m ON m.id=p.match_id
        WHERE m.season=? AND m.status='completed' ''',(season,))]
    counts=defaultdict(Counter)
    for r in c.execute('''SELECT e.match_id,e.person_id,e.phase,e.skill,COUNT(*) n,SUM(e.success) k FROM match_events e
        JOIN scheduled_matches m ON m.id=e.match_id WHERE m.season=? AND m.status='completed'
        AND e.phase IN('main','support','leader') GROUP BY e.match_id,e.person_id,e.phase,e.skill''',(season,)):
        counts[r['match_id'],r['person_id']][r['phase'],r['skill'],'n']=r['n']
        counts[r['match_id'],r['person_id']][r['phase'],r['skill'],'k']=r['k']
    by_match=defaultdict(list);records={};issues=[]
    teams=defaultdict(set)
    for r in c.execute('SELECT t.match_id,t.agency_id FROM match_team_stats t JOIN scheduled_matches m ON m.id=t.match_id WHERE m.season=?',(season,)):
        teams[r[0]].add(r[1])
    registered=defaultdict(set)
    for r in c.execute('SELECT match_id,agency_id FROM match_participants WHERE season=?',(season,)):registered[r[0]].add(r[1])
    for identity in matches:
        if len(teams[identity])!=2 or teams[identity]!=registered[identity]:issues.append('기획사 경기 결과 누락: '+identity)
    identities={r['id']:dict(r) for r in c.execute('SELECT id,name,photo_path FROM people')}
    for p in players:
        key=p['match_id'],p['person_id'];v=counts[key];by_match[p['match_id']].append(p)
        n=sum(v[phase,s,'n'] for phase in ('main','support') for s in SKILLS)
        k=sum(v[phase,s,'k'] for phase in ('main','support') for s in SKILLS)
        leader_n=v['leader','leadership','n'];leader_k=v['leader','leadership','k']
        if n!=60 or k!=p['base_successes'] or any(sum(v[phase,s,'n'] for s in SKILLS)!=30 for phase in ('main','support')) or (leader_n,leader_k)!=(p['leader_attempts'],p['leader_successes']):
            issues.append('일반/리더 판정 이벤트가 요약과 일치하지 않습니다: '+p['match_id']+'/'+p['person_id'])
        if p['person_id'] not in records:
            ident=regular_identity(c,p['person_id'],season)
            records[p['person_id']]=dict(id=p['person_id'],name=identities[p['person_id']]['name'],photo_path=identities[p['person_id']]['photo_path'],
                agency=ident['agency_id'],debut=ident['debut_season'],appearances=0,wins=0,losses=0,winning_idol=0,losing_idol=0,
                leader_games=0,leader_attempts=0,leader_successes=0,skills={s:dict(attempts=0,successes=0) for s in SKILLS},contributions={})
        row=records[p['person_id']];row['appearances']+=1;row['wins']+=p['outcome']=='win';row['losses']+=p['outcome']=='loss'
        row['leader_games']+=leader_n>0;row['leader_attempts']+=leader_n;row['leader_successes']+=leader_k
        part=row['contributions'].setdefault(p['agency_id'],dict(appearances=0,wins=0,losses=0,winning_idol=0,losing_idol=0,leader_attempts=0,leader_successes=0,skills={s:dict(attempts=0,successes=0) for s in SKILLS}))
        part['appearances']+=1;part['wins']+=p['outcome']=='win';part['losses']+=p['outcome']=='loss';part['leader_attempts']+=leader_n;part['leader_successes']+=leader_k
        for s in SKILLS:
            for field,t in (('attempts','n'),('successes','k')):
                value=sum(v[phase,s,t] for phase in ('main','support'))
                row['skills'][s][field]+=value;part['skills'][s][field]+=value
    for match in matches.values():
        participants=by_match[match['id']]
        if not participants and match['resolution'] not in ('forfeit','double_forfeit'):issues.append('출전 기록 누락: '+match['id'])
        for field,team,metric in (('winning_idol',match['winner_id'],'base_successes'),('losing_idol',match['loser_id'],'base_failures')):
            own=[p for p in participants if p['agency_id']==team]
            if not own:continue
            selected=[p['person_id'] for p in own if p[field]]
            if len(selected)>1:issues.append('중복 확정 선정자: '+match['id']);continue
            recovered=c.execute('SELECT person_id FROM award_match_selections WHERE match_id=? AND kind=?',(match['id'],field)).fetchone()
            if not selected and recovered:selected=[recovered[0]]
            if not selected:
                if not recover:issues.append('복구 가능한 경기 선정자 누락: '+match['id']);continue
                best=max(p[metric] for p in own)
                selected=[choose_award([p['person_id'] for p in own if p[metric]==best],rng)]
                c.execute('INSERT INTO award_match_selections VALUES (?,?,?,?)',(match['id'],field,selected[0],'saved_events_existing_tie_policy'))
            if selected[0] not in {p['person_id'] for p in own}:issues.append('선정자 소속 오류: '+match['id']);continue
            row=records[selected[0]];row[field]+=1;row['contributions'][team][field]+=1
    # MVP/rookie have no minimum-appearance rule. A first-year professional
    # with zero appearances remains eligible with real zero counters.
    for p in c.execute('''SELECT p.id,p.name,p.photo_path,m.retired_day FROM professional_history h
        JOIN people p ON p.id=h.person_id LEFT JOIN market_careers m ON m.person_id=p.id''').fetchall():
        if p['id'] in records or (p['retired_day'] is not None and p['retired_day']<(season-1)*224):continue
        ident=regular_identity(c,p['id'],season)
        if ident['debut_season'] is None or ident['debut_season']>season:continue
        records[p['id']]=dict(id=p['id'],name=p['name'],photo_path=p['photo_path'],agency=ident['agency_id'],debut=ident['debut_season'],
            appearances=0,wins=0,losses=0,winning_idol=0,losing_idol=0,leader_games=0,leader_attempts=0,leader_successes=0,
            skills={s:dict(attempts=0,successes=0) for s in SKILLS},contributions={})
    return list(records.values()),issues

def decide(records,order,season,rng):
    """Fraction comparisons; seeded uniform shuffles only inside same-rank ties."""
    if any(r.get('debut') is None for r in records):
        raise AwardError('프로 최초 데뷔 시즌이 누락되어 신인 자격을 확인할 수 없습니다.')
    ranks={a:i+1 for i,a in enumerate(order)};results={}
    def ranked(rows,key,stage,draws,limit=1):
        groups=defaultdict(list)
        scores=sorted((key(r) for r in rows),reverse=True)
        threshold=scores[min(limit,len(scores))-1] if scores else None
        for r in rows:
            if r['agency'] not in ranks:
                if key(r)>=threshold:raise AwardError('선정에 필요한 정규 종료 소속 순위를 찾을 수 없습니다: '+r['id'])
                continue
            groups[key(r),-ranks[r['agency']]].append(r)
        output=[]
        for score in sorted(groups,reverse=True):
            group=sorted(groups[score],key=lambda r:r['id'])
            if len(group)>1:
                if rng is not None:
                    pool=[r['id'] for r in group];rng.shuffle(group)
                    draws.append(dict(stage=stage,pool=pool,order=[r['id'] for r in group]))
                else:draws.append(dict(stage=stage,pool=[r['id'] for r in group],pending=True))
            output.extend(group)
        return output
    for kind in AWARDS:
        draws=[];eligible=list(records)
        if kind=='rookie':eligible=[r for r in eligible if r['debut']==season]
        if kind=='leader':eligible=[r for r in eligible if r['leader_attempts']>0]
        if kind in SKILLS:
            eligible=[r for r in eligible if r['skills'][kind]['attempts']>0]
            eligible=ranked(eligible,lambda r:r['skills'][kind]['attempts'],'candidate_boundary',draws,5)[:5]
            candidates=ranked(eligible,lambda r:Fraction(r['skills'][kind]['successes'],r['skills'][kind]['attempts']),'success_rate',draws)
        else:candidates=ranked(eligible,lambda r:r['leader_successes'] if kind=='leader' else r['winning_idol'],'award',draws)
        if not candidates:
            if kind=='rookie' and records and not eligible:
                results[kind]=dict(winner=None,candidates=[],draws=[],regular_rank=None,status='NO_ELIGIBLE_CANDIDATE')
                continue
            raise AwardError(AWARDS[kind]+'의 실제 유효 후보 기록이 없습니다.')
        results[kind]=dict(winner=candidates[0],candidates=candidates[:5],draws=draws,regular_rank=ranks[candidates[0]['agency']])
    return results

def readiness(c,season):
    day=current_game_date(c)
    if not day or day.absolute_day<(season-1)*224+182:return '정규 24주가 아직 끝나지 않았습니다.'
    count,done=c.execute("SELECT COUNT(*),SUM(status='completed') FROM scheduled_matches WHERE season=?",(season,)).fetchone()
    results=c.execute('SELECT COUNT(*) FROM match_results r JOIN scheduled_matches m ON m.id=r.match_id WHERE m.season=?',(season,)).fetchone()[0]
    if count!=585 or done!=585 or results!=585:return '정규 585경기의 공식 결과가 모두 필요합니다.'
    final=c.execute('SELECT * FROM season_finals WHERE season=?',(season,)).fetchone()
    if not final or not final['final_order_json']:return '정규 최종 순위가 미확정입니다.'
    if c.execute("SELECT 1 FROM final_contests WHERE season=? AND kind='tie' AND status!='completed'",(season,)).fetchone():return '순위 동률 결정전을 먼저 완료해 주세요.'
    if final['status']!='completed' or not final['champion_id']:return '포스트시즌 결승이 아직 끝나지 않았습니다.'
    order=json.loads(final['final_order_json'])
    if len(order)!=10 or len(set(order))!=10:return '확정 순위 10개 기획사의 기록을 확인해야 합니다.'
    return ''

def finalize(c,season,*,seed=None):
    old=c.execute('SELECT * FROM season_awards WHERE season=?',(season,)).fetchone()
    if old:
        winners=dict(c.execute('SELECT award_type,person_id FROM individual_awards WHERE season=?',(season,)))
        done=set(winners)
        for r in c.execute('SELECT award_type,status,person_id FROM award_outcomes WHERE season=?',(season,)):
            if r['status']=='AWARDED' and winners.get(r['award_type'])!=r['person_id']:
                raise AwardError('확정 수상자 기록이 누락되거나 불일치합니다: '+r['award_type'])
            if r['status']=='NO_ELIGIBLE_CANDIDATE' and r['award_type'] in winners:
                raise AwardError('수상 공석과 실제 수상 기록이 중복되었습니다.')
            done.add(r['award_type'])
        if done!=set(AWARDS):raise AwardError('확정 시상식의 11개 항목이 불완전합니다.')
        return False
    issue=readiness(c,season)
    if issue:raise AwardError(issue)
    c.execute('SAVEPOINT individual_awards_finalize')
    try:
        seed=str(seed if seed is not None else secrets.randbits(128));rng=random.Random(seed)
        rows,issues=aggregate(c,season,recover=True,rng=rng)
        if issues:raise AwardError('\n'.join(issues[:5]))
        if any(r['debut'] is None for r in rows):raise AwardError('프로 최초 데뷔 시즌이 확인되지 않는 출전 선수가 있습니다.')
        unknown=c.execute('''SELECT 1 FROM professional_history h LEFT JOIN market_careers m ON m.person_id=h.person_id
            WHERE m.debut_season IS NULL AND NOT EXISTS(SELECT 1 FROM draft_picks d WHERE d.person_id=h.person_id)
            AND (EXISTS(SELECT 1 FROM roster_memberships r WHERE r.person_id=h.person_id AND r.career_status IN('pro_pending','first_team','second_team'))
                OR EXISTS(SELECT 1 FROM finance_contracts x WHERE x.person_id=h.person_id AND x.kind='pro')) LIMIT 1''').fetchone()
        if unknown:raise AwardError('프로 최초 데뷔 시즌 기록이 누락되었습니다. 신인 자격 확인이 필요합니다.')
        final=c.execute('SELECT * FROM season_finals WHERE season=?',(season,)).fetchone();order=json.loads(final['final_order_json'])
        chosen=decide(rows,order,season,rng);capture_regular_rosters(c,season)
        day=current_game_date(c).absolute_day
        c.execute('INSERT INTO season_awards(season,seed,finalized_day,regular_first,champion,records_json) VALUES (?,?,?,?,?,?)',(season,seed,day,order[0],final['champion_id'],dump(rows)))
        for kind,value in chosen.items():
            winner=value['winner']
            c.execute('INSERT INTO award_outcomes VALUES (?,?,?,?)',(season,kind,'AWARDED' if winner else 'NO_ELIGIBLE_CANDIDATE',winner['id'] if winner else None))
            if winner is None:continue
            agency=c.execute('SELECT agency_id FROM roster_memberships WHERE person_id=?',(winner['id'],)).fetchone()
            c.execute('INSERT INTO individual_awards VALUES (?,?,?,?,?,?,?,?,?)',(season,kind,winner['id'],agency[0] if agency else None,winner['agency'],value['regular_rank'],dump(winner),dump(value['candidates']),dump(value['draws'])))
        c.execute('RELEASE individual_awards_finalize');return True
    except Exception:
        c.execute('ROLLBACK TO individual_awards_finalize');c.execute('RELEASE individual_awards_finalize');raise


class AwardsService:
    def __init__(self,database):self.database=database
    def finalize(self,season):
        with closing(self.database.connect()) as c,c:
            c.execute('BEGIN IMMEDIATE');return finalize(c,season)
    def view(self,season):
        with closing(self.database.connect()) as c:
            c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
            batch=c.execute('SELECT * FROM season_awards WHERE season=?',(season,)).fetchone()
            awards=[]
            for row in c.execute('SELECT * FROM individual_awards WHERE season=?',(season,)):
                value=dict(row)
                for key in ('stats','candidates','draws'):value[key]=json.loads(value.pop(key+'_json'))
                value['label']=AWARDS[value['award_type']];awards.append(value)
            for row in c.execute("SELECT * FROM award_outcomes WHERE season=? AND status='NO_ELIGIBLE_CANDIDATE'",(season,)):
                awards.append(dict(row,label=AWARDS[row['award_type']],stats=None,candidates=[],draws=[],awarded_agency_id=None,regular_agency_id=None,regular_rank=None))
            issue='';records=json.loads(batch['records_json']) if batch else [];preview={}
            if not batch:
                try:
                    records,issues=aggregate(c,season);issue='\n'.join(issues[:5]) or readiness(c,season)
                    final=c.execute('SELECT final_order_json FROM season_finals WHERE season=?',(season,)).fetchone()
                    if final and final[0]:preview=decide(records,json.loads(final[0]),season,None)
                except AwardError as error:issue=str(error)
            return dict(season=season,batch=dict(batch) if batch else None,awards=awards,records=records,preview=preview,issue=issue)
    def history(self,person=None,agency=None):
        with closing(self.database.connect()) as c:return history(c,person,agency)
    def seasons(self):
        with closing(self.database.connect()) as c:return [r[0] for r in c.execute('SELECT season FROM season_schedules UNION SELECT season FROM season_awards ORDER BY season DESC')]

def history(c,person=None,agency=None):
    return [dict(r,label=AWARDS[r['award_type']],stats=json.loads(r['stats_json'])) for r in c.execute('''SELECT a.*,s.finalized_day,s.created_at FROM individual_awards a
        JOIN season_awards s ON s.season=a.season WHERE (? IS NULL OR a.person_id=?) AND (? IS NULL OR a.awarded_agency_id=?)
        ORDER BY a.season DESC,a.award_type''',(person,person,agency,agency))]
