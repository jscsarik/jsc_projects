"""Release fixes use fixed fixtures and a copy of the phase-25 checkpoint."""
from contextlib import closing
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
import json,random,sqlite3,tempfile,unittest
from idol_manager.config import ROOT
from idol_manager.awards import decide,finalize,AwardError
from idol_manager.database import Database
from tests.test_awards import record
from tests import test_market as fixture

class AwardVacancyTests(unittest.TestCase):
    def test_zero_one_many_rookies_and_zero_wins(self):
        order=['ador','jyp'];old=record('old',debut=1);young=record('new',wins=0,debut=2)
        self.assertEqual(decide([old],order,2,random.Random(1))['rookie']['status'],'NO_ELIGIBLE_CANDIDATE')
        self.assertEqual(decide([old,young],order,2,random.Random(1))['rookie']['winner']['id'],'new')
        second=deepcopy(young);second['id']='new2';seen={decide([old,young,second],order,2,random.Random(s))['rookie']['winner']['id'] for s in range(20)}
        self.assertEqual(seen,{'new','new2'})
        with self.assertRaises(AwardError):decide([],order,2,random.Random(1))
        unknown=deepcopy(old);unknown['debut']=None
        with self.assertRaises(AwardError):decide([unknown],order,2,random.Random(1))

    def test_real_checkpoint_v17_migration_vacancy_and_failure_rollback(self):
        source=ROOT/'diagnostics/25_seed250029/simulation.sqlite3'
        if not source.exists():self.skipTest('25차 실제 엔진 체크포인트가 없음')
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'한글 공백.sqlite3'
            with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(target)) as dst:src.backup(dst)
            db=Database(target);self.assertIsNotNone(db.last_backup_path)
            with closing(db.connect()) as c,c:
                before=c.execute('SELECT COUNT(*) FROM match_results').fetchone()[0]
                c.execute("CREATE TRIGGER qa_fail BEFORE INSERT ON award_outcomes WHEN NEW.award_type='dance' BEGIN SELECT RAISE(ABORT,'injected');END")
            with closing(db.connect()) as c,c:
                with self.assertRaises(sqlite3.IntegrityError):finalize(c,2,seed=26)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM season_awards WHERE season=2').fetchone()[0],0)
                c.execute('DROP TRIGGER qa_fail')
            with closing(db.connect()) as c,c:
                self.assertTrue(finalize(c,2,seed=26));self.assertFalse(finalize(c,2,seed=99))
                self.assertEqual(c.execute('SELECT COUNT(*) FROM award_outcomes WHERE season=2').fetchone()[0],11)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM individual_awards WHERE season=2').fetchone()[0],10)
                self.assertEqual(tuple(c.execute("SELECT status,person_id FROM award_outcomes WHERE season=2 AND award_type='rookie'").fetchone()),('NO_ELIGIBLE_CANDIDATE',None))
                self.assertEqual(c.execute('SELECT COUNT(*) FROM match_results').fetchone()[0],before)
                self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())
                c.execute("DELETE FROM individual_awards WHERE season=2 AND award_type='dance'")
                with self.assertRaises(AwardError):finalize(c,2)
            self.assertIsNone(Database(target).last_backup_path)

class MarketReleaseTests(unittest.TestCase):
    setUpClass=classmethod(fixture.MarketTests.setUpClass.__func__)
    def setUp(self):fixture.MarketTests.setUp(self)
    rows=fixture.MarketTests.rows;dump=fixture.MarketTests.dump;day=fixture.MarketTests.day;member=fixture.MarketTests.member
    finite=fixture.MarketTests.finite;vacancy=fixture.MarketTests.vacancy
    def test_open_fa_auction_or_negotiation_cannot_be_stolen_as_trainee(self):
        self.vacancy();self.vacancy('jyp');self.day(203)
        person=self.rows("SELECT i.person_id FROM idols i JOIN roster_memberships r ON r.person_id=i.person_id WHERE i.status='candidate' AND r.career_status='unassigned' LIMIT 1")[0][0]
        with closing(self.db.connect()) as c,c:c.execute('UPDATE idols SET age=22 WHERE person_id=?',(person,))
        auction=self.market.bid('ador',person,33000000,1,request_id='qa-bid')
        with self.assertRaises(ValueError):self.market.sign_trainee('jyp',person,request_id='qa-steal')
        self.day(205)
        with self.market.write() as c:fixture._settle_auctions(c,205,lambda:1)
        self.assertEqual(self.rows('SELECT status,winner FROM market_auctions WHERE id=?',(auction,)),[('completed','ador')])
    def test_adult_nonprofessional_trainee_and_pro_reentry_rejected(self):
        self.day(203)
        person=self.rows("SELECT i.person_id FROM idols i JOIN roster_memberships r ON r.person_id=i.person_id WHERE i.status='candidate' AND r.career_status='unassigned' LIMIT 1")[0][0]
        with closing(self.db.connect()) as c,c:c.execute('UPDATE idols SET age=22 WHERE person_id=?',(person,))
        self.market.sign_trainee('ador',person,request_id='adult-free')
        from idol_manager.trainee_recruitment import finalize
        with self.market.write() as c:finalize(c,203,policy=lambda candidates,rng:())
        self.assertEqual(self.rows('SELECT career_status FROM roster_memberships WHERE person_id=?',(person,)),[('trainee',)])
        self.market.sign_trainee('ador',person,request_id='adult-free')
        founder=self.member()
        with self.assertRaises(ValueError):self.market.sign_trainee('jyp',founder,request_id='bad-pro')

    def test_annual_two_missed_drafts_uses_retirement_policy(self):
        from idol_manager.market_service import record_outcome
        from idol_manager.annual_draft import sync_session
        self.day(413)
        person=self.rows("SELECT person_id FROM roster_memberships WHERE career_status='unassigned' LIMIT 1")[0][0]
        with closing(self.db.connect()) as c,c:
            c.execute('INSERT INTO market_draft_outcomes VALUES (1,1,?,0)',(person,))
            c.execute('UPDATE market_careers SET unemployed_since=1 WHERE person_id=?',(person,))
            c.execute("INSERT INTO annual_sessions VALUES (2,1,3,'in_progress','[]',413,NULL)")
            c.execute('INSERT INTO annual_pool VALUES (2,?)',(person,))
            agencies=[a.id for a in self.service.agencies()]
            for n in range(1,31):c.execute("INSERT INTO annual_turns(season,pick_number,round_number,agency_id,pick_id,status) VALUES(2,?,?,?,?, 'failed')",(n,(n-1)//10+1,agencies[(n-1)%10],f'qa{n}'))
            sync_session(c,2);sync_session(c,2)
            self.assertEqual(c.execute('SELECT career_status FROM roster_memberships WHERE person_id=?',(person,)).fetchone()[0],'retired')
            self.assertEqual(c.execute("SELECT COUNT(*) FROM market_history WHERE person_id=? AND kind='two_drafts_unselected'",(person,)).fetchone()[0],1)

class PresentationReleaseTests(unittest.TestCase):
    def test_cache_above_capacity_does_not_restart_completion_cycle(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from idol_manager.ui.thumbnails import ThumbnailCache
        from tests.test_annual_draft import png
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);paths=[]
            for n in range(270):
                path=root/'assets/idols'/f'{n}.png';png(path,n);paths.append(path.relative_to(root).as_posix())
            cache=ThumbnailCache(root,root/'cache');notifications=[]
            def refresh():
                notifications.append(1)
                for p in paths:cache.get(p)
            cache.changed.connect(refresh)
            try:
                for p in paths:cache.get(p)
                for _ in range(300):
                    QTest.qWait(10)
                    if not cache.pending:break
                self.assertFalse(cache.pending);before=len(notifications);QTest.qWait(100)
                self.assertEqual(len(notifications),before);self.assertLessEqual(before,270)
            finally:cache.close()

    def test_portrait_releases_closed_profile_registrations(self):
        from tests import test_profile_ui as f
        from PySide6.QtCore import QCoreApplication,QEvent
        from PySide6.QtTest import QTest
        f.ProfileUITests.setUpClass();case=f.ProfileUITests('test_other_agency_search_click_profile_filters_compare_and_close_no_write');case.setUp()
        try:
            w=case.window;w.resize(900,1400);QTest.qWait(80);counts=[]
            for _ in range(6):
                w.profiles.open(case.person);QTest.qWait(30);w.profiles.dialog.close()
                QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);case.app.processEvents()
                counts.append((len(w.portrait_layout.tables),len(w.portrait_layout.boxes)))
            self.assertEqual(counts[0],counts[-1]);self.assertFalse(w.portrait_layout.dialogs)
        finally:case.doCleanups();f.ProfileUITests.doClassCleanups()

if __name__=='__main__':unittest.main()
