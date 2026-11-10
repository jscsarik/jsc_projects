from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import json
import os
import random
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from idol_manager.calendar_service import CalendarService, CalendarError
from idol_manager.config import ROOT, load_settings
from idol_manager.database import Database
from idol_manager.domain import Person
from idol_manager.draft import DraftEngine
from idol_manager.draft_session import DraftSession
from idol_manager.game_clock import GameDate
from idol_manager.service import GameService
from idol_manager.squads import SquadService, SquadError
from idol_manager.ui.main_window import MainWindow


def copy_db(source,target):
    with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(target)) as dst:
        src.backup(dst)


class InitialRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.temp=tempfile.TemporaryDirectory(prefix='idol_recovery_template_')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.template=Path(cls.temp.name)/'legacy.sqlite3'
        db=Database(cls.template)
        people=tuple(Person(f'p{i}',f'가상 선수{i:03}',f'가상 선수{i:03}',f'assets/idols/{i}.png') for i in range(310))
        db.create_game(people,load_settings(),random.Random(55))
        from tests.game_fixtures import legacy_save
        legacy_save(db)
        engine=DraftEngine(db);DraftSession(engine).select_agency('jyp');engine.start(rng=random.Random(4))
        for number,person in enumerate(engine.available_candidates()[:160],1):
            engine.pick(engine.state().next_turn.agency_id,person.id,expected_pick_number=number)
        calendar=CalendarService(db,rng=random.Random(22));calendar.ensure_current_schedule()
        # Reproduce the old bug in a disposable DB without a production bypass.
        with closing(db.connect()) as c,c:
            c.execute('UPDATE game_clock SET absolute_day=2,revision=3')
        calendar.ensure_current_schedule()

    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(prefix='idol_recovery_테스트_')
        self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/'세이브.sqlite3'
        copy_db(self.template,self.path)
        self.db=Database(self.path);self.calendar=CalendarService(self.db)

    def rows(self,sql,args=()):
        with closing(self.db.connect()) as c:
            return [tuple(r) for r in c.execute(sql,args)]

    def dump(self):
        with closing(self.db.connect()) as c:
            return list(c.iterdump())

    def protected(self):
        tables=[r[0] for r in self.rows("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name!='game_clock'")]
        return {t:self.rows(f'SELECT * FROM "{t}" ORDER BY 1') for t in tables}

    def approve(self,status=None,**extra):
        status=status or self.calendar.initial_recovery_status()
        return self.calendar.recover_initial_date(approved=True,expected_absolute_day=status.absolute_day,
            expected_revision=status.revision,expected_token=status.token,**extra)

    def backups(self):
        return list(self.path.parent.glob('backups/*initial_date_recovery*.sqlite3'))

    def open_window(self):
        self.service=GameService(ROOT,database_path=self.path)
        self.window=MainWindow(self.service);self.addCleanup(self.window.close)
        self.window.show();QTest.mouseClick(self.window.squad_menu,Qt.MouseButton.LeftButton)
        return self.window.squad_page

    def wait(self,predicate):
        deadline=time.monotonic()+15
        while not predicate() and time.monotonic()<deadline:
            QTest.qWait(10);time.sleep(.005)
        self.assertTrue(predicate(),'선수단 저장 시간 초과')

    def test_old_wednesday_deadlock_reproduced_and_day_advance_rejected_without_writes(self):
        self.assertEqual(self.calendar.state().date,GameDate(2))
        self.assertEqual(self.rows('SELECT COUNT(*) FROM draft_picks'),[(160,)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM squad_formations'),[(0,)])
        before=self.dump()
        with self.assertRaisesRegex(CalendarError,'최초 선수단 편성'):
            self.calendar.advance_day(expected_absolute_day=2)
        with self.assertRaisesRegex(SquadError,'월요일'):
            squads=SquadService(self.db)
            squads.confirm_initial(tuple(m.id for m in squads.snapshot().members[:5]))
        self.assertEqual(before,self.dump())
        self.assertTrue(self.calendar.initial_recovery_status().allowed)

    def test_incomplete_draft_blocks_advance_in_service(self):
        with closing(self.db.connect()) as c,c:
            c.execute("UPDATE draft_state SET status='in_progress'")
        before=self.dump()
        with self.assertRaisesRegex(CalendarError,'드래프트'):
            self.calendar.advance_day(expected_absolute_day=2)
        self.assertEqual(before,self.dump())
        self.assertFalse(self.calendar.initial_recovery_status().allowed)

    def test_approval_required_no_backup_no_mutation(self):
        status=self.calendar.initial_recovery_status();before=self.dump()
        for approved in (False,None,1,'yes'):
            with self.assertRaisesRegex(CalendarError,'명시적'):
                self.calendar.recover_initial_date(approved=approved,expected_absolute_day=2,
                    expected_revision=3,expected_token=status.token)
        self.assertEqual(before,self.dump());self.assertEqual(self.backups(),[])

    def test_explicit_recovery_backup_is_full_original_and_only_clock_changes(self):
        original=self.dump();protected=self.protected()
        result=self.approve()
        self.assertTrue(result.backup_path.is_file())
        with closing(sqlite3.connect(result.backup_path)) as backup:
            self.assertEqual(original,list(backup.iterdump()))
            self.assertEqual(backup.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.assertEqual(self.rows('SELECT * FROM game_clock'),[(1,0,4)])
        self.assertEqual(protected,self.protected())
        self.assertEqual(self.rows('SELECT COUNT(*) FROM scheduled_matches'),[(585,)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM special_events'),[(6,)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM draft_picks'),[(160,)])
        from idol_manager.migrations import SCHEMA_VERSION
        self.assertEqual(self.rows('PRAGMA user_version'),[(SCHEMA_VERSION,)])
        self.assertFalse(self.calendar.initial_recovery_status().allowed)
        with self.assertRaises(CalendarError):self.approve()
        self.assertEqual(len(self.backups()),1)

    def test_backup_failure_and_date_write_failure_preserve_entire_db(self):
        before=self.dump()
        with patch('idol_manager.initial_setup.backup_database',side_effect=OSError('backup failure')):
            with self.assertRaises(OSError):self.approve()
        self.assertEqual(before,self.dump());self.assertEqual(self.backups(),[])
        with closing(self.db.connect()) as c,c:
            c.execute("CREATE TRIGGER recovery_failure BEFORE UPDATE ON game_clock BEGIN SELECT RAISE(ABORT,'write failed'); END")
        before=self.dump()
        with self.assertRaises(sqlite3.IntegrityError):self.approve()
        self.assertEqual(before,self.dump());self.assertEqual(len(self.backups()),1)

    def test_stale_approval_cannot_restore_after_another_edit(self):
        status=self.calendar.initial_recovery_status()
        with closing(self.db.connect()) as c,c:
            c.execute('UPDATE idols SET health=health-1 WHERE person_id=(SELECT person_id FROM idols LIMIT 1)')
        before=self.dump()
        with self.assertRaisesRegex(CalendarError,'변경'):
            self.approve(status)
        self.assertEqual(before,self.dump());self.assertEqual(self.backups(),[])

    def test_unexpected_trigger_cannot_mutate_funds_during_date_only_recovery(self):
        with closing(self.db.connect()) as c,c:
            c.execute("""CREATE TRIGGER unexpected_clock_effect AFTER UPDATE ON game_clock
                BEGIN UPDATE agencies SET funds_krw=funds_krw+1 WHERE id='jyp'; END""")
        before=self.dump()
        with self.assertRaisesRegex(CalendarError,'날짜 이외'):
            self.approve()
        self.assertEqual(before,self.dump())
        self.assertEqual(len(self.backups()),1)

    def test_existing_result_alone_is_enough_to_block_recovery(self):
        identity=self.rows('SELECT id FROM scheduled_matches LIMIT 1')[0][0]
        with closing(self.db.connect()) as c,c:
            c.execute("INSERT INTO match_results(match_id,resolution,summary_json) VALUES (?,'double_forfeit','{}')",(identity,))
        before=self.dump()
        with self.assertRaisesRegex(CalendarError,'경기'):
            self.approve()
        self.assertEqual(before,self.dump());self.assertEqual(self.backups(),[])

    def test_concurrent_approvals_restore_once_with_one_backup_and_one_revision(self):
        status=self.calendar.initial_recovery_status()
        def recover(_):
            try:self.approve(status);return 'restored'
            except CalendarError:return 'blocked'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(recover,range(2))),['blocked','restored'])
        self.assertEqual(self.rows('SELECT * FROM game_clock'),[(1,0,4)])
        self.assertEqual(len(self.backups()),1)

    def test_any_prepared_blocked_completed_run_prevents_recovery(self):
        match_id=self.rows('SELECT id FROM scheduled_matches LIMIT 1')[0][0]
        for status in ('prepared','blocked','completed'):
            with self.subTest(status=status):
                with closing(self.db.connect()) as c,c:
                    c.execute('DELETE FROM match_runs')
                    c.execute('INSERT INTO match_runs(match_id,engine_version,seed,input_json,status) VALUES (?,?,?,?,?)',
                              (match_id,'regular-1','1','{}',status))
                before=self.dump();inspection=self.calendar.initial_recovery_status()
                self.assertFalse(inspection.allowed);self.assertIn('경기',inspection.reason)
                with self.assertRaises(CalendarError):self.approve(inspection)
                self.assertEqual(before,self.dump())
        self.assertEqual(self.backups(),[])

    def test_completed_match_or_special_status_prevents_recovery_even_without_results(self):
        for table in ('scheduled_matches','special_events'):
            with self.subTest(table=table):
                with closing(self.db.connect()) as c,c:
                    c.execute(f"UPDATE {table} SET status='completed' WHERE id=(SELECT id FROM {table} LIMIT 1)")
                before=self.dump()
                with self.assertRaises(CalendarError):self.approve()
                self.assertEqual(before,self.dump())
                with closing(self.db.connect()) as c,c:c.execute(f"UPDATE {table} SET status='scheduled'")
        self.assertEqual(self.backups(),[])

    def test_funds_settlement_unknown_progress_or_partial_formation_fail_closed(self):
        for scenario in ('funds','settlement','formation'):
            with self.subTest(scenario=scenario):
                copy_db(self.template,self.path)
                with closing(self.db.connect()) as c,c:
                    if scenario=='funds':c.execute("UPDATE agencies SET funds_krw=funds_krw-1 WHERE id='jyp'")
                    elif scenario=='settlement':
                        c.execute('CREATE TABLE season_settlements(season INTEGER)');c.execute('INSERT INTO season_settlements VALUES (1)')
                    else:c.execute("INSERT INTO squad_formations(agency_id) VALUES ('ador')")
                before=self.dump()
                self.assertFalse(self.calendar.initial_recovery_status().allowed)
                with self.assertRaises(CalendarError):self.approve()
                self.assertEqual(before,self.dump())
                self.assertEqual(self.backups(),[])

    def test_incomplete_schedule_and_mismatched_pending_roster_reject_recovery(self):
        with closing(self.db.connect()) as c,c:
            c.execute("UPDATE roster_memberships SET career_status='first_team' WHERE person_id=(SELECT person_id FROM roster_memberships WHERE career_status='pro_pending' LIMIT 1)")
        before=self.dump()
        with self.assertRaises(CalendarError):self.approve()
        self.assertEqual(before,self.dump())
        copy_db(self.template,self.path)
        with closing(self.db.connect()) as c,c:
            c.execute('DELETE FROM scheduled_matches WHERE match_order=1')
        before=self.dump()
        with self.assertRaises(CalendarError):self.approve()
        self.assertEqual(before,self.dump())

    def test_gate_requires_initial_formation_and_both_player_leaders(self):
        self.approve();squads=SquadService(self.db)
        with self.assertRaisesRegex(CalendarError,'최초 선수단'):
            self.calendar.advance_day(expected_absolute_day=0)
        squads.confirm_initial(tuple(m.id for m in squads.snapshot().members[:5]))
        self.assertEqual(self.rows('SELECT COUNT(*) FROM squad_formations'),[(10,)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM squad_leaders WHERE agency_id!='jyp'"),[(18,)])
        with self.assertRaisesRegex(CalendarError,'1군·2군 리더'):
            self.calendar.advance_day(expected_absolute_day=0)
        for squad in ('first_team','second_team'):
            state=squads.snapshot();identity=next(m.id for m in state.members if m.squad==squad)
            squads.set_leader(squad,identity,expected_revision=state.revision)
            if squad=='first_team':
                with self.assertRaisesRegex(CalendarError,'2군 리더'):
                    self.calendar.advance_day(expected_absolute_day=0)
        self.assertEqual(self.calendar.advance_day(expected_absolute_day=0),GameDate(1))
        with self.assertRaisesRegex(SquadError,'월요일'):
            squads.move(identity,'first_team',expected_revision=squads.snapshot().revision)

    def test_gui_day_error_cancel_restore_formation_leaders_and_restart(self):
        page=self.open_window();before=self.dump()
        self.assertTrue(self.window.recovery_button.isVisible())
        with patch.object(QMessageBox,'warning') as warning:
            __import__("tests.game_fixtures",fromlist=["confirm_day"]).confirm_day(self.window)
            self.assertIn('최초 선수단 편성',warning.call_args.args[2])
            self.assertIn('초기 날짜 복구',warning.call_args.args[2])
        self.assertEqual(before,self.dump())
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No) as question:
            QTest.mouseClick(self.window.recovery_button,Qt.MouseButton.LeftButton)
            self.assertIn('기존 데이터를 백업한 뒤',question.call_args.args[2])
            self.assertIn('월요일로 복구하시겠습니까',question.call_args.args[2])
        self.assertEqual(before,self.dump());self.assertEqual(self.backups(),[])
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes),patch.object(QMessageBox,'information'):
            QTest.mouseClick(self.window.recovery_button,Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.game_date_label.text(),str(GameDate(0)))
        self.assertFalse(self.window.recovery_button.isVisible())
        self.assertEqual(len(self.backups()),1)
        for row in range(5):
            page.table.setCurrentIndex(page.proxy.index(row,0));QTest.keyClick(page.table,Qt.Key.Key_Space)
        self.assertTrue(page.confirm_button.isEnabled())
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):
            QTest.mouseClick(page.confirm_button,Qt.MouseButton.LeftButton)
        self.wait(lambda:page.job is None)
        self.assertTrue(page.snapshot.initialized)
        self.assertEqual(sum(m.squad=='first_team' for m in page.snapshot.members),5)
        self.assertEqual(sum(m.squad=='second_team' for m in page.snapshot.members),11)
        for combo,button in ((page.first_leader_combo,page.first_leader_button),(page.second_leader_combo,page.second_leader_button)):
            combo.setFocus();QTest.keyClick(combo,Qt.Key.Key_Home);QTest.keyClick(combo,Qt.Key.Key_Down)
            QTest.mouseClick(button,Qt.MouseButton.LeftButton)
        self.assertFalse(self.service.calendar.state().advance_block_reason)
        self.assertEqual(self.window.day_button.toolTip(),'미처리 경기가 없으면 다음 날로 진행합니다.')
        expected=page.snapshot
        self.window.close()
        reopened=GameService(ROOT,database_path=self.path)
        self.assertEqual(reopened.squads.snapshot(),expected)
        window=MainWindow(reopened);self.addCleanup(window.close);window.show();window.show_squads()
        self.assertEqual(window.game_date_label.text(),str(GameDate(0)))
        self.assertEqual(window.squad_page.snapshot.leaders,expected.leaders)
        __import__("tests.game_fixtures",fromlist=["confirm_day"]).confirm_day(window)
        self.assertEqual(reopened.calendar.state().date,GameDate(1))
        self.assertFalse(window.squad_page.first_leader_button.isEnabled())

    def test_actual_save_copy_approval_changes_only_clock_then_gui_setup(self):
        source=ROOT/'data/idol_manager.sqlite3'
        copy_db(source,self.path)
        self.db=Database(self.path);self.calendar=CalendarService(self.db)
        status=self.calendar.initial_recovery_status()
        if not status.allowed:self.skipTest('Actual save no longer has the untouched initial deadlock: '+status.reason)
        self.assertEqual(status.absolute_day,2)
        before=self.protected();page=self.open_window()
        original=self.dump()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No):
            QTest.mouseClick(self.window.recovery_button,Qt.MouseButton.LeftButton)
        self.assertEqual(original,self.dump())
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes),patch.object(QMessageBox,'information'):
            QTest.mouseClick(self.window.recovery_button,Qt.MouseButton.LeftButton)
        self.assertEqual(before,self.protected())
        self.assertEqual(self.rows('SELECT absolute_day,revision FROM game_clock'),[(0,status.revision+1)])
        for row in range(5):
            page.table.setCurrentIndex(page.proxy.index(row,0));QTest.keyClick(page.table,Qt.Key.Key_Space)
        self.assertTrue(page.confirm_button.isEnabled())
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):
            QTest.mouseClick(page.confirm_button,Qt.MouseButton.LeftButton)
        self.wait(lambda:page.job is None)
        for combo,button in ((page.first_leader_combo,page.first_leader_button),(page.second_leader_combo,page.second_leader_button)):
            combo.setFocus();QTest.keyClick(combo,Qt.Key.Key_Home);QTest.keyClick(combo,Qt.Key.Key_Down)
            QTest.mouseClick(button,Qt.MouseButton.LeftButton)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM squad_formations'),[(10,)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM squad_leaders'),[(20,)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM scheduled_matches'),[(585,)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM draft_picks'),[(160,)])
        for table in ('people','idols','abilities','agencies','draft_state','draft_turns','draft_picks','scheduled_matches','match_participants','special_events'):
            self.assertEqual(before[table],self.protected()[table])
        self.assertEqual(len(page.snapshot.leaders),2)
        self.wait(lambda:not self.window.thumbnails.pending)
        self.assertTrue(self.window.grab().save(str(ROOT/'.test-artifacts/initial_recovery_copy_completed.png')))


if __name__=='__main__':unittest.main()
