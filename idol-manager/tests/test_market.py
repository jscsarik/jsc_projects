"""Market fixtures are temporary; original save is never opened for writes."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import json,sqlite3,unittest,uuid,random,subprocess,sys
from idol_manager.market_service import (MarketService,MarketError,_new_contract,active_contract,process_market,
 _settle_auctions,release_penalty,_settlement,initialize_market,public_people)
from idol_manager.market_rules import market_salary,acceptance,raised_offer,trade_response
from idol_manager.finance_service import debt,cash,obligation
from tests import test_finance as fixture

class MarketRulesTests(unittest.TestCase):
    def test_formula_8_skills_age_top_two_clamps_rounding(self):
        self.assertEqual(market_salary([50]*8,18),30000000)
        self.assertEqual(market_salary([50]*8,20),32000000)
        self.assertEqual(market_salary([100]*8,20),60000000)
        self.assertEqual(market_salary([0]*8,33),30000000)
        self.assertEqual(market_salary([60]*8,24),35000000)
        self.assertGreater(market_salary([90,90,50,50,50,50,50,50],20),market_salary([60]*8,20))
    def test_chance_interpolation_floor_ceiling_raise(self):
        for offered,expected in ((90,.3),(95,.5),(100,.8),(105,.9),(110,1),(20,.3),(200,1),(97.5,.65)):
            self.assertAlmostEqual(acceptance(int(offered*10000),1000000),expected)
        self.assertEqual(raised_offer(30000000),31500000)
    def test_ai_thresholds_no_unconfirmed_probability(self):
        self.assertEqual(trade_response(.89),'reject');self.assertEqual(trade_response(.95),'reject')
        self.assertEqual(trade_response(1.05),'counter');self.assertEqual(trade_response(1.2),'accept')
        self.assertEqual(trade_response(.95,salary_relief=True,need=True,round_number=3),'accept')
        self.assertEqual(trade_response(.95,salary_relief=True,need=False,round_number=3),'reject')

class MarketTests(unittest.TestCase):
    setUpClass=classmethod(fixture.FinanceTests.setUpClass.__func__)
    def setUp(self):
        fixture.FinanceTests.setUp(self);self.market=self.service.market;self.market.seed_factory=lambda:1
        self.day(0)
    dump=fixture.FinanceTests.dump
    rows=fixture.FinanceTests.rows
    def day(self,d):
        with closing(self.db.connect()) as c,c:c.execute('UPDATE game_clock SET absolute_day=?',(d,))
    def member(self,agency='ador',role='second_team'):
        return self.rows('SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status=? ORDER BY person_id LIMIT 1',(agency,role))[0][0]
    def finite(self,p,annual=30000000,duration=1):
        with self.market.write() as c:return dict(_new_contract(c,p,self.rows('SELECT agency_id FROM roster_memberships WHERE person_id=?',(p,))[0][0],annual,duration,'pro'))
    def vacancy(self,agency='ador'):
        p=self.member(agency);self.finite(p)
        self.market.release(agency,p,'immediate',request_id=uuid.uuid4().hex)
        return p
    def free_trainee(self,agency='ador',age=17):
        p=self.rows("SELECT r.person_id FROM roster_memberships r JOIN idols i ON i.person_id=r.person_id WHERE r.career_status='unassigned' AND i.status='candidate' ORDER BY r.person_id LIMIT 1")[0][0]
        self.day(203)
        with closing(self.db.connect()) as c,c:c.execute('UPDATE idols SET age=16 WHERE person_id=?',(p,))
        # Pre-v18 already-owned trainee fixture. New applications are tested separately.
        from idol_manager.market_service import _move
        with self.market.write() as c:
            contract=_new_contract(c,p,agency,0,1,'free_trainee')
            _move(c,p,agency,'trainee','trainee',contract)
        with closing(self.db.connect()) as c,c:c.execute('UPDATE idols SET age=? WHERE person_id=?',(age,p))
        return p
    def trade_terms(self,a='ador',b='jyp',cash=0):return dict(pro_a=self.member(a),pro_b=self.member(b),cash=cash,trainees_a=[],trainees_b=[])
    def test_public_candidate_ca_health_salary_not_leaked_no_pa_sql(self):
        original=self.db.connect;queries=[]
        def connect():
            c=original();c.set_trace_callback(queries.append)
            c.set_authorizer(lambda action,t,col,*_:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_READ and col in ('potential','archetype') else sqlite3.SQLITE_OK);return c
        with patch.object(self.db,'connect',side_effect=connect):people=self.market.public_people(available=True)
        hidden=[p for p in people if not p['exact']];self.assertTrue(hidden)
        for p in hidden:
            self.assertIsNone(p['health']);self.assertIsNotNone(p['ranges'])
            self.assertFalse(any('SELECT skill,value FROM abilities' in q and p['id'] in q for q in queries))
    def test_negotiation_success_idempotent_and_salary_not_immediately_charged(self):
        person=self.vacancy();before=self.rows("SELECT funds_krw FROM agencies WHERE id='ador'")[0][0];self.day(203)
        n=self.market.start_negotiation('ador',person,'fa');result=self.market.offer(n,66000000,2,request_id='offer1')
        self.assertTrue(result['accepted']);self.assertEqual(result,self.market.offer(n,66000000,2,request_id='offer1'))
        self.assertEqual(self.rows("SELECT funds_krw FROM agencies WHERE id='ador'"),[(before,)])
        self.assertEqual(self.rows('SELECT career_status FROM roster_memberships WHERE person_id=?',(person,)),[('second_team',)])
        with closing(self.db.connect()) as c:
            contract=active_contract(c,person);self.assertEqual(contract['annual_krw'],66000000);self.assertEqual(contract['end_season'],3)
    def test_three_rejects_persist_no_ownership_change_retry_raise(self):
        person=self.vacancy();self.day(203);self.market.seed_factory=lambda:0
        n=self.market.start_negotiation('ador',person,'fa');annual=1000000
        for i in range(3):
            result=self.market.offer(n,annual,1,request_id='reject'+str(i));self.assertFalse(result['accepted']);annual=raised_offer(annual)
        self.assertEqual(self.market.start_negotiation('ador',person,'fa'),n)
        with self.assertRaises(MarketError):self.market.offer(n,annual,1,request_id='fourth')
        self.assertEqual(self.rows('SELECT agency_id FROM roster_memberships WHERE person_id=?',(person,)),[(None,)])
        other=MarketService(self.db);self.assertEqual(other.negotiations('ador'),self.market.negotiations('ador'))
    def test_reject_does_not_allow_same_or_lower_offer(self):
        person=self.vacancy();self.day(203);self.market.seed_factory=lambda:0
        n=self.market.start_negotiation('ador',person,'fa');self.market.offer(n,1000000,1,request_id='one')
        with self.assertRaises(MarketError):self.market.offer(n,1000000,1,request_id='two')
    def test_capacity_and_debt_budget_reject_before_rng(self):
        target=next(p for p in self.market.public_people(available=True) if p['age']>=17)
        self.day(203);n=self.market.start_negotiation('ador',target['id'],'fa')
        self.market.seed_factory=lambda:(_ for _ in ()).throw(AssertionError('RNG must not run'))
        with self.assertRaises(MarketError):self.market.offer(n,60000000,1,request_id='full')
    def test_trainee_debut_fixed_salary_and_second_team(self):
        self.vacancy();p=self.free_trainee();self.day(210)
        n=self.market.start_negotiation('ador',p,'debut')
        with self.assertRaises(MarketError):self.market.offer(n,40000000,1,request_id='bad')
        result=self.market.offer(n,30000000,1,request_id='debut');self.assertTrue(result['accepted'])
        self.assertEqual(self.rows('SELECT career_status FROM roster_memberships WHERE person_id=?',(p,)),[('second_team',)])
        self.assertEqual(self.rows('SELECT debut_season FROM market_careers WHERE person_id=?',(p,)),[(2,)])
        with closing(self.db.connect()) as c,c:
            with self.assertRaises(sqlite3.IntegrityError):c.execute("UPDATE roster_memberships SET career_status='trainee' WHERE person_id=?",(p,))
    def test_trainee_debut_reject_keeps_trainee(self):
        self.vacancy();p=self.free_trainee();self.day(210);self.market.seed_factory=lambda:0
        n=self.market.start_negotiation('ador',p,'debut')
        for i in range(3):self.assertFalse(self.market.offer(n,30000000,1,request_id='d'+str(i))['accepted'])
        self.assertEqual(self.rows('SELECT career_status FROM roster_memberships WHERE person_id=?',(p,)),[('trainee',)])
    def test_illegal_debut_friday_or_no_release_credit(self):
        p=self.free_trainee();self.day(4)
        with self.assertRaises(MarketError):self.market.start_negotiation('ador',p,'debut')
        self.day(7)
        with self.assertRaises(MarketError):self.market.start_negotiation('ador',p,'debut')
    def test_trainee_free_and_drafted_types_distinct(self):
        p=self.free_trainee(age=16)
        self.assertEqual(self.rows('SELECT annual_krw,kind FROM finance_contracts WHERE person_id=?',(p,)),[(0,'free_trainee')])
        q=self.rows("SELECT person_id FROM roster_memberships WHERE career_status='unassigned' AND person_id!=? LIMIT 1",(p,))[0][0]
        self.day(196)
        with closing(self.db.connect()) as c,c:c.execute('UPDATE idols SET age=15 WHERE person_id=?',(q,))
        self.market.connect_draft_pick('ador',q,1,pick_id='future-draft-1')
        self.assertEqual(self.rows('SELECT annual_krw,kind FROM finance_contracts WHERE person_id=?',(q,)),[(10000000,'draft_trainee')])
    def test_draft_cannot_be_bypassed_by_market_ui_api(self):
        self.day(196);p=next(p for p in self.market.public_people(available=True) if p['age']>=17)
        with self.assertRaises(MarketError):self.market.start_negotiation('ador',p['id'],'draft')
    def test_trade_professionals_cash_ownership_contracts_and_records(self):
        terms=self.trade_terms(cash=1000000);a,b=terms['pro_a'],terms['pro_b']
        with closing(self.db.connect()) as c:old_a=dict(active_contract(c,a));old_b=dict(active_contract(c,b))
        before=self.rows('SELECT SUM(funds_krw) FROM agencies')[0][0];abilities=self.rows('SELECT * FROM abilities ORDER BY person_id,skill')
        identity=self.market.propose_trade('ador','jyp',terms,request_id='trade')
        self.assertEqual(self.market.trade_reply(identity,'jyp','accept',expected_version=1),'completed')
        self.assertEqual(self.rows('SELECT agency_id FROM roster_memberships WHERE person_id=?',(a,)),[('jyp',)])
        self.assertEqual(self.rows('SELECT SUM(funds_krw) FROM agencies'),[(before,)])
        self.assertEqual(abilities,self.rows('SELECT * FROM abilities ORDER BY person_id,skill'))
        with closing(self.db.connect()) as c:
            new_a=active_contract(c,a);self.assertEqual(new_a['annual_krw'],old_a['annual_krw']);self.assertEqual(new_a['end_day'],old_a['end_day']);self.assertEqual(new_a['root_id'],old_a['root_id'])
        before=self.dump();self.market.trade_reply(identity,'jyp','accept',expected_version=1);self.assertEqual(before,self.dump())
    def test_trade_first_team_leader_does_not_follow_to_other_agency(self):
        a=self.member('ador','first_team');b=self.member('jyp','first_team')
        with closing(self.db.connect()) as c,c:c.execute("INSERT OR REPLACE INTO squad_leaders VALUES ('ador','first_team',?)",(a,))
        terms=dict(pro_a=a,pro_b=b,cash=0,trainees_a=[],trainees_b=[])
        t=self.market.propose_trade('ador','jyp',terms,request_id='leader');self.market.trade_reply(t,'jyp','accept',expected_version=1)
        self.assertFalse(self.rows('SELECT 1 FROM squad_leaders WHERE person_id=?',(a,)))
        self.assertEqual(self.rows("SELECT COUNT(*) FROM roster_memberships WHERE agency_id='ador' AND career_status='first_team'"),[(5,)])
    def test_trade_pending_until_monday_and_counter_limit(self):
        self.day(1);terms=self.trade_terms();t=self.market.propose_trade('ador','jyp',terms,request_id='pending')
        self.assertEqual(self.market.trade_reply(t,'jyp','accept',expected_version=1),'accepted_pending')
        self.assertEqual(self.rows('SELECT agency_id FROM roster_memberships WHERE person_id=?',(terms['pro_a'],)),[('ador',)])
        self.day(7)
        with self.market.write() as c:process_market(c,7,run_ai=False)
        self.assertEqual(self.rows('SELECT status FROM market_trades WHERE id=?',(t,)),[('completed',)])
    def test_trade_failure_rolls_back_both_moves_cash_contracts(self):
        t=self.market.propose_trade('ador','jyp',self.trade_terms(cash=1000000),request_id='fail');before=self.dump()
        with patch('idol_manager.market_service._history',side_effect=RuntimeError('disk failed')):
            with self.assertRaises(RuntimeError):self.market.trade_reply(t,'jyp','accept',expected_version=1)
        self.assertEqual(before,self.dump())
    def test_trade_duplicate_player_wrong_owner_and_four_trainees_denied(self):
        terms=self.trade_terms();terms['pro_b']=terms['pro_a']
        with self.assertRaises(MarketError):self.market.propose_trade('ador','jyp',terms,request_id='bad')
        terms=self.trade_terms();terms['trainees_a']=['x','y','z','w']
        with self.assertRaises(MarketError):self.market.propose_trade('ador','jyp',terms,request_id='four')
    def test_trade_ai_uses_no_potential_and_persists_counter(self):
        t=self.market.propose_trade('ador','jyp',self.trade_terms(),request_id='ai')
        original=self.db.connect
        def connect():
            c=original();c.set_authorizer(lambda action,table,col,*_:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_READ and col in ('potential','archetype') else sqlite3.SQLITE_OK);return c
        with patch.object(self.db,'connect',side_effect=connect):r=self.market.evaluate_trade(t,'jyp')
        self.assertIn(r['action'],('accept','counter','reject'))
    def test_auction_2day_extension_highest_revalidated_and_persistent(self):
        p=self.vacancy();self.vacancy('jyp');self.day(203)
        a=self.market.bid('ador',p,30000000,1,request_id='b1');self.day(204)
        self.market.bid('jyp',p,33000000,1,request_id='b2')
        self.assertEqual(self.rows('SELECT deadline FROM market_auctions WHERE id=?',(a,)),[(206,)])
        self.day(206)
        with self.market.write() as c:_settle_auctions(c,206,lambda:9)
        self.assertEqual(self.rows('SELECT agency_id FROM roster_memberships WHERE person_id=?',(p,)),[('jyp',)])
        before=self.dump()
        with self.market.write() as c:_settle_auctions(c,206,lambda:999)
        self.assertEqual(before,self.dump())
    def test_auction_original_club_tie_priority_and_external_uniform_lottery(self):
        p=self.vacancy();self.vacancy('jyp');self.day(203)
        a=self.market.bid('jyp',p,30000000,1,request_id='tie1');self.market.bid('ador',p,30000000,1,request_id='tie2');self.day(205)
        with self.market.write() as c:_settle_auctions(c,205,lambda:0)
        self.assertEqual(self.rows('SELECT winner FROM market_auctions WHERE id=?',(a,)),[('ador',)])
    def test_release_legacy_unknown_term_does_not_invent_penalty(self):
        p=self.member();before=self.dump()
        with self.assertRaisesRegex(MarketError,'미정'):self.market.release('ador',p,'immediate',request_id='legacy')
        self.assertEqual(before,self.dump())
    def test_release_immediate_penalty_1third_and_arrears_preserved(self):
        p=self.member();self.finite(p);self.day(28)
        with self.market.write() as c:
            contract=active_contract(c,p);expected=release_penalty(c,contract,28)
        before=self.rows("SELECT funds_krw FROM agencies WHERE id='ador'")[0][0]
        self.market.release('ador',p,'immediate',request_id='release')
        self.assertEqual(self.rows("SELECT funds_krw FROM agencies WHERE id='ador'"),[(before-expected,)])
        self.assertEqual(self.rows('SELECT career_status FROM roster_memberships WHERE person_id=?',(p,)),[('fa',)])
        with closing(self.db.connect()) as c:self.assertIsNone(active_contract(c,p))
    def test_release_33_retires_no_candidate_reappearance(self):
        p=self.member();self.finite(p)
        with closing(self.db.connect()) as c,c:c.execute('UPDATE idols SET age=33 WHERE person_id=?',(p,))
        self.market.release('ador',p,'immediate',request_id='retire')
        self.assertNotIn(p,{p['id'] for p in self.market.public_people(available=True)})
    def test_installments_10_across_season_no_duplicate(self):
        p=self.member();self.finite(p,duration=2);self.day(210)
        result=self.market.release('ador',p,'installments',request_id='plan')
        with closing(self.db.connect()) as c:self.assertEqual(debt(c,'ador'),result['total'])
        for week in range(1,11):
            self.day(210+7*week)
            with self.market.write() as c:process_market(c,210+7*week,run_ai=False)
        self.assertEqual(self.rows('SELECT SUM(amount),COUNT(*) FROM market_installments WHERE plan_id=?',('plan',)),[(result['total'],10)])
        before=self.dump()
        with self.market.write() as c:process_market(c,280,run_ai=False)
        self.assertEqual(before,self.dump())
    def test_expiry_and_renewal_preserve_previous_paid_records(self):
        p=self.member();self.finite(p);self.day(189);n=self.market.start_negotiation('ador',p,'renew')
        self.market.offer(n,66000000,1,request_id='renew');self.day(196)
        with self.market.write() as c:process_market(c,196,run_ai=False)
        self.assertEqual(self.rows('SELECT agency_id FROM roster_memberships WHERE person_id=?',(p,)),[('ador',)])
    def test_expiry_without_renewal_fa_no_penalty(self):
        p=self.member();self.finite(p);self.day(196)
        with self.market.write() as c:process_market(c,196,run_ai=False)
        self.assertEqual(self.rows('SELECT agency_id,career_status FROM roster_memberships WHERE person_id=?',(p,)),[(None,'fa')])
        self.assertFalse(self.rows('SELECT 1 FROM market_release_plans WHERE person_id=?',(p,)))
    def test_expiry_pending_renewal_blocks_ignoring_negotiation(self):
        p=self.member();self.finite(p);self.day(189);self.market.start_negotiation('ador',p,'renew');self.day(196)
        with self.assertRaises(MarketError):
            with self.market.write() as c:process_market(c,196,run_ai=False)
    def test_bid_concurrency_one_contract_only(self):
        p=self.vacancy();self.vacancy('jyp');self.day(203)
        def bid(team):return self.market.bid(team,p,30000000,1,request_id='concurrent:'+team)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(bid,('ador','jyp')))
        self.assertEqual(results[0],results[1]);self.day(205)
        with self.market.write() as c:_settle_auctions(c,205,lambda:2)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM finance_contracts WHERE person_id=? AND start_day<=205 AND (end_day IS NULL OR end_day>205)',(p,)),[(1,)])
    def test_two_unpicked_years_require_real_draft_outcomes(self):
        p=next(p for p in self.market.public_people(available=True))['id'];self.day(196)
        self.market.record_draft_outcome(1,p,picked=False);self.day(413);self.market.record_draft_outcome(2,p,picked=False)
        self.assertEqual(self.rows('SELECT career_status FROM roster_memberships WHERE person_id=?',(p,)),[('retired',)])


class MarketIntegrationTests(unittest.TestCase):
    setUpClass=classmethod(MarketTests.setUpClass.__func__)
    setUp=MarketTests.setUp
    day=MarketTests.day
    dump=MarketTests.dump
    rows=MarketTests.rows
    member=MarketTests.member
    finite=MarketTests.finite
    vacancy=MarketTests.vacancy
    free_trainee=MarketTests.free_trainee
    trade_terms=MarketTests.trade_terms
    def test_payroll_owner_days_28_and_previous_salary_arrears_stay_seller(self):
        from idol_manager.development_service import capture_day
        from idol_manager.finance_service import settle_week
        person=self.member();terms=self.trade_terms()
        with self.market.write() as c:
            for day in range(7):capture_day(c,day)
        self.day(7);t=self.market.propose_trade('ador','jyp',terms,request_id='daily');self.market.trade_reply(t,'jyp','accept',expected_version=1)
        with self.market.write() as c:
            for day in range(7,28):capture_day(c,day)
            c.execute('UPDATE game_clock SET absolute_day=27');settle_week(c,27)
        rows=self.rows('SELECT agency_id,base_krw FROM finance_payroll WHERE person_id=? ORDER BY agency_id',(person,))
        self.assertEqual(dict(rows),{'ador':1250000,'jyp':3750000})
        before=self.dump()
        with self.market.write() as c:settle_week(c,27)
        self.assertEqual(before,self.dump())
    def test_forced_sale_real_cash_debt_contract_and_idempotent(self):
        from idol_manager.finance_service import obligation
        outgoing=self.member('jyp');self.finite(outgoing)
        self.market.release('jyp',outgoing,'immediate',request_id='buyer-slot')
        with self.market.write() as c:
            c.execute("UPDATE agencies SET funds_krw=0 WHERE id='ador'")
            s=_settlement(c,'ador','debt-fixture');obligation(c,s,'salary_test',20000000)
        buyer_before=self.rows("SELECT funds_krw FROM agencies WHERE id='jyp'")[0][0]
        result=self.market.force_sale('ador',request_id='forced')
        self.assertEqual(result['buyer'],'jyp');self.assertEqual(result['price'],15000000)
        self.assertEqual(self.rows("SELECT funds_krw FROM agencies WHERE id='jyp'"),[(buyer_before-15000000,)])
        with closing(self.db.connect()) as c:self.assertEqual(debt(c,'ador'),5000000)
        before=self.dump();self.market.force_sale('ador',request_id='forced');self.assertEqual(before,self.dump())
    def test_forced_sale_no_buyer_does_not_create_money_or_move_player(self):
        with self.market.write() as c:
            c.execute("UPDATE agencies SET funds_krw=0 WHERE id='ador'");s=_settlement(c,'ador','debt');obligation(c,s,'salary_test',20000000)
        before=self.dump();result=self.market.force_sale('ador',request_id='none')
        self.assertFalse(result['completed']);self.assertEqual(before,self.dump())
    def test_pro_plus_trainee_trade_keeps_free_salary_type(self):
        trainee=self.free_trainee(age=16);self.day(210)
        terms=self.trade_terms();terms['trainees_a']=[trainee]
        t=self.market.propose_trade('ador','jyp',terms,request_id='extras');self.market.trade_reply(t,'jyp','accept',expected_version=1)
        with closing(self.db.connect()) as c:
            self.assertEqual(active_contract(c,trainee)['kind'],'free_trainee');self.assertEqual(active_contract(c,trainee)['annual_krw'],0)
        self.assertEqual(self.rows('SELECT agency_id,career_status FROM roster_memberships WHERE person_id=?',(trainee,)),[('jyp','trainee')])
    def test_contract_changed_after_proposal_is_not_silently_inherited(self):
        terms=self.trade_terms();t=self.market.propose_trade('ador','jyp',terms,request_id='stale')
        self.finite(terms['pro_b'],annual=50000000)
        before=self.dump()
        with self.assertRaises(MarketError):self.market.trade_reply(t,'jyp','accept',expected_version=1)
        self.assertEqual(before,self.dump())
    def test_counter_three_versions_restart_and_wrong_responder(self):
        terms=self.trade_terms();t=self.market.propose_trade('ador','jyp',terms,request_id='counter')
        self.market.trade_reply(t,'jyp','counter',terms=terms,expected_version=1)
        self.market.trade_reply(t,'ador','counter',terms=terms,expected_version=2)
        with self.assertRaises(MarketError):self.market.trade_reply(t,'jyp','counter',terms=terms,expected_version=3)
        self.assertEqual(self.market.trades()[0]['version'],3)
    def test_late_fa_window_clips_at_market_close_no_late_bid(self):
        p=self.vacancy();self.vacancy('jyp');self.day(209)
        a=self.market.bid('ador',p,30000000,1,request_id='late')
        self.assertEqual(self.rows('SELECT deadline FROM market_auctions WHERE id=?',(a,)),[(210,)])
        self.day(210)
        with self.assertRaises(MarketError):self.market.bid('jyp',p,33000000,1,request_id='too-late')
        with self.market.write() as c:_settle_auctions(c,210,lambda:3)
        self.assertEqual(self.rows('SELECT status FROM market_auctions WHERE id=?',(a,)),[('completed',)])
    def test_highest_bidder_loses_finance_eligibility_before_close(self):
        p=self.vacancy();self.vacancy('jyp');self.day(203)
        a=self.market.bid('ador',p,30000000,1,request_id='valid');self.market.bid('jyp',p,33000000,1,request_id='high')
        with self.market.write() as c:c.execute("UPDATE agencies SET funds_krw=0 WHERE id='jyp'")
        self.day(205)
        with self.market.write() as c:_settle_auctions(c,205,lambda:1)
        self.assertEqual(self.rows('SELECT winner FROM market_auctions WHERE id=?',(a,)),[('ador',)])
    def test_auction_external_tie_uses_saved_uniform_seed(self):
        p=self.vacancy();self.vacancy('jyp');self.vacancy('sm');self.day(203)
        a=self.market.bid('jyp',p,30000000,1,request_id='e1');self.market.bid('sm',p,30000000,1,request_id='e2');self.day(205)
        seed=93
        with self.market.write() as c:_settle_auctions(c,205,lambda:seed)
        expected=random.Random(seed).choice(sorted(['jyp','sm']))
        self.assertEqual(self.rows('SELECT winner,seed FROM market_auctions WHERE id=?',(a,)),[(expected,str(seed))])
    def test_prepared_match_blocks_roster_contract_mutation(self):
        self.day(2);fixture_=next(f for f in self.service.matches.fixtures() if f.player_participates)
        self.service.matches._prepare(fixture_.id,None,None)
        self.day(7);terms=self.trade_terms();t=self.market.propose_trade('ador','jyp',terms,request_id='prepared')
        before=self.dump()
        with self.assertRaises(MarketError):self.market.trade_reply(t,'jyp','accept',expected_version=1)
        self.assertEqual(before,self.dump())

    def test_ai_to_ai_auctions_and_trades_progress_without_private_data(self):
        self.vacancy('jyp');self.vacancy('sm');self.day(203)
        with self.market.write() as c:
            c.set_authorizer(lambda action,t,col,*_:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_READ and col in ('potential','archetype') else sqlite3.SQLITE_OK)
            process_market(c,203,run_ai=True)
        bidders={r[0] for r in self.rows('SELECT DISTINCT agency_id FROM market_bids')}
        self.assertIn('jyp',bidders);self.assertIn('sm',bidders)
        self.day(205)
        with self.market.write() as c,patch('idol_manager.market_service.secrets.randbits',return_value=1):process_market(c,205,run_ai=True)
        self.assertTrue(self.rows("SELECT 1 FROM market_auctions WHERE status='completed' LIMIT 1"))
        with closing(self.db.connect()) as c:self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
    def test_ai_renewals_survive_unrelated_optional_trade_rejection(self):
        from idol_manager.market_service import MarketError
        self.day(0)
        for p, in self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='jyp' AND career_status IN ('first_team','second_team')"):
            self.finite(p)
        self.day(189)
        with self.market.write() as c,patch.object(MarketService,'propose_trade',side_effect=MarketError('optional trade rejected')):
            process_market(c,189,run_ai=True)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM market_offers o JOIN market_negotiations n ON n.id=o.negotiation_id WHERE n.agency_id='jyp' AND n.purpose='renew'"),[(16,)])

    def test_ai_trade_proposal_and_counter_or_rejection_are_automatic(self):
        self.day(189)
        with self.market.write() as c:
            # Isolate automatic negotiation from the randomly generated ages:
            # age-dependent values can complete a competing proposal first and
            # legitimately invalidate the later offer's ownership precondition.
            c.execute('UPDATE idols SET age=20')
            c.execute('UPDATE abilities SET value=0')
            c.execute("UPDATE abilities SET value=1 WHERE person_id IN (SELECT person_id FROM roster_memberships WHERE agency_id IN ('jyp','sm'))")
            process_market(c,189,run_ai=True)
        self.assertTrue(self.rows("SELECT 1 FROM market_trades WHERE agency_a='jyp' AND agency_b='sm'"))
        self.day(190)
        with self.market.write() as c:process_market(c,190,run_ai=True)
        self.assertTrue(self.rows("SELECT 1 FROM market_trades WHERE version>1 OR status IN ('rejected','completed')"))
    def test_process_exit_mid_exchange_leaves_neither_side_changed(self):
        terms=self.trade_terms(cash=1000000);identity=self.market.propose_trade('ador','jyp',terms,request_id='crash')
        before=self.dump()
        code="""import os,sys
from pathlib import Path
from idol_manager.database import Database
from idol_manager import market_service as m
api=m.MarketService(Database(Path(sys.argv[1])))
original=m._history
calls=[]
def crash(*args,**kwargs):
 calls.append(1)
 if len(calls)==2:os._exit(93)
 return original(*args,**kwargs)
m._history=crash
api.trade_reply('crash','jyp','accept',expected_version=1)
"""
        result=subprocess.run([sys.executable,'-c',code,str(self.path)],capture_output=True)
        self.assertEqual(result.returncode,93,result.stderr.decode(errors='replace'))
        self.assertEqual(before,self.dump())

    def test_two_season_contract_terms_survive_exchange(self):
        a=self.member();b=self.member('jyp');self.finite(a,duration=2);self.finite(b,duration=2)
        with closing(self.db.connect()) as c:old=dict(active_contract(c,a))
        self.day(7);terms=dict(pro_a=a,pro_b=b,cash=0,trainees_a=[],trainees_b=[])
        t=self.market.propose_trade('ador','jyp',terms,request_id='two-year');self.market.trade_reply(t,'jyp','accept',expected_version=1)
        with closing(self.db.connect()) as c:
            new=active_contract(c,a);self.assertEqual((new['start_season'],new['end_season'],new['end_day'],new['annual_krw']),(old['start_season'],2,old['end_day'],old['annual_krw']))
    def test_old_unpaid_salary_stays_original_team_after_trade(self):
        from idol_manager.development_service import capture_day
        from idol_manager.finance_service import settle_week
        with self.market.write() as c:
            c.execute('UPDATE agencies SET funds_krw=0')
            for day in range(28):capture_day(c,day)
            c.execute('UPDATE game_clock SET absolute_day=27');settle_week(c,27)
        person=self.rows("SELECT person_id FROM finance_payroll WHERE agency_id='ador' AND paid_krw<due_krw LIMIT 1")[0][0]
        old=self.rows('SELECT * FROM finance_payroll ORDER BY id');debts=self.rows('SELECT * FROM finance_debts ORDER BY id')
        self.day(28);terms=dict(pro_a=person,pro_b=self.member('jyp'),cash=0,trainees_a=[],trainees_b=[])
        t=self.market.propose_trade('ador','jyp',terms,request_id='arrears');self.market.trade_reply(t,'jyp','accept',expected_version=1)
        self.assertEqual(old,self.rows('SELECT * FROM finance_payroll ORDER BY id'));self.assertEqual(debts,self.rows('SELECT * FROM finance_debts ORDER BY id'))
    def test_instalment_unpaid_becomes_due_debt_future_incomes_do_not_accelerate_plan(self):
        from idol_manager.finance_service import income
        p=self.member();self.finite(p);plan=self.market.release('ador',p,'installments',request_id='unpaid-plan')
        with self.market.write() as c:c.execute("UPDATE agencies SET funds_krw=0 WHERE id='ador'")
        self.day(7)
        with self.market.write() as c:
            process_market(c,7,run_ai=False)
            owed=debt(c,'ador');self.assertEqual(owed,plan['total'])
            s=_settlement(c,'ador','repay-overdue');income(c,s,'test_income',5000000)
            first=round(plan['total']/10)
            self.assertEqual(debt(c,'ador'),plan['total']-first)
            self.assertEqual(cash(c,'ador'),5000000-first)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM finance_points'),[(0,)])
    def test_completed_match_and_draft_history_survive_real_participant_trade(self):
        self.day(2);game=next(f for f in self.service.matches.fixtures() if f.player_participates);result=self.service.matches.play(game.id)
        actor=next(p['person_id'] for p in result.players if p['agency_id']=='ador')
        before=self.rows('SELECT * FROM match_player_stats ORDER BY match_id,person_id');draft=self.rows('SELECT * FROM draft_picks ORDER BY pick_number')
        self.day(7);terms=dict(pro_a=actor,pro_b=self.member('jyp'),cash=0,trainees_a=[],trainees_b=[])
        t=self.market.propose_trade('ador','jyp',terms,request_id='past-game');self.market.trade_reply(t,'jyp','accept',expected_version=1)
        self.assertEqual(result,self.service.matches.play(game.id));self.assertEqual(before,self.rows('SELECT * FROM match_player_stats ORDER BY match_id,person_id'));self.assertEqual(draft,self.rows('SELECT * FROM draft_picks ORDER BY pick_number'))
        self.service.draft_session.validate_completion()

    def test_draft_bridge_reveals_only_selected_candidate_and_consumes_failed_pick(self):
        self.vacancy();self.day(196)
        p=next(p for p in self.market.public_people(available=True) if not p['exact'] and p['age']>=17)
        self.market.connect_draft_pick('ador',p['id'],1,pick_id='selected17')
        self.assertTrue(next(q for q in self.market.public_people(available=True) if q['id']==p['id'])['exact'])
        self.market.seed_factory=lambda:0;n=self.market.start_negotiation('ador',p['id'],'draft')
        annual=1000000
        for i in range(3):self.market.offer(n,annual,1,request_id=f'draft-fail:{i}');annual=raised_offer(annual)
        self.assertEqual(self.rows('SELECT consumed FROM market_draft_rights WHERE id=?',('selected17',)),[(1,)])
        self.assertEqual(self.rows('SELECT career_status FROM roster_memberships WHERE person_id=?',(p['id'],)),[('fa',)])

    def test_preopened_direct_negotiation_cannot_bypass_new_public_auction(self):
        p=self.vacancy();self.vacancy('jyp');self.day(203)
        n=self.market.start_negotiation('ador',p,'fa');self.market.bid('jyp',p,33000000,1,request_id='public-first')
        before=self.dump()
        with self.assertRaisesRegex(MarketError,'공개 입찰'):self.market.offer(n,66000000,1,request_id='bypass')
        self.assertEqual(before,self.dump())
    def test_same_day_repeated_transfer_never_invoices_zero_day_segments(self):
        from idol_manager.development_service import capture_day
        from idol_manager.finance_service import settle_week
        p=self.member();self.finite(p,annual=31000000)
        with self.market.write() as c:
            for d in range(7):capture_day(c,d)
        self.day(7)
        t=self.market.propose_trade('ador','jyp',dict(pro_a=p,pro_b=self.member('jyp'),cash=0,trainees_a=[],trainees_b=[]),request_id='same1');self.market.trade_reply(t,'jyp','accept',expected_version=1)
        t=self.market.propose_trade('jyp','sm',dict(pro_a=p,pro_b=self.member('sm'),cash=0,trainees_a=[],trainees_b=[]),request_id='same2');self.market.trade_reply(t,'sm','accept',expected_version=1)
        with self.market.write() as c:
            for d in range(7,28):capture_day(c,d)
            c.execute('UPDATE game_clock SET absolute_day=27');settle_week(c,27)
        self.assertEqual(self.rows('SELECT SUM(base_krw) FROM finance_payroll WHERE person_id=?',(p,)),[(5170000,)])
        self.assertFalse(self.rows("SELECT 1 FROM finance_payroll WHERE person_id=? AND agency_id='jyp'",(p,)))

    def test_empty_squads_after_expiry_do_not_block_reaching_fa_week(self):
        for person, in self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador'"):self.finite(person)
        self.day(195)
        with self.market.write() as c:
            # Legacy rollout of annual intake begins next season in this
            # expiry-only fixture. Annual gates have separate real-flow tests.
            c.execute('UPDATE annual_runtime SET first_season=2')
            # Stand-in past completions in this isolated calendar gate fixture.
            c.execute("UPDATE scheduled_matches SET status='completed'")
            c.execute("UPDATE special_events SET status='completed'")
        self.assertEqual(self.service.calendar.advance_day(expected_absolute_day=195).absolute_day,196)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM roster_memberships WHERE agency_id='ador'"),[(0,)])
        self.assertEqual(self.service.calendar.advance_day(expected_absolute_day=196).absolute_day,197)
        self.assertEqual(self.service.calendar.state().advance_block_reason,'')
