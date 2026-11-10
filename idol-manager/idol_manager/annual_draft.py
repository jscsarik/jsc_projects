"""Annual coordinator: founding DraftTurn DTO + existing MarketService contracts."""
from contextlib import closing,contextmanager
from pathlib import Path
import json
from .game_clock import current_game_date
from .draft import DraftTurn,DraftError
from .market_service import MarketService,MarketError,public_people,_entry_day,_slot,_budget,_move,sync_terms
from .annual_recruitment import intake,intake_issue

class AnnualDraftError(DraftError):pass


def bound_market(c,seed_factory=None):
    class Bound(MarketService):
        @contextmanager
        def write(self):yield c
    return Bound(None,seed_factory=seed_factory)


def sync_session(c,season):
    session=c.execute('SELECT * FROM annual_sessions WHERE season=?',(season,)).fetchone()
    if not session or session['status']=='completed':return
    day=current_game_date(c).absolute_day
    for t in c.execute("SELECT * FROM annual_turns WHERE season=? AND status='negotiating'",(season,)).fetchall():
        n=c.execute('SELECT status FROM market_negotiations WHERE id=?',(t['negotiation_id'],)).fetchone()
        if not n or n[0]=='open':continue
        status='signed' if n[0]=='accepted' else 'failed'
        if n[0]=='abandoned':
            _move(c,t['person_id'],None,'fa','draft_contract_abandoned',related=t['pick_id'])
            c.execute('UPDATE market_draft_rights SET consumed=1 WHERE id=?',(t['pick_id'],))
        c.execute('UPDATE annual_turns SET status=?,completed_day=?,contract_kind=? WHERE season=? AND pick_number=?',(status,day,('draft_trainee' if t['registration']=='trainee' else 'pro') if status=='signed' else None,season,t['pick_number']))
    finished=c.execute("SELECT COUNT(*) FROM annual_turns WHERE season=? AND status IN('signed','failed')",(season,)).fetchone()[0]
    if finished==30:
        c.execute("UPDATE annual_sessions SET status='completed',completed_day=? WHERE season=?",(day,season))
        from .market_service import record_outcome
        for p in c.execute('''SELECT p.person_id,EXISTS(SELECT 1 FROM annual_turns t WHERE t.season=p.season AND t.person_id=p.person_id) picked
            FROM annual_pool p WHERE p.season=?''',(season,)).fetchall():
            record_outcome(c,season,p['person_id'],picked=bool(p['picked']))


def draft_issue(c,season):
    runtime=c.execute('SELECT first_season FROM annual_runtime').fetchone()
    if not runtime or season<runtime[0]:return ''
    issue=intake_issue(c,season)
    if issue:return issue
    session=c.execute('SELECT status FROM annual_sessions WHERE season=?',(season,)).fetchone()
    return '' if session and session[0]=='completed' else '통합 드래프트 30개 지명권과 계약 처리를 완료한 뒤 비시즌 3주차로 진행할 수 있습니다.'


def pool_ids(c):
    day=current_game_date(c)
    return [r[0] for r in c.execute('''SELECT i.person_id FROM idols i JOIN roster_memberships r ON r.person_id=i.person_id
        WHERE r.agency_id IS NULL AND r.career_status IN('fa','unassigned')
        AND (i.status='candidate' OR EXISTS(SELECT 1 FROM professional_history h WHERE h.person_id=i.person_id))
        AND NOT EXISTS(SELECT 1 FROM finance_contracts x WHERE x.person_id=i.person_id AND x.start_day<=? AND (x.end_day IS NULL OR x.end_day>?))
        ORDER BY i.person_id''',(day.absolute_day,day.absolute_day))]


class AnnualDraftService:
    def __init__(self,database,root,market,*,user_asset_dir=None):self.database=database;self.root=Path(root);self.market=market;self.user_asset_dir=user_asset_dir

    @contextmanager
    def write(self):
        with closing(self.database.connect()) as c,c:
            c.execute('BEGIN IMMEDIATE')
            sync_terms(c)
            if not c.execute("SELECT 1 FROM draft_state WHERE status='completed'").fetchone():raise AnnualDraftError('창단 16라운드 드래프트를 먼저 완료해 주세요.')
            yield c

    def rescan(self):
        with self.write() as c:
            result=intake(c,self.root,user_asset_dir=self.user_asset_dir)
            if result is None:raise AnnualDraftError('신규 유입은 적용 대상 시즌의 비시즌 1~2주차에 진행합니다.')
            return result

    def start(self):
        with self.write() as c:
            day=current_game_date(c)
            runtime=c.execute('SELECT first_season FROM annual_runtime').fetchone()
            if not runtime or day.season<runtime[0]:raise AnnualDraftError('이 세이브는 다음 적용 시즌부터 통합 드래프트를 사용합니다.')
            if not day.is_offseason or day.week!=2:raise AnnualDraftError('통합 드래프트는 비시즌 2주차에 진행합니다.')
            if c.execute('SELECT 1 FROM annual_sessions WHERE season=?',(day.season,)).fetchone():return
            issue=intake_issue(c,day.season)
            if issue:raise AnnualDraftError(issue)
            row=c.execute('SELECT final_order_json FROM season_finals WHERE season=?',(day.season,)).fetchone()
            if not row or not row[0]:raise AnnualDraftError('전년도 정규 최종 순위를 먼저 확정해 주세요.')
            ranks=json.loads(row[0]);agencies={r[0] for r in c.execute('SELECT id FROM agencies')}
            if len(ranks)!=10 or set(ranks)!=agencies:raise AnnualDraftError('10개 기획사의 확정 정규 순위가 필요합니다.')
            if c.execute("SELECT 1 FROM final_contests WHERE season=? AND kind='tie' AND status!='completed'",(day.season,)).fetchone():raise AnnualDraftError('정규 순위 동률 결정전이 미완료입니다.')
            c.execute("INSERT INTO annual_sessions VALUES (?,1,?,'in_progress',?,?,NULL)",(day.season,day.season+1,json.dumps(ranks),day.absolute_day))
            for round_number in range(1,4):
                order=list(reversed(ranks)) if round_number%2 else ranks
                for position,agency in enumerate(order,1):
                    turn=DraftTurn((round_number-1)*10+position,round_number,position,agency)
                    c.execute('''INSERT INTO annual_turns(season,pick_number,round_number,agency_id,pick_id)
                        VALUES (?,?,?,?,?)''',(day.season,turn.pick_number,turn.round_number,turn.agency_id,f'annual:{day.season}:{turn.pick_number}'))
            c.executemany('INSERT INTO annual_pool VALUES (?,?)',[(day.season,p) for p in pool_ids(c)])

    @staticmethod
    def _current(c,season):
        return c.execute("SELECT * FROM annual_turns WHERE season=? AND status IN('scheduled','negotiating') ORDER BY pick_number LIMIT 1",(season,)).fetchone()

    @staticmethod
    def _candidates(c,season):
        ids=[r[0] for r in c.execute('''SELECT p.person_id FROM annual_pool p
            WHERE p.season=? AND NOT EXISTS(SELECT 1 FROM annual_turns t WHERE t.season=p.season AND t.person_id=p.person_id)''',(season,))]
        legal=set(pool_ids(c));ids=[p for p in ids if p in legal]
        return list(public_people(c,available=True,person_ids=ids)) if ids else []

    def state(self,season=None):
        with closing(self.database.connect()) as c:
            c.execute('PRAGMA query_only=ON');c.execute('BEGIN');day=current_game_date(c)
            season=season or (day.season if day else 1)
            event=c.execute('SELECT * FROM annual_intakes WHERE season=?',(season,)).fetchone()
            session=c.execute('SELECT * FROM annual_sessions WHERE season=?',(season,)).fetchone()
            turn=self._current(c,season) if session else None
            turns=[dict(r) for r in c.execute('''SELECT t.*,p.name,p.photo_path FROM annual_turns t LEFT JOIN people p ON p.id=t.person_id WHERE season=? ORDER BY pick_number''',(season,))]
            candidates=self._candidates(c,season) if session else list(public_people(c,available=True,person_ids=pool_ids(c))) if day else []
            new_ids={r[0] for r in c.execute('SELECT person_id FROM annual_entries WHERE intake_season=?',(season,))}
            for p in candidates:p['new']=p['id'] in new_ids
            negotiation=None
            if turn and turn['negotiation_id']:
                n=c.execute('SELECT * FROM market_negotiations WHERE id=?',(turn['negotiation_id'],)).fetchone()
                negotiation=dict(n) if n else None
                if negotiation:negotiation['offers']=[dict(r) for r in c.execute('SELECT * FROM market_offers WHERE negotiation_id=? ORDER BY ordinal',(turn['negotiation_id'],))]
            player=c.execute('SELECT agency_id FROM player_settings').fetchone()
            runtime=c.execute('SELECT first_season FROM annual_runtime').fetchone()
            return dict(season=season,target_season=season+1,event=dict(event) if event else None,session=dict(session) if session else None,
                turn=dict(turn) if turn else None,turns=turns,candidates=candidates,player=player[0] if player else None,negotiation=negotiation,
                first_season=runtime[0] if runtime else 1,day=day.absolute_day if day else None)

    def person(self,identity):
        with closing(self.database.connect()) as c:
            values=public_people(c,person_ids=[identity])
            return values[0] if values else None

    def pick(self,agency,person,*,expected_pick,registration='pro'):
        with self.write() as c:
            day=_entry_day(c,agency,'draft');season=day.season
            turn=self._current(c,season)
            if not turn or turn['pick_number']!=expected_pick or turn['agency_id']!=agency or turn['status']!='scheduled':raise AnnualDraftError('지명 순서가 변경되었거나 이미 사용한 지명권입니다. 새로 확인해 주세요.')
            candidate=next((p for p in self._candidates(c,season) if p['id']==person),None)
            if candidate is None:raise AnnualDraftError('이미 지명·계약되었거나 지명할 수 없는 후보입니다.')
            if registration not in ('pro','trainee'):raise AnnualDraftError('등록 신분을 확인해 주세요.')
            registration='trainee' if candidate['age']<17 else registration
            if registration=='trainee' and (candidate['debut_season'] is not None or c.execute('SELECT 1 FROM professional_history WHERE person_id=?',(person,)).fetchone()):raise AnnualDraftError('기존 프로 경력자는 연습생으로 되돌릴 수 없습니다. 프로 등록을 선택해 주세요.')
            if registration=='pro':_slot(c,agency)
            _budget(c,agency,30000000 if candidate['age']>=17 else 20000000)
            c.execute('UPDATE annual_turns SET registration=? WHERE season=? AND pick_number=?',(registration,season,expected_pick))
            c.execute("UPDATE annual_turns SET person_id=?,prior_role=?,status='negotiating',picked_day=?,was_public=?,picked_age=? WHERE season=? AND pick_number=?",(person,candidate['career_status'],day.absolute_day,int(candidate['exact']),candidate['age'],season,expected_pick))
            api=bound_market(c,self.market.seed_factory)
            api.connect_draft_pick(agency,person,season,pick_id=turn['pick_id'])
            if candidate['age']<=16:
                c.execute("UPDATE annual_turns SET status='signed',completed_day=?,contract_kind='draft_trainee' WHERE season=? AND pick_number=?",(day.absolute_day,season,expected_pick))
            else:
                negotiation=api.start_negotiation(agency,person,'draft',context=turn['pick_id'])
                c.execute('UPDATE annual_turns SET negotiation_id=? WHERE season=? AND pick_number=?',(negotiation,season,expected_pick))
            sync_session(c,season)

    def offer(self,agency,annual,duration,*,expected_pick,request_id):
        with self.write() as c:
            day=current_game_date(c);turn=self._current(c,day.season)
            if not turn or turn['agency_id']!=agency or turn['pick_number']!=expected_pick or turn['status']!='negotiating':raise AnnualDraftError('현재 기획사의 진행 중인 지명 계약이 아닙니다.')
            return bound_market(c,self.market.seed_factory).offer(turn['negotiation_id'],annual,duration,request_id=request_id)

    def ai_step(self):
        from .annual_policy import offer_amount
        state=self.state();turn=state['turn']
        if not turn or turn['agency_id']==state['player']:return False
        agency=turn['agency_id']
        with closing(self.database.connect()) as c,c:
            from .recruitment_philosophy import ensure
            philosophy=ensure(c)[agency]
            own=public_people(c,agency=agency)
            # Debut metadata can be absent while the public pro-history guard applies.
            prior_pro_ids={r[0] for r in c.execute('SELECT person_id FROM professional_history')}
            legal=[]
            for p in state['candidates']:
                try:
                    if p['debut_season'] is not None or p['id'] in prior_pro_ids:_slot(c,agency)
                    _budget(c,agency,20000000 if p['age']<17 else 30000000)
                    legal.append(p)
                except ValueError:continue
            from .annual_policy import style_for
            style=style_for(self.root,agency)
        if turn['status']=='scheduled':
            if not legal:raise AnnualDraftError('계약 가능한 후보가 없습니다. 지명권은 보존했습니다. 기획사 재정을 정리한 뒤 재개해 주세요.')
            from .recruitment_policy import decide,public_view
            chosen,_=decide([public_view(p) for p in legal],[public_view(p) for p in own],philosophy,context='annual')
            mode='pro'
            with closing(self.database.connect()) as c:
                try:_slot(c,agency)
                except ValueError:mode='trainee'
            if philosophy['philosophy']=='development' and chosen['age']<=20 and next(p for p in legal if p['id']==chosen['id'])['debut_season'] is None and chosen['id'] not in prior_pro_ids:mode='trainee'
            self.pick(agency,chosen['id'],expected_pick=turn['pick_number'],registration=mode)
            state=self.state();turn=state['turn']
        if turn and turn['agency_id']==agency and turn['status']=='negotiating':
            with closing(self.database.connect()) as c:
                p=public_people(c,available=True,person_ids=[turn['person_id']])[0]
            n=state['negotiation'];amount=max(30000000,offer_amount(p,n['offers'],style))
            self.offer(agency,amount,1,expected_pick=turn['pick_number'],request_id=f'{turn["pick_id"]}:offer:{len(n["offers"])+1}')
        return True
