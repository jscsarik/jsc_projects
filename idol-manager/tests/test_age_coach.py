"""Age milestones and coach reports on disposable saves only."""
import json,unittest,sqlite3
from contextlib import closing
from unittest.mock import patch
from PySide6.QtCore import Qt,QUrl
from PySide6.QtTest import QTest
from idol_manager.coach_service import CoachService
from idol_manager.database import Database
from idol_manager.development_service import settle_birthday
from idol_manager.game_clock import GameDate
from tests import test_training as fixture

class AgeCoachTests(unittest.TestCase):
    setUpClass=classmethod(fixture.TrainingTests.setUpClass.__func__)
    setUp=fixture.TrainingTests.setUp
    day=fixture.TrainingTests.day;rows=fixture.TrainingTests.rows;dump=fixture.TrainingTests.dump
    settle=fixture.TrainingTests.settle

    def birthday(self,day):
        with closing(self.db.connect()) as c,c:
            runtime=c.execute('SELECT * FROM development_runtime').fetchone()
            settle_birthday(c,day,runtime,json.loads(runtime['rules_json']))

    def test_two_regular_mondays_health_contracts_and_no_offseason_repeat(self):
        before=dict(self.rows('SELECT person_id,age FROM idols'))
        health=dict(self.rows('SELECT person_id,health FROM idols'))
        abilities=self.rows('SELECT * FROM abilities');contracts=self.rows('SELECT * FROM finance_contracts')
        self.birthday(76);self.assertEqual(dict(self.rows('SELECT person_id,age FROM idols')),before)
        self.birthday(77)
        self.assertEqual(dict(self.rows('SELECT person_id,age FROM idols')),{p:a+1 for p,a in before.items()})
        self.birthday(77);self.birthday(161)
        self.assertEqual(dict(self.rows('SELECT person_id,age FROM idols')),{p:a+2 for p,a in before.items()})
        self.assertEqual(dict(self.rows('SELECT person_id,health FROM idols')),{p:max(0,a-2) for p,a in health.items()})
        for d in (168,175,182,189,196,203,210):self.birthday(d)
        self.birthday(161)
        self.assertEqual(self.rows('SELECT * FROM finance_contracts'),contracts)
        self.assertEqual(self.rows('SELECT * FROM abilities'),abilities)
        loaded=Database(self.path)
        with closing(loaded.connect()) as c,c:
            runtime=c.execute('SELECT * FROM development_runtime').fetchone();settle_birthday(c,161,runtime,json.loads(runtime['rules_json']))
        self.assertEqual(dict(self.rows('SELECT person_id,age FROM idols')),{p:a+2 for p,a in before.items()})
        self.assertEqual(self.rows("SELECT absolute_day FROM development_settlements WHERE kind='birthday' ORDER BY absolute_day"),[(77,),(161,)])

    def test_adoption_no_backfill_and_backup(self):
        self.day(100)
        tables=('idols','abilities','roster_memberships','finance_contracts','scheduled_matches','draft_picks','agencies')
        with closing(self.db.connect()) as c,c:
            before={t:[tuple(r) for r in c.execute('SELECT * FROM '+t)] for t in tables}
            for t in ('age_policy','coach_seen','coach_reports','coach_runtime'):c.execute('DROP TABLE '+t)
            c.execute('PRAGMA user_version=23')
        db=Database(self.path);self.assertTrue(db.last_backup_path.exists())
        with closing(db.connect()) as c:
            for t in tables:self.assertEqual(before[t],[tuple(r) for r in c.execute('SELECT * FROM '+t)])
        self.birthday(77);self.assertEqual(before['idols'],self.rows('SELECT * FROM idols'))
        self.birthday(161);self.assertNotEqual(before['idols'],self.rows('SELECT * FROM idols'))

    def test_date_failure_rolls_back_birthday_and_debut_still_offseason_only(self):
        self.day(76);before=self.dump()
        with patch.object(self.service.calendar,'_pending',return_value=0),patch('idol_manager.finance_service.advance_finance',side_effect=ValueError('test failure')):
            with self.assertRaises(ValueError):self.service.calendar.advance_day(expected_absolute_day=76)
        self.assertEqual(before,self.dump())
        from idol_manager.market_service import _entry_day
        for d in (77,161,168,189):
            self.day(d)
            with closing(self.db.connect()) as c:
                with self.assertRaises(ValueError):_entry_day(c,'ador','debut')
        self.day(210)
        with closing(self.db.connect()) as c:self.assertEqual(_entry_day(c,'ador','debut'),GameDate(210))

    def test_daily_unread_persistence_tasks_do_not_complete_by_reading(self):
        self.day(1);api=CoachService(self.db)
        rows=api.refresh();daily=next(r for r in rows if r['report_key']=='daily:1')
        training=next(t for t in daily['targets'] if t['target']=='training');self.assertFalse(training['done'])
        api.read();saved=api.refresh();self.assertTrue(all(r['is_read'] for r in saved))
        loaded=CoachService(Database(self.path));self.assertTrue(all(r['is_read'] for r in loaded.refresh()))
        self.assertFalse(next(t for r in loaded.refresh() if r['report_key']=='daily:1' for t in r['targets'] if t['target']=='training')['done'])
        state=self.service.training.state('ador');self.service.training.save('ador',{},confirm=True,expected_revision=state['revision'])
        rows=api.refresh();self.assertTrue(next(t for r in rows if r['report_key']=='daily:1' for t in r['targets'] if t['target']=='training')['done'])
        count=len(rows);self.assertEqual(count,len(api.refresh()))
        self.day(2);self.assertTrue(any(not r['is_read'] for r in api.refresh()))

    def test_actual_result_reports_and_growth_one_winner_no_private_reads(self):
        self.day(1);api=CoachService(self.db);api.refresh()
        self.assertFalse(any(r['kind']=='match' for r in api.refresh()))
        self.settle()
        # Use actual saved growth entries; force two tied public result facts only
        # in this test DB, without touching CA/PA or running another settlement.
        with closing(self.db.connect()) as c,c:
            c.execute("UPDATE coach_runtime SET rollout_day=0")
            s=c.execute("SELECT id FROM development_settlements WHERE kind='growth' AND absolute_day=7").fetchone()[0]
            c.execute("DELETE FROM development_trials WHERE settlement_id=? AND json_extract(trial_json,'$.kind')='additional'",(s,))
        self.assertFalse(any(r['kind']=='growth' for r in api.refresh()))
        with closing(self.db.connect()) as c,c:
            ids=[r[0] for r in c.execute("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status IN ('first_team','second_team') ORDER BY person_id LIMIT 2")]
            for person in ids:
                ordinal=c.execute('SELECT COALESCE(MAX(ordinal),0)+1 FROM development_trials WHERE settlement_id=? AND person_id=?',(s,person)).fetchone()[0]
                c.execute('INSERT INTO development_trials VALUES (?,?,?,?)',(s,person,ordinal,json.dumps(dict(kind='additional',skill='vocal',applied=1))))
        original=self.db.connect
        def connect():
            c=original();c.set_authorizer(lambda a,t,col,*_:sqlite3.SQLITE_DENY if a==sqlite3.SQLITE_READ and (t=='abilities' or col in ('potential','archetype')) else sqlite3.SQLITE_OK);return c
        with patch.object(self.db,'connect',side_effect=connect):reports=api.refresh()
        winners=[r for r in reports if r['kind']=='growth'];self.assertEqual(len(winners),1)
        self.assertEqual(len(winners[0]['targets']),1)
        before=len(reports);api.read();self.assertEqual(len(api.refresh()),before)
        self.assertTrue(all(r['is_read'] for r in api.refresh()))
        # Commit one actual regular match, then observe one result report.
        self.day(2)
        match=self.rows('SELECT id FROM scheduled_matches WHERE week=1 AND weekday=2 ORDER BY day_order,match_order LIMIT 1')[0][0]
        self.service.matches.play(match)
        self.assertTrue(any(r['kind']=='match' for r in api.refresh()))

    def test_gui_bottom_right_collapse_read_and_internal_link(self):
        from idol_manager.ui.main_window import MainWindow
        from idol_manager.ui.theme_manager import ThemeManager
        from PySide6.QtWidgets import QApplication
        manager=ThemeManager(QApplication.instance(),self.base/'coach-appearance.ini')
        self.addCleanup(lambda:QApplication.instance().removeEventFilter(manager))
        self.addCleanup(lambda:manager.set_mode('light',persist=False))
        self.day(1);w=MainWindow(self.service);self.addCleanup(w.close);w.resize(1300,900);w.show();QTest.qWait(80)
        panel=w.coach_panel;self.assertTrue(panel.isVisible());self.assertTrue(panel.body.isHidden());self.assertTrue(panel.alert.isVisible())
        QTest.mouseClick(panel.toggle,Qt.MouseButton.LeftButton);QTest.qWait(50)
        self.assertFalse(panel.body.isHidden());self.assertTrue(panel.alert.isVisible())
        self.assertLessEqual(w.pages.geometry().bottom(),panel.parentWidget().height())
        panel.link(QUrl('go:daily%3A1:training'));self.assertIs(w.pages.currentWidget(),w.development_hub);self.assertEqual(w.development_tabs.currentIndex(),1)
        self.assertFalse(self.service.training.state('ador')['confirmed'])
        QTest.mouseClick(panel.read_all,Qt.MouseButton.LeftButton);self.assertFalse(panel.alert.isVisible())
        for mode in ('dark','light'):
            manager.set_mode(mode);QTest.qWait(220);self.assertTrue(panel.isVisible())
            from pathlib import Path
            folder=Path('reports/age_coach');folder.mkdir(parents=True,exist_ok=True);w.grab().save(str(folder/('coach_'+mode+'.png')))
        QTest.mouseClick(panel.toggle,Qt.MouseButton.LeftButton);self.assertTrue(panel.body.isHidden())
        w.resize(900,1100);QTest.qWait(60);self.assertLessEqual(panel.width(),w.width())

    def test_actual_trainee_contract_and_draft_reports_group_once(self):
        self.day(7);api=CoachService(self.db);api.refresh()
        candidate=self.service.recruitment.candidates()[0].id
        self.service.recruitment.apply('ador',[candidate])
        from idol_manager.trainee_recruitment import finalize
        with closing(self.db.connect()) as c,c:finalize(c,7,policy=lambda candidates,rng:())
        self.assertTrue(any(r['kind']=='trainee' for r in api.refresh()))
        self.assertTrue(any(r['kind']=='draft' for r in api.refresh()))
        self.day(189)
        person=self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='second_team' ORDER BY person_id LIMIT 1")[0][0]
        n=self.service.market.start_negotiation('ador',person,'renew')
        self.service.market.offer(n,60000000,1,request_id='coach-renew')
        rows=api.refresh();self.assertTrue(any(r['kind']=='contract' for r in rows))
        keys=[r['report_key'] for r in rows];self.assertEqual(keys,[r['report_key'] for r in api.refresh()])

    def test_one_two_season_contract_terms_do_not_shorten_with_birthdays(self):
        from idol_manager.market_service import _new_contract,public_people
        self.day(0)
        people=[r[0] for r in self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='second_team' ORDER BY person_id LIMIT 2")]
        with closing(self.db.connect()) as c,c:
            for duration,person in enumerate(people,1):_new_contract(c,person,'ador',30000000,duration,'pro')
        before=self.rows('SELECT * FROM finance_contracts');terms=self.rows('SELECT * FROM market_terms')
        self.birthday(77);self.birthday(161)
        self.assertEqual(before,self.rows('SELECT * FROM finance_contracts'));self.assertEqual(terms,self.rows('SELECT * FROM market_terms'))
        self.day(217)
        with closing(self.db.connect()) as c:
            second=next(p for p in public_people(c,agency='ador') if p['id']==people[1])
            self.assertEqual(second['remaining_seasons'],1)
