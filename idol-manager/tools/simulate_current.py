"""32-week end-to-end runner. Writes only a marked diagnostics database.

Uses real production services and seeded entropy, never synthetic match outcomes.
Player actions use public information; nine AI policies are left unchanged.
"""
from pathlib import Path
from contextlib import closing
import argparse,hashlib,json,random,sqlite3,sys,time,traceback
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.simulate_game import Simulation,seeded_entropy,public_policy,schedule_audit,quick_audit,dump
from idol_manager.service import GameService
from idol_manager.config import load_settings,SKILLS
from idol_manager.game_clock import GameDate
from idol_manager.market_rules import raised_offer

class CurrentSimulation(Simulation):
    def setup(self):
        if self.args.resume:
            self.service=GameService(ROOT,self.path);self.service.calendar.rng=self.calendar_rng
            self.complete_draft();return
        dump(self.marker,dict(test_only=True,version='32-week-e2e',seed=self.args.seed,source_root=str(ROOT)))
        self.service=GameService(ROOT,self.path);self.service.calendar.rng=self.calendar_rng
        self.service.database.create_game(self.service.scan.people,load_settings(),random.Random(self.args.seed+3))
        self.service.calendar.initialize();self.service.draft_session.select_agency('ador')
        self.service.draft.start(rng=random.Random(self.args.seed+4))
        self.complete_draft()
        self.snapshot(1);self.save()

    def complete_draft(self):
        while self.service.draft.state().status!='completed':
            snap=self.service.draft_session.snapshot();turn=snap.state.next_turn
            if turn.agency_id!='ador':self.service.draft_session.pick_ai_turn();continue
            person=max(snap.candidates,key=lambda p:(sum(e.midpoint for e in p.estimates),p.id))
            self.service.draft_session.pick_player(person.id,expected_pick_number=turn.pick_number)

    def negotiate(self,n,amount=None):
        for attempt in range(3):
            row=next(x for x in self.service.market.negotiations('ador') if x['id']==n['id'])
            if row['status']!='open':return
            p=next(p for p in self.service.market.public_people() if p['id']==n['person_id'])
            offers=self.rows('SELECT annual FROM market_offers WHERE negotiation_id=? ORDER BY ordinal DESC',(n['id'],))
            annual=raised_offer(offers[0]['annual']) if offers else amount or ((p['market']*110+999999)//1000000)*10000
            self.service.market.offer(n['id'],annual,1,request_id=f'e2e:{n["id"]}:{len(offers)+1}')

    def formation(self):
        s=self.service.squads.snapshot()
        if not s.initialized:
            members=[p for p in s.members if p.squad in ('pro_pending','first_team','second_team')]
            self.service.squads.confirm_initial(self.service.squads.policy.plan(members).first_team_ids)
        else:
            while True:
                s=self.service.squads.snapshot()
                if sum(p.squad=='first_team' for p in s.members)>=5:break
                with closing(self.service.database.connect()) as c:
                    from idol_manager.conditions import promotion_allowed
                    eligible=[p for p in s.members if p.squad=='second_team' and promotion_allowed(c,p.id,self.service.calendar.state().date.absolute_day)]
                if not eligible:break
                p=max(eligible,key=lambda p:(p.average,p.health,p.id))
                self.service.squads.move(p.id,'first_team',expected_revision=s.revision)
        s=self.service.squads.snapshot()
        for role in ('first_team','second_team'):
            s=self.service.squads.snapshot();members=[p for p in s.members if p.squad==role]
            if members and not dict(s.leaders).get(role):
                self.service.squads.set_leader(role,max(members,key=lambda p:(p.leadership,p.id)).id,expected_revision=s.revision)

    def replenish(self):
        svc=self.service
        for attempt in range(24):
            own=svc.market.public_people(agency='ador')
            if sum(p['career_status'] in ('first_team','second_team','pro_pending') for p in own)>=16:return
            options=[p for p in svc.market.public_people(available=True) if p['age']>=17]
            if not options:return
            target=max(options,key=lambda p:(p['average'],p['health'] or 0,p['id']))
            identity=svc.market.start_negotiation('ador',target['id'],'fa')
            self.negotiate(next(n for n in svc.market.negotiations('ador') if n['id']==identity))

    def player_actions(self,d):
        svc=self.service
        if d.is_founding and d.weekday()==1:
            for n in svc.market.negotiations('ador'):
                if n['purpose']=='founding' and n['status']=='open':self.negotiate(n,70000000)
        if d.is_founding and d.weekday() in (3,5):self.replenish()
        if d.is_offseason and d.week==1 and d.weekday()==0:
            for p in svc.market.public_people(agency='ador'):
                if p['career_status'] in ('first_team','second_team') and p['end_season'] is not None and p['end_season']<=d.season:
                    identity=svc.market.start_negotiation('ador',p['id'],'renew')
                    self.negotiate(next(n for n in svc.market.negotiations('ador') if n['id']==identity))
        if d.is_offseason and d.week==2 and d.weekday()==0:self.annual()
        if d.is_offseason and d.week==3 and d.weekday()==0:self.replenish()
        if (d.is_founding and d.weekday()==6) or (not d.is_founding and d.weekday()==0 and (d.is_regular or d.is_preparation or d.is_maintenance or d.is_postseason)):
            if not d.is_founding and svc.squads.snapshot().initialized and d.is_regular:
                super().player_policy()
            self.formation()
        state=svc.recruitment.state('ador')
        if state['can_apply']:
            options=svc.recruitment.candidates()
            svc.recruitment.apply('ador',[p.id for p in options[:2]],expected_revision=state['revision'])
        if d.weekday()==1 and (d.is_regular or d.is_postseason):
            sheet=svc.training.state('ador')
            if not sheet['confirmed']:
                budget=max(0,svc.finance.budget('ador'));choices={}
                for p in sheet['players']:
                    if p['career_status']=='second_team' and budget>=150000:
                        choices[p['id']]=SKILLS[max(range(8),key=lambda i:(100-p['skills'][i])*(3 if p['skills'][i]>=90 else 2))];budget-=150000
                svc.training.save('ador',choices,confirm=True,expected_revision=sheet['revision'])

    def annual(self):
        api=self.service.annual_draft;api.start()
        for step in range(150):
            state=api.state();turn=state['turn']
            if turn is None:return
            if turn['agency_id']!='ador':api.ai_step();continue
            if turn['status']=='scheduled':
                own=self.service.market.public_people(agency='ador')
                full=sum(p['career_status'] in ('first_team','second_team','pro_pending') for p in own)>=16
                prior={r['person_id'] for r in self.rows('SELECT person_id FROM professional_history')}
                candidates=[p for p in state['candidates'] if not full or (p['debut_season'] is None and p['id'] not in prior)]
                if not candidates:raise ValueError('No legal player annual draft candidate')
                p=max(candidates,key=lambda p:(p['average'],p['id']))
                api.pick('ador',p['id'],expected_pick=turn['pick_number'],registration='trainee' if full else 'pro')
                state=api.state();turn=state['turn']
            if turn and turn['agency_id']=='ador' and turn['status']=='negotiating':
                p=api.person(turn['person_id']);offers=state['negotiation']['offers']
                amount=raised_offer(offers[-1]['annual']) if offers else max(30000000,((p['market']*110+999999)//1000000)*10000)
                api.offer('ador',amount,1,expected_pick=turn['pick_number'],request_id=f'e2e:annual:{state["season"]}:{turn["pick_number"]}:{len(offers)+1}')
        raise RuntimeError('Annual draft did not terminate within 150 official actions')

    def audit_now(self,d,*,full=False):
        with closing(self.service.database.connect()) as c:
            checks=quick_audit(c)
            leaders=c.execute('''SELECT COUNT(*) FROM squad_leaders l LEFT JOIN roster_memberships r ON r.person_id=l.person_id WHERE r.agency_id IS NOT l.agency_id OR r.career_status!=l.squad''').fetchone()[0]
            checks['invalid_leaders']=leaders
            checks['trade_limit']=c.execute("SELECT COUNT(*) FROM (SELECT a.agency_id,((t.executed_day/224)+1) season,COUNT(*) n FROM market_trades t JOIN (SELECT id,agency_a agency_id FROM market_trades UNION ALL SELECT id,agency_b FROM market_trades) a ON a.id=t.id WHERE t.status='completed' GROUP BY a.agency_id,season HAVING n>2)").fetchone()[0]
            checks['average_cache']=c.execute('SELECT COUNT(*) FROM idols i WHERE ABS(i.average-(SELECT AVG(value) FROM abilities a WHERE a.person_id=i.person_id))>0.00501').fetchone()[0]
            checks['cash_ledger']=c.execute('SELECT COUNT(*) FROM (SELECT a.id FROM agencies a LEFT JOIN finance_ledger l ON l.agency_id=a.id GROUP BY a.id HAVING a.funds_krw!=1000000000+COALESCE(SUM(l.cash_delta),0))').fetchone()[0]
            if full:
                checks['integrity']=int(c.execute('PRAGMA integrity_check').fetchone()[0]!='ok')
                schedule=schedule_audit(c,d.season);self.audit.append(schedule)
                if schedule['status']!='PASS':raise AssertionError(schedule)
            self.audit.append(dict(day=d.absolute_day,checks=checks))
        dump(self.output/'integrity_checks.json',self.audit)
        if any(checks.values()):raise AssertionError(checks)

    def report(self,status):
        d=self.service.calendar.state().date
        counts=self.rows('''SELECT m.season,COUNT(*) regular FROM match_results r JOIN scheduled_matches m ON m.id=r.match_id GROUP BY m.season''')
        report=dict(status=status,seed=self.args.seed,absolute_day=d.absolute_day,date=str(d),elapsed=round(time.monotonic()-self.started,2),seasons=self.seasons,regular=counts,issues=self.issues,action=self.current_action,test_db=str(self.path))
        dump(self.output/'simulation_summary.json',report);print(json.dumps(report,ensure_ascii=False),flush=True)

    def run(self):
        status='running'
        with seeded_entropy(self.entropy,self.identities):
            try:
                self.setup()
                while True:
                    d=self.service.calendar.state().date
                    if d.season>self.args.seasons:break
                    if time.monotonic()>self.deadline:raise TimeoutError('Checkpoint time budget reached')
                    self.current_action=f'player:{d.absolute_day}';self.player_actions(d)
                    for f in self.service.matches.fixtures():
                        if f.status=='completed':continue
                        self.current_action=f'regular:{d.absolute_day}:{f.id}';r=self.service.matches.play(f.id)
                        if f.day_order==1 and self.entropy.random()<.02:
                            assert self.service.matches.play(f.id)==r
                    for e in self.service.specials.events():
                        if not e['today'] or e['status']=='completed':continue
                        self.current_action=f'special:{d.absolute_day}:{e["id"]}';self.service.specials.start(e['id'])
                        while True:
                            todo=[r for r in self.service.specials.state(e['id'])['rounds'] if r['status']!='completed']
                            if not todo:break
                            self.service.specials.play(todo[0]['id'])
                    for row in self.service.finals.rows():
                        if row['status']!='completed':
                            self.current_action=f'final:{d.absolute_day}:{row["id"]}';self.service.finals.play(row['id'])
                    if d.weekday()==6:
                        self.current_action=f'audit:{d.absolute_day}';self.audit_now(d,full=d.day_in_season==223)
                        self.save();self.report('running')
                    if d.day_in_season==223:
                        self.finish_season(d.season)
                        if self.seasons[-1]['status']!='PASS':raise AssertionError(self.seasons[-1])
                    self.current_action=f'advance:{d.absolute_day}';self.service.calendar.advance_day(expected_absolute_day=d.absolute_day)
                    if d.weekday()==6:
                        # Reopen services from disk; no cached date, lineup or result assumptions.
                        self.service=GameService(ROOT,self.path);self.service.calendar.rng=self.calendar_rng
                status='completed'
            except Exception as error:
                status='checkpoint' if isinstance(error,TimeoutError) else 'blocked'
                self.issues.append(dict(action=self.current_action,error=repr(error),traceback=traceback.format_exc()));print(traceback.format_exc(),flush=True)
            finally:
                if hasattr(self,'service'):self.save();self.report(status)
        return status

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--seed',type=int,default=361105)
    parser.add_argument('--seasons',type=int,default=2);parser.add_argument('--resume',action='store_true');parser.add_argument('--budget-seconds',type=int,default=7200)
    args=parser.parse_args();args.allow_long_run=True
    raise SystemExit(0 if CurrentSimulation(args).run()=='completed' else 1)
