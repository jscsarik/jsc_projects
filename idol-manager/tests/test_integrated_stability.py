"""Additional exception paths in disposable modern-schema saves only."""
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import json,random,sqlite3,unittest
from tests import test_season32 as fixture
from idol_manager.service import GameService
from idol_manager.database import Database
from idol_manager.config import load_settings
from idol_manager.market_rules import raised_offer
from idol_manager.market_service import MarketError,active_contract,release_penalty,_settle_auctions
from idol_manager.ai_training import plan
from idol_manager.training_service import FOCUS_COST

class IntegratedStabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.Season32Tests.setUpClass.__func__(cls)
    setUp=fixture.Season32Tests.setUp
    rows=fixture.Season32Tests.rows;day=fixture.Season32Tests.day

    def dump(self):
        with closing(self.db.connect()) as c:return list(c.iterdump())

    def release(self,agency='ador'):
        person=self.rows("SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='second_team' AND person_id NOT IN (SELECT person_id FROM squad_leaders) LIMIT 1",(agency,))[0][0]
        self.service.market.release(agency,person,'immediate',request_id='integrated:release:'+agency)
        return person

    def test_all_three_founding_contracts_fail_then_fa_fill_and_sunday_formation(self):
        svc=GameService(self.root,database_path=Path(self.temp.name)/'founding.sqlite3')
        svc.database.create_game(svc.scan.people,load_settings(),random.Random(17));svc.calendar.initialize()
        svc.draft_session.select_agency('ador');svc.draft.start(rng=random.Random(3))
        for pick in range(1,161):svc.draft.pick(svc.draft.state().next_turn.agency_id,svc.draft.available_candidates()[0].id,expected_pick_number=pick)
        svc.calendar.advance_day(expected_absolute_day=0)
        negotiations=[n for n in svc.market.negotiations('ador') if n['purpose']=='founding']
        self.assertEqual(len(negotiations),3)
        for n in negotiations:
            p=next(p for p in svc.market.public_people() if p['id']==n['person_id']);annual=p['market']*9//10
            for attempt in range(3):
                with patch('idol_manager.market_service.random.Random') as rng:
                    rng.return_value.random.return_value=.999999
                    svc.market.offer(n['id'],annual,1,request_id=f'fail:{n["id"]}:{attempt}')
                annual=raised_offer(annual)
            self.assertEqual(next(p for p in svc.market.public_people() if p['id']==n['person_id'])['career_status'],'fa')
        with closing(svc.database.connect()) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM roster_memberships WHERE agency_id='ador' AND career_status='pro_pending'").fetchone()[0],13)
        svc.calendar.advance_day(expected_absolute_day=1)
        first=svc.recruitment.candidates()[0].id
        svc.recruitment.apply('ador',[first]);svc.recruitment.apply('jyp',[first])
        svc.calendar.advance_day(expected_absolute_day=2)
        results=svc.recruitment.results('ador',-21)
        self.assertTrue(any(r['person_id']==first and 'ador' in r['applicants'] and 'jyp' in r['applicants'] for r in results))
        for i in range(3):
            candidate=next(p for p in svc.market.public_people(available=True) if p['age']>=17)
            identity=svc.market.start_negotiation('ador',candidate['id'],'fa')
            svc.market.offer(identity,70000000,1,request_id='fill:'+candidate['id'])
        while svc.calendar.state().date.absolute_day<6:svc.calendar.advance_day(expected_absolute_day=svc.calendar.state().date.absolute_day)
        members=svc.squads.snapshot().members;svc.squads.confirm_initial(tuple(m.id for m in members if m.squad=='pro_pending')[:5])
        for squad in ('first_team','second_team'):
            state=svc.squads.snapshot();svc.squads.set_leader(squad,next(m.id for m in state.members if m.squad==squad),expected_revision=state.revision)
        svc.calendar.advance_day(expected_absolute_day=6)
        with closing(svc.database.connect()) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM squad_formations').fetchone()[0],10)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM roster_memberships WHERE career_status='first_team'").fetchone()[0],50)

    def test_competing_fa_bids_settle_once_with_contract_inheritance(self):
        person=self.release();self.release('jyp')
        auction=self.service.market.bid('ador',person,40000000,2,request_id='auction:a')
        self.service.market.bid('jyp',person,45000000,2,request_id='auction:b')
        deadline=self.rows('SELECT deadline FROM market_auctions WHERE id=?',(auction,))[0][0]
        self.day(deadline)
        with self.service.market.write() as c:_settle_auctions(c,deadline,lambda:9)
        self.assertEqual(self.rows('SELECT agency_id FROM roster_memberships WHERE person_id=?',(person,)),[('jyp',)])
        self.assertEqual(self.rows('SELECT end_season-start_season+1 FROM market_terms t JOIN finance_contracts x ON x.id=t.contract_id WHERE person_id=? ORDER BY x.rowid DESC LIMIT 1',(person,)),[(2,)])
        before=self.dump()
        with self.service.market.write() as c:_settle_auctions(c,deadline,lambda:123)
        self.assertEqual(before,self.dump())

    def test_no_cash_blocks_signing_and_focus_without_partial_writes(self):
        person=self.release();n=self.service.market.start_negotiation('ador',person,'fa')
        with closing(self.db.connect()) as c,c:c.execute("UPDATE agencies SET funds_krw=0 WHERE id='ador'")
        before=self.dump()
        with self.assertRaises(ValueError):self.service.market.offer(n,30000000,1,request_id='no-cash')
        self.assertEqual(before,self.dump());self.day(8)
        p=next(p for p in self.service.training.state('ador')['players'] if p['career_status']=='second_team')
        before=self.dump()
        with self.assertRaises(ValueError):self.service.training.save('ador',{p['id']:'vocal'},confirm=True,expected_revision=0)
        self.assertEqual(before,self.dump())

    def test_ai_training_private_read_denied_and_zero_cash_skips(self):
        self.day(8)
        with closing(self.db.connect()) as c,c:
            c.execute("UPDATE agencies SET funds_krw=0 WHERE id='jyp'")
            before=c.execute("SELECT funds_krw FROM agencies WHERE id='sm'").fetchone()[0]
            c.set_authorizer(lambda action,table,col,*_:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_READ and (table=='annual_secrets' or col in ('potential','archetype','special_prospect')) else sqlite3.SQLITE_OK)
            plan(c,self.root)
        self.assertFalse(self.rows("SELECT 1 FROM training_choices WHERE agency_id='jyp' AND skill IS NOT NULL"))
        count=self.rows("SELECT COUNT(*) FROM training_choices WHERE agency_id='sm' AND skill IS NOT NULL")[0][0]
        self.assertEqual(count,11);self.assertEqual(self.rows("SELECT funds_krw FROM agencies WHERE id='sm'")[0][0],before-count*FOCUS_COST)
        saved=self.dump()
        with closing(self.db.connect()) as c,c:plan(c,self.root)
        self.assertEqual(saved,self.dump())

    def test_future_schema_rejected_without_mutation(self):
        with closing(self.db.connect()) as c,c:c.execute('PRAGMA user_version=29')
        before=self.dump()
        with self.assertRaisesRegex(RuntimeError,'최신'):Database(self.path)
        self.assertEqual(before,self.dump())

    def test_release_one_third_remaining_basic_pay_and_retry_is_idempotent(self):
        person=self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='second_team' AND person_id NOT IN (SELECT person_id FROM squad_leaders) LIMIT 1")[0][0]
        with closing(self.db.connect()) as c:
            contract=active_contract(c,person)
            expected=((contract['annual_krw']+15000)//30000)*10000
            self.assertEqual(release_penalty(c,contract,7),expected)
        funds=self.rows("SELECT funds_krw FROM agencies WHERE id='ador'")[0][0]
        self.service.market.release('ador',person,'immediate',request_id='third-pay')
        self.assertEqual(self.rows("SELECT funds_krw FROM agencies WHERE id='ador'")[0][0],funds-expected)
        before=self.dump();self.service.market.release('ador',person,'immediate',request_id='third-pay')
        self.assertEqual(before,self.dump())

    def test_profile_projection_never_reads_or_returns_private_potential(self):
        original=self.db.connect
        def guarded():
            c=original();c.set_authorizer(lambda a,t,col,*_:sqlite3.SQLITE_DENY if a==sqlite3.SQLITE_READ and (t=='annual_secrets' or col in ('potential','archetype','special_prospect')) else sqlite3.SQLITE_OK);return c
        person=self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='first_team' LIMIT 1")[0][0]
        with patch.object(self.db,'connect',side_effect=guarded):record=self.service.profiles.get(person)
        for forbidden in ('potential','archetype','special_prospect'):self.assertNotIn(forbidden,json.dumps(record))

    def test_two_season_contract_does_not_shrink_at_half_year_birthday(self):
        self.day(203);person=self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='second_team' LIMIT 1")[0][0]
        n=self.service.market.start_negotiation('ador',person,'renew');self.service.market.offer(n,70000000,2,request_id='two-season')
        with closing(self.db.connect()) as c:contract=dict(active_contract(c,person));term=tuple(c.execute('SELECT start_season,end_season FROM market_terms WHERE contract_id=?',(contract['id'],)).fetchone())
        self.day(315)
        from idol_manager.development_service import settle_birthday
        with closing(self.db.connect()) as c,c:
            runtime=c.execute('SELECT * FROM development_runtime').fetchone();rules=json.loads(runtime['rules_json'])
            settle_birthday(c,315,runtime,rules);settle_birthday(c,315,runtime,rules)
            self.assertEqual(tuple(c.execute('SELECT start_season,end_season FROM market_terms WHERE contract_id=?',(contract['id'],)).fetchone()),term)
            self.assertEqual(c.execute('SELECT end_day FROM finance_contracts WHERE id=?',(contract['id'],)).fetchone()[0],contract['end_day'])
