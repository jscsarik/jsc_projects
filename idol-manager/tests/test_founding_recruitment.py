"""New founding flow; every test uses synthetic people and a disposable database."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json,random,sqlite3,tempfile,unittest
from unittest.mock import patch
from idol_manager.database import Database
from idol_manager.domain import Person
from idol_manager.config import ROOT,load_settings
from idol_manager.draft import DraftEngine
from idol_manager.draft_session import DraftSession
from idol_manager.calendar_service import CalendarService,CalendarError
from idol_manager.game_clock import current_game_date,GameDate,DAYS_PER_SEASON
from idol_manager.market_service import MarketService,_move
from idol_manager.squads import SquadService,SquadError
from idol_manager.trainee_recruitment import RecruitmentService,RecruitmentError,finalize

class FoundingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        cls.base=Path(cls.temp.name)/'base.sqlite3';db=Database(cls.base)
        db.create_game(tuple(Person(f'p{i}',f'후보{i}',f'후보{i}',f'missing/{i}.png') for i in range(310)),load_settings(),random.Random(12),founding_protocol=getattr(cls,'protocol',1))
        e=DraftEngine(db);DraftSession(e).select_agency('ador');e.start(rng=random.Random(2))
        for n in range(160):e.pick(e.state().next_turn.agency_id,e.available_candidates()[0].id,expected_pick_number=n+1)
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/'복사본.sqlite3'
        with closing(sqlite3.connect(self.base)) as src,closing(sqlite3.connect(self.path)) as dst:src.backup(dst)
        self.db=Database(self.path);self.calendar=CalendarService(self.db,root=ROOT);self.market=MarketService(self.db)
        self.squads=SquadService(self.db);self.recruitment=RecruitmentService(self.db)
    def rows(self,sql,args=()):
        with closing(self.db.connect()) as c:return [tuple(r) for r in c.execute(sql,args)]
    def dump(self):
        with closing(self.db.connect()) as c:return list(c.iterdump())
    def ready(self):
        for n in self.market.negotiations('ador'):
            if n['status']=='open':
                p=next(p for p in self.market.public_people() if p['id']==n['person_id'])
                self.market.offer(n['id'],p['market']*11//10,1,request_id='test:'+n['id'])
        self.squads.confirm_initial(tuple(m.id for m in self.squads.snapshot().members[:5]))
        for role in ('first_team','second_team'):
            state=self.squads.snapshot();self.squads.set_leader(role,next(m.id for m in state.members if m.squad==role),expected_revision=state.revision)
    def close(self,policy=lambda candidates,rng:()):
        with closing(self.db.connect()) as c,c:
            c.execute('BEGIN IMMEDIATE');return finalize(c,-7,policy=policy)
    def test_new_clock_7_days_and_season_unchanged(self):
        self.assertEqual(self.calendar.state().date,GameDate(-7));self.assertEqual(DAYS_PER_SEASON,217)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM scheduled_matches')[0][0],0)
        self.assertEqual(len(self.recruitment.candidates()),40)
    def test_unfinished_contract_gate_no_changes(self):
        before=self.dump()
        with self.assertRaises(CalendarError):self.calendar.advance_day(expected_absolute_day=-7)
        self.assertEqual(before,self.dump())
    def test_top3_contracts_fixed13_and_ai9(self):
        self.assertEqual(self.rows("SELECT COUNT(*) FROM founding_contracts WHERE status='pending'")[0][0],3)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM squad_formations')[0][0],9)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM squad_leaders')[0][0],18)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM finance_contracts WHERE annual_krw=30000000 AND person_id IN (SELECT k.person_id FROM draft_picks k JOIN draft_turns t USING(pick_number) WHERE t.round_number>=4)")[0][0],130)
    def test_ready_then_7days_no_growth_payroll_and_regular_schedule(self):
        self.ready();protected=self.rows('SELECT * FROM abilities ORDER BY person_id,skill');picks=self.rows('SELECT * FROM draft_picks ORDER BY pick_number')
        for day in range(-7,0):self.assertEqual(self.calendar.advance_day(expected_absolute_day=day),GameDate(day+1))
        self.assertEqual(self.rows('SELECT COUNT(*) FROM scheduled_matches')[0][0],585)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM special_events')[0][0],6)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM development_settlements')[0][0],0)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM finance_payroll')[0][0],0)
        self.assertEqual(protected,self.rows('SELECT * FROM abilities ORDER BY person_id,skill'))
        self.assertEqual(picks,self.rows('SELECT * FROM draft_picks ORDER BY pick_number'))
        self.assertEqual(CalendarService(Database(self.path),root=ROOT).state().date,GameDate(0))
    def test_monday_only_after_preparation(self):
        self.ready();self.calendar.advance_day(expected_absolute_day=-7)
        state=self.squads.snapshot()
        with self.assertRaises(SquadError):self.squads.set_leader('first_team',next(m.id for m in state.members if m.squad=='first_team'),expected_revision=state.revision)
        with self.assertRaises(RecruitmentError):self.recruitment.apply('ador',())
    def test_application_0_1_2_edit_reject3(self):
        ids=[p.id for p in self.recruitment.candidates()[:3]]
        for n in range(3):self.assertEqual(self.recruitment.apply('ador',ids[:n])['count'],n)
        before=self.dump()
        with self.assertRaises(RecruitmentError):self.recruitment.apply('ador',ids)
        with self.assertRaises(RecruitmentError):self.recruitment.apply('ador',[ids[0],ids[0]])
        self.assertEqual(before,self.dump())
        self.assertEqual(self.recruitment.apply('ador',[ids[2]])['targets'][0]['person_id'],ids[2])
    def test_solo_zero_salary_and_no_immediate_transfer(self):
        person=self.recruitment.candidates()[0].id;self.recruitment.apply('ador',[person])
        self.assertIsNone(self.rows('SELECT agency_id FROM roster_memberships WHERE person_id=?',(person,))[0][0])
        results=self.close();self.assertEqual(results[0]['winner'],'ador')
        self.assertEqual(self.rows('SELECT agency_id,career_status FROM roster_memberships WHERE person_id=?',(person,))[0],('ador','trainee'))
        self.assertEqual(self.rows('SELECT annual_krw FROM finance_contracts WHERE person_id=?',(person,))[0][0],0)
    def test_contested_equal_draw_saved_and_no_early_disclosure(self):
        person=self.recruitment.candidates()[0].id
        for agency in ('ador','jyp','yg'):self.recruitment.apply(agency,[person])
        self.assertEqual(self.recruitment.state('ador')['results'],[])
        results=self.close();self.assertEqual(results[0]['applicants'],['ador','jyp','yg'])
        self.assertIn(results[0]['winner'],('ador','jyp','yg'));before=self.dump()
        self.assertEqual(results,self.close());self.assertEqual(before,self.dump())
        with self.assertRaises(RecruitmentError):self.recruitment.apply('ador',[])
        self.assertEqual(results,RecruitmentService(Database(self.path)).results('ador',-7))
    def test_ai_all9_max2_no_potential_reads(self):
        original=self.db.connect
        def connect():
            c=original();c.set_authorizer(lambda a,t,col,*_:sqlite3.SQLITE_DENY if a==sqlite3.SQLITE_READ and (col in ('potential','archetype') or t=='annual_secrets') else sqlite3.SQLITE_OK);return c
        with patch.object(self.db,'connect',side_effect=connect):
            with closing(self.db.connect()) as c,c:c.execute('BEGIN IMMEDIATE');finalize(c,-7)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM trainee_sheets')[0][0],10)
        self.assertTrue(all(n<=2 for _,n in self.rows('SELECT agency_id,COUNT(*) FROM trainee_applications GROUP BY agency_id')))
    def test_changed_owner_conflict_consumes_application(self):
        person=self.recruitment.candidates()[0].id;self.recruitment.apply('ador',[person])
        with closing(self.db.connect()) as c,c:c.execute("UPDATE roster_memberships SET agency_id='jyp',career_status='trainee' WHERE person_id=?",(person,))
        self.assertEqual(self.close()[0]['status'],'ineligible');self.assertEqual(self.recruitment.state('ador')['count'],1)
    def test_save_failure_full_rollback_rng_and_contract(self):
        person=self.recruitment.candidates()[0].id;self.recruitment.apply('ador',[person])
        with closing(self.db.connect()) as c,c:c.execute("CREATE TRIGGER fail_result BEFORE INSERT ON trainee_results BEGIN SELECT RAISE(ABORT,'test');END")
        before=self.dump()
        with self.assertRaises(sqlite3.IntegrityError):self.close()
        self.assertEqual(before,self.dump())
    def test_revision_conflict_rollback(self):
        self.ready();self.recruitment.apply('ador',());before=self.dump()
        with self.assertRaises(CalendarError):self.calendar.advance_day(expected_absolute_day=-7,expected_trainee_revision=0)
        self.assertEqual(before,self.dump())
    def test_concurrent_finalize_only_once(self):
        self.recruitment.apply('ador',[self.recruitment.candidates()[0].id])
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:self.close(),range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(self.rows('SELECT COUNT(*) FROM trainee_results')[0][0],1)
    def test_legacy_no_retroactive_phase(self):
        with closing(self.db.connect()) as c,c:c.execute('DELETE FROM founding_setup')
        self.assertFalse(self.calendar.state().date.is_founding)
    def test_failed_top_contract_direct_fa_replacement(self):
        n=next(n for n in self.market.negotiations('ador') if n['status']=='open')
        self.market.abandon(n['id'],'ador')
        self.assertEqual(self.rows('SELECT agency_id FROM roster_memberships WHERE person_id=?',(n['person_id'],))[0][0],None)
        person=self.recruitment.candidates()[0].id
        identity=self.market.start_negotiation('ador',person,'fa')
        p=next(p for p in self.market.public_people() if p['id']==person)
        self.market.offer(identity,p['market']*11//10,1,request_id='replacement')
        self.ready();self.assertEqual(self.calendar.state().advance_block_reason,'')
    def test_auction_during_preparation_blocked(self):
        with self.assertRaises(ValueError):self.market.bid('ador',self.recruitment.candidates()[0].id,30000000,1,request_id='bid')

    def test_other_agency_applications_hidden_until_closure(self):
        person=self.recruitment.candidates()[0].id;self.recruitment.apply('jyp',[person])
        self.assertEqual(self.recruitment.state('jyp')['targets'],[])
        self.close();self.assertEqual(self.recruitment.state('jyp')['targets'][0]['person_id'],person)
    def test_three_failed_offers_release_only_that_player(self):
        self.market.seed_factory=lambda:0
        n=next(n for n in self.market.negotiations('ador') if n['status']=='open')
        before=self.rows('SELECT * FROM abilities ORDER BY person_id,skill')
        for i,amount in enumerate((10000,20000,30000)):
            result=self.market.offer(n['id'],amount,1,request_id='failed:'+str(i));self.assertFalse(result['accepted'])
        self.assertEqual(self.rows('SELECT career_status FROM roster_memberships WHERE person_id=?',(n['person_id'],))[0][0],'fa')
        self.assertEqual(before,self.rows('SELECT * FROM abilities ORDER BY person_id,skill'))
        self.assertNotIn(n['person_id'],{p.id for p in self.recruitment.candidates()})
    def test_unlimited_owned_trainees_with_weekly_two_limit(self):
        from idol_manager.market_service import _new_contract
        ids=[p.id for p in self.recruitment.candidates()[:8]]
        with self.market.write() as c:
            for p in ids[:6]:
                contract=_new_contract(c,p,'ador',0,1,'free_trainee');_move(c,p,'ador','trainee','trainee',contract)
        self.recruitment.apply('ador',ids[6:]);self.close()
        self.assertEqual(self.rows("SELECT COUNT(*) FROM roster_memberships WHERE agency_id='ador' AND career_status='trainee'")[0][0],8)
    def test_v17_backup_migration_preserves_every_old_row_and_no_prep(self):
        from tests.migration_fixtures import drop_founding
        with closing(self.db.connect()) as c,c:
            # Reconstruct an old-schema copy only; no production save is opened.
            trigger=c.execute("SELECT sql FROM sqlite_master WHERE name='finance_pro_debut'").fetchone()[0]
            c.execute('DROP TRIGGER finance_pro_debut');drop_founding(c)
            trigger=trigger.replace("AND NOT EXISTS(SELECT 1 FROM founding_setup WHERE game_id=1 AND status IN ('pending','active'))",'')
            c.execute(trigger);c.execute('PRAGMA user_version=17')
        with closing(self.db.connect()) as c:
            tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            before={t:[tuple(r) for r in c.execute('SELECT * FROM "'+t+'"')] for t in tables}
        upgraded=Database(self.path);self.assertIsNotNone(upgraded.last_backup_path)
        with closing(upgraded.connect()) as c:
            from idol_manager.migrations import SCHEMA_VERSION
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],SCHEMA_VERSION)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM founding_setup').fetchone()[0],0)
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            for t,rows in before.items():self.assertEqual(rows,[tuple(r) for r in c.execute('SELECT * FROM "'+t+'"')],t)
        with closing(sqlite3.connect(upgraded.last_backup_path)) as c:self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],17)

    def test_zero_applications_close_with_no_awards_and_no_reroll(self):
        self.recruitment.apply('ador',());self.assertEqual(self.close(),[])
        self.assertTrue(self.recruitment.state('ador')['closed'])
        before=self.dump();self.assertEqual(self.close(),[]);self.assertEqual(before,self.dump())
    def test_reversed_submission_order_same_draw(self):
        person=self.recruitment.candidates()[0].id
        for agency in ('ador','jyp','yg'):self.recruitment.apply(agency,[person])
        clone=self.path.with_name('reversed.sqlite3')
        with closing(self.db.connect()) as c,closing(sqlite3.connect(clone)) as dst:c.backup(dst)
        results=self.close()
        other=Database(clone)
        with closing(other.connect()) as c,c:
            c.execute('DELETE FROM trainee_applications');c.execute('DELETE FROM trainee_sheets');c.execute('DELETE FROM trainee_weeks')
        api=RecruitmentService(other)
        for agency in ('yg','jyp','ador'):api.apply(agency,[person])
        with closing(other.connect()) as c,c:
            c.execute('BEGIN IMMEDIATE');opposite=finalize(c,-7,policy=lambda candidates,rng:())
        self.assertEqual(results,opposite)
    def test_professional_retired_and_open_negotiation_excluded(self):
        ids=[p.id for p in self.recruitment.candidates()[:3]]
        with closing(self.db.connect()) as c,c:
            c.execute("UPDATE roster_memberships SET career_status='retired' WHERE person_id=?",(ids[0],))
            c.execute("INSERT INTO market_negotiations VALUES ('blocked',1,'jyp',?,'fa','open',-7,'test')",(ids[1],))
            c.execute('UPDATE market_careers SET debut_season=1 WHERE person_id=?',(ids[2],))
        self.assertFalse(set(ids)&{p.id for p in self.recruitment.candidates()})
        for p in ids:
            with self.assertRaises(RecruitmentError):self.recruitment.apply('ador',[p])

class FoundingUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
        FoundingTests.setUpClass.__func__(cls)
    def setUp(self):
        FoundingTests.setUp(self)
        from idol_manager.service import GameService
        from idol_manager.ui.main_window import MainWindow
        self.service=GameService(ROOT,self.path);self.window=MainWindow(self.service)
        self.addCleanup(self.window.close);self.window.resize(1280,900);self.window.show();self.app.processEvents()
    def test_prep_date_and_market_application_add_remove(self):
        from PySide6.QtWidgets import QMessageBox,QPushButton
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt
        self.assertIn('창단 준비 · 월요일',self.window.game_date_label.text())
        self.window.show_market();page=self.window.market_page
        page.tabs.setCurrentIndex(5);self.app.processEvents()
        self.assertEqual(page.trainee_table.rowCount(),40)
        page.trainee_table.setCurrentCell(0,2)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes),patch.object(QMessageBox,'information'):
            button=next(b for b in page.findChildren(QPushButton) if b.text()=='이번 회차 신청 추가')
            QTest.mouseClick(button,Qt.MouseButton.LeftButton)
        self.assertEqual(self.service.recruitment.state('ador')['count'],1)
        self.assertIn('1/2',page.trainee_status.text())
        person=self.service.recruitment.state('ador')['targets'][0]['person_id']
        for row in range(page.trainee_table.rowCount()):
            if page.trainee_table.item(row,0).data(Qt.ItemDataRole.UserRole)==person:page.trainee_table.setCurrentCell(row,2);break
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes),patch.object(QMessageBox,'information'):
            button=next(b for b in page.findChildren(QPushButton) if b.text()=='선택 후보 신청 취소')
            QTest.mouseClick(button,Qt.MouseButton.LeftButton)
        self.assertEqual(self.service.recruitment.state('ador')['count'],0)
        import os
        if os.environ.get('IDOL_QA_CAPTURE'):
            QTest.qWait(150)
            self.assertTrue(self.window.grab().save(str(ROOT/'reports/founding_preparation/founding_market.png')))
    def test_monday_close_cancel_no_changes_then_approved(self):
        from PySide6.QtWidgets import QMessageBox
        FoundingTests.ready(self);self.window.refresh_calendar()
        before=FoundingTests.dump(self)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No):self.window.advance_day()
        self.assertEqual(before,FoundingTests.dump(self))
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):self.window.advance_day()
        self.assertEqual(self.service.calendar.state().date,GameDate(-6))
        self.assertTrue(self.service.recruitment.state('ador')['closed'])
        self.assertIn('화요일',self.window.game_date_label.text())
    rows=FoundingTests.rows
    dump=FoundingTests.dump

if __name__=='__main__':unittest.main()
