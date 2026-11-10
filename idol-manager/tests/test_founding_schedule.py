"""Stage calendar checks on synthetic copied saves; never opens user slots."""
from contextlib import closing
import sqlite3,unittest
from unittest.mock import patch
from idol_manager.database import Database
from idol_manager.config import ROOT
from idol_manager.calendar_service import CalendarService,CalendarError
from idol_manager.market_service import MarketService,MarketError
from idol_manager.trainee_recruitment import RecruitmentService,RecruitmentError,finalize,submit,round_info
from idol_manager.squads import SquadError
from tests import test_founding_recruitment as fixture

class FoundingScheduleTests(unittest.TestCase):
    protocol=2
    setUpClass=classmethod(fixture.FoundingTests.setUpClass.__func__)
    setUp=fixture.FoundingTests.setUp
    rows=fixture.FoundingTests.rows;dump=fixture.FoundingTests.dump
    def advance(self):
        d=self.calendar.state().date.absolute_day
        return self.calendar.advance_day(expected_absolute_day=d)
    def tuesday(self):
        self.advance()
        for n in self.market.negotiations('ador'):
            if n['status']=='open':
                p=next(p for p in self.market.public_people() if p['id']==n['person_id'])
                self.market.offer(n['id'],p['market']*11//10,1,request_id='fixed:'+n['id'])
    def at(self,day):
        if self.calendar.state().date.absolute_day==-7:self.tuesday()
        while self.calendar.state().date.absolute_day<day:self.advance()
    def test_monday_draft_rights_tuesday_contracts(self):
        self.assertEqual(self.rows('SELECT COUNT(*) FROM draft_picks')[0][0],160)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM finance_contracts')[0][0],0)
        self.assertTrue(self.market.action_reason('ador','founding'))
        self.advance()
        self.assertEqual(self.calendar.state().date.absolute_day,-6)
        self.assertEqual(len([n for n in self.market.negotiations('ador') if n['status']=='open']),3)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM squad_formations')[0][0],0)
        self.assertEqual(self.rows('''SELECT COUNT(*) FROM finance_contracts x JOIN market_terms t ON t.contract_id=x.id
          JOIN draft_picks p ON p.person_id=x.person_id JOIN draft_turns k USING(pick_number)
          WHERE k.round_number>=4 AND x.annual_krw=30000000 AND t.start_season=1 AND t.end_season=1''')[0][0],130)
        with self.assertRaises(CalendarError):self.advance()
    def test_tuesday_three_rejections_go_fa(self):
        self.advance();n=next(n for n in self.market.negotiations('ador') if n['status']=='open')
        basis=next(p['market'] for p in self.market.public_people() if p['id']==n['person_id'])
        # A deterministic high roll fails three legal 5%-raised offers.
        self.market.seed_factory=lambda:2
        annual=basis*9//10
        for i in range(3):
            with patch('idol_manager.market_service.random.Random') as factory:
                factory.return_value.random.return_value=.999
                self.market.offer(n['id'],annual,1,request_id=f'fail:{i}')
            from idol_manager.market_rules import raised_offer
            annual=raised_offer(annual)
        self.assertEqual(self.rows('SELECT status FROM founding_contracts WHERE person_id=?',(n['person_id'],))[0][0],'failed')
        self.assertEqual(self.rows('SELECT agency_id,career_status FROM roster_memberships WHERE person_id=?',(n['person_id'],))[0],(None,'fa'))
    def test_two_independent_application_rounds_and_saved_draw(self):
        self.at(-5);ids=[p.id for p in self.recruitment.candidates()[:3]]
        for n in range(3):self.assertEqual(self.recruitment.apply('ador',ids[:n])['count'],n)
        with self.assertRaises(RecruitmentError):self.recruitment.apply('ador',ids)
        self.recruitment.apply('jyp',[ids[0]])
        with closing(self.db.connect()) as c,c:
            submit(c,round_info(c)['key'],policy=lambda candidates,rng:())
        self.assertTrue(self.recruitment.state('ador')['submitted'])
        self.assertEqual(self.recruitment.state('ador')['results'],[])
        self.assertIsNone(self.rows('SELECT agency_id FROM roster_memberships WHERE person_id=?',(ids[0],))[0][0])
        with self.assertRaises(RecruitmentError):self.recruitment.apply('ador',[])
        self.advance();results=self.recruitment.state('ador')['results']
        self.assertEqual(results[0]['applicants'],['ador','jyp'])
        self.assertIn(results[0]['winner'],['ador','jyp'])
        before=self.dump()
        with closing(self.db.connect()) as c,c:self.assertEqual(finalize(c,-21),results)
        self.assertEqual(before,self.dump())
        self.assertEqual(RecruitmentService(Database(self.path)).state('ador')['results'],results)
        self.advance();self.assertEqual(self.calendar.state().date.absolute_day,-3)
        self.assertEqual(self.recruitment.state('ador')['count'],0)
        self.recruitment.apply('ador',[p.id for p in self.recruitment.candidates()[:2]])
        self.advance();self.assertTrue(self.recruitment.state('ador')['closed'])
        self.assertEqual(self.recruitment.state('ador')['round_number'],2)
    def test_solo_lottery_and_atomic_failure(self):
        self.at(-5);person=self.recruitment.candidates()[0].id
        self.recruitment.apply('ador',[person])
        with closing(self.db.connect()) as c,c:submit(c,-21,policy=lambda candidates,rng:())
        with closing(self.db.connect()) as c,c:
            c.execute("CREATE TRIGGER fail_trainee BEFORE INSERT ON trainee_results BEGIN SELECT RAISE(ABORT,'test save failure'); END")
        before=self.dump()
        with self.assertRaises(sqlite3.IntegrityError):self.advance()
        self.assertEqual(before,self.dump())
        with closing(self.db.connect()) as c,c:c.execute('DROP TRIGGER fail_trainee')
        self.advance();self.assertEqual(self.recruitment.state('ador')['results'][0]['winner'],'ador')
    def test_fa_bid_keeps_two_days_and_auto_settles_on_rest_day(self):
        self.at(-4);person=self.recruitment.candidates()[0].id
        # One failed top contract creates a real vacancy, never invented players.
        own=self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador' LIMIT 1")[0][0]
        with closing(self.db.connect()) as c,c:c.execute("UPDATE roster_memberships SET agency_id=NULL,career_status='fa' WHERE person_id=?",(own,))
        auction=self.market.bid('ador',person,50000000,1,request_id='bid-thu')
        self.assertEqual(self.rows('SELECT deadline FROM market_auctions WHERE id=?',(auction,))[0][0],-2)
        with self.assertRaises(RecruitmentError):self.recruitment.apply('ador',[person])
        self.advance();self.assertNotIn(person,[p.id for p in self.recruitment.candidates()])
        self.advance();self.assertEqual(self.rows('SELECT status FROM market_auctions WHERE id=?',(auction,))[0][0],'completed')
    def test_new_week_then_roster_then_first_wednesday(self):
        abilities=self.rows('SELECT * FROM abilities ORDER BY person_id,skill');picks=self.rows('SELECT * FROM draft_picks ORDER BY pick_number')
        self.at(-1)
        self.assertTrue(self.market.action_reason('ador','fa'))
        self.advance();self.assertEqual(self.calendar.state().date.absolute_day,0)
        with self.assertRaises(CalendarError):self.advance()
        ids=[m.id for m in self.squads.snapshot().members if m.squad in ('pro_pending','first_team','second_team')][:5]
        self.squads.confirm_initial(ids)
        for role in ('first_team','second_team'):
            s=self.squads.snapshot();self.squads.set_leader(role,next(m.id for m in s.members if m.squad==role),expected_revision=s.revision)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM squad_formations')[0][0],10)
        self.advance();self.advance()
        self.assertEqual(self.calendar.state().date.absolute_day,2)
        self.assertGreater(self.calendar.state().unprocessed_count,0)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM scheduled_matches')[0][0],585)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM special_events')[0][0],6)
        self.assertEqual(abilities,self.rows('SELECT * FROM abilities ORDER BY person_id,skill'))
        self.assertEqual(picks,self.rows('SELECT * FROM draft_picks ORDER BY pick_number'))
        self.assertEqual(self.rows('SELECT COUNT(*) FROM development_settlements')[0][0],0)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM finance_payroll')[0][0],0)
        from idol_manager.service import GameService
        service=GameService(ROOT,self.path)
        match=service.matches.fixtures()[0]
        service.matches.play(match.id)
        self.assertEqual(self.rows('SELECT status FROM scheduled_matches WHERE id=?',(match.id,))[0][0],'completed')
        self.assertEqual(self.rows('SELECT COUNT(*) FROM match_results WHERE match_id=?',(match.id,))[0][0],1)
    def test_early_formation_and_wrong_days_blocked(self):
        self.tuesday()
        with self.assertRaises(SquadError):self.squads.confirm_initial([m.id for m in self.squads.snapshot().members[:5]])
        for purpose in ('renew','fa','trainee','trade','release'):self.assertTrue(self.market.action_reason('ador',purpose))
        with self.assertRaises(RecruitmentError):self.recruitment.apply('ador',[])

    def test_thirteen_real_contracts_can_form_without_invented_players(self):
        self.advance()
        for n in self.market.negotiations('ador'):
            if n['status']=='open':self.market.abandon(n['id'],'ador')
        self.at(0)
        members=[m for m in self.squads.snapshot().members if m.squad in ('pro_pending','first_team','second_team')]
        self.assertEqual(len(members),13)
        self.squads.confirm_initial([m.id for m in members[:5]])
        for role in ('first_team','second_team'):
            s=self.squads.snapshot();self.squads.set_leader(role,next(m.id for m in s.members if m.squad==role),expected_revision=s.revision)
        self.assertEqual(self.rows("SELECT career_status,COUNT(*) FROM roster_memberships WHERE agency_id='ador' AND career_status IN ('first_team','second_team') GROUP BY career_status"),[('first_team',5),('second_team',8)])
        self.advance()

    def test_saturday_auction_survives_sunday_and_closes_regular_monday(self):
        self.advance()
        n=next(n for n in self.market.negotiations('ador') if n['status']=='open')
        self.market.abandon(n['id'],'ador')
        for other in self.market.negotiations('ador'):
            if other['status']=='open':
                basis=next(p['market'] for p in self.market.public_people() if p['id']==other['person_id'])
                self.market.offer(other['id'],basis*11//10,1,request_id='sat:'+other['id'])
        self.at(-2);person=self.recruitment.candidates()[0].id
        identity=self.market.bid('ador',person,60000000,1,request_id='bid-sat')
        self.assertEqual(self.rows('SELECT deadline FROM market_auctions WHERE id=?',(identity,))[0][0],0)
        self.advance();self.assertEqual(self.rows('SELECT status FROM market_auctions WHERE id=?',(identity,))[0][0],'open')
        with self.assertRaises(MarketError):self.market.bid('ador',person,61000000,1,request_id='sunday-bid')
        self.advance();self.assertEqual(self.rows('SELECT status FROM market_auctions WHERE id=?',(identity,))[0][0],'completed')
        self.assertEqual(self.rows('SELECT agency_id FROM roster_memberships WHERE person_id=?',(person,))[0][0],'ador')

    def test_ai_sheets_no_hidden_reads_and_conflict_recheck(self):
        self.at(-5);person=self.recruitment.candidates()[0].id
        self.recruitment.apply('ador',[person])
        with closing(self.db.connect()) as c,c:
            c.set_authorizer(lambda a,t,col,*_:sqlite3.SQLITE_DENY if a==sqlite3.SQLITE_READ and (col in ('potential','archetype') or t=='annual_secrets') else sqlite3.SQLITE_OK)
            submit(c,-21)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM trainee_sheets WHERE absolute_day=-21')[0][0],10)
        self.assertTrue(all(n<=2 for n, in self.rows('SELECT COUNT(*) FROM trainee_applications WHERE absolute_day=-21 GROUP BY agency_id')))
        with closing(self.db.connect()) as c,c:c.execute("UPDATE roster_memberships SET agency_id='jyp',career_status='trainee' WHERE person_id=?",(person,))
        self.advance()
        result=next(r for r in self.recruitment.state('ador')['results'] if r['person_id']==person)
        self.assertEqual(result['status'],'ineligible')
        self.assertEqual(self.rows('SELECT agency_id FROM roster_memberships WHERE person_id=?',(person,))[0][0],'jyp')

    def test_v18_backup_keeps_clock_and_contracts(self):
        self.tuesday()
        with closing(self.db.connect()) as c,c:
            for t in ('ai_trade_messages','ai_trade_windows','ai_trade_checks'):c.execute('DROP TABLE '+t)
            c.execute('DROP TABLE trainee_rounds');c.execute('ALTER TABLE founding_setup DROP COLUMN protocol');c.execute('PRAGMA user_version=18')
            before={t:[tuple(r) for r in c.execute('SELECT * FROM '+t)] for t in ('game_clock','founding_setup','founding_contracts','finance_contracts','abilities','draft_picks','agencies')}
        upgraded=Database(self.path);self.assertTrue(upgraded.last_backup_path.is_file())
        with closing(upgraded.connect()) as c:
            from idol_manager.migrations import SCHEMA_VERSION
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],SCHEMA_VERSION)
            self.assertEqual(c.execute('SELECT protocol FROM founding_setup').fetchone()[0],1)
            for t,rows in before.items():
                actual=[tuple(r) for r in c.execute('SELECT '+('game_id,status,prep_day' if t=='founding_setup' else '*')+' FROM '+t)]
                self.assertEqual(rows,actual,t)
            self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())

class FoundingUITests(unittest.TestCase):
    protocol=2
    setUpClass=classmethod(fixture.FoundingTests.setUpClass.__func__)
    setUp=fixture.FoundingTests.setUp
    rows=fixture.FoundingTests.rows;dump=fixture.FoundingTests.dump
    advance=FoundingScheduleTests.advance;tuesday=FoundingScheduleTests.tuesday;at=FoundingScheduleTests.at
    def test_stage_buttons_and_capture(self):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM','windows')
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from idol_manager.service import GameService
        from idol_manager.ui.main_window import MainWindow
        app=QApplication.instance() or QApplication([])
        w=MainWindow(GameService(ROOT,self.path));self.addCleanup(w.close)
        w.resize(1440,900);w.show();w.show_market();page=w.market_page
        QTest.qWait(40);self.assertFalse(page.recruit_button.isEnabled());self.assertFalse(page.bid_button.isEnabled())
        self.at(-5);page.reload();page.tabs.setCurrentIndex(5);w.refresh_calendar();QTest.qWait(40)
        self.assertTrue(page.recruit_button.isEnabled());self.assertFalse(page.renew_button.isEnabled())
        root=ROOT/'reports/founding_schedule';root.mkdir(exist_ok=True)
        w.grab().save(str(root/'wednesday.png'))
        self.advance();page.reload();w.refresh_calendar();QTest.qWait(40)
        self.assertTrue(page.bid_button.isEnabled());self.assertFalse(page.recruit_button.isEnabled())
        w.grab().save(str(root/'thursday.png'))
        self.at(0);page.reload();w.refresh_calendar();QTest.qWait(40)
        self.assertTrue(page.bid_button.isEnabled());self.assertTrue(page.recruit_button.isEnabled())
        self.assertTrue(page.trade_send_button.isEnabled());self.assertTrue(page.release_button.isEnabled());self.assertFalse(page.renew_button.isEnabled())
        w.grab().save(str(root/'regular_monday.png'))

if __name__=='__main__':unittest.main()
