from contextlib import closing
from pathlib import Path
from collections import Counter
from dataclasses import replace
import os
import gc
import random
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox

from idol_manager.config import ROOT,load_settings
from idol_manager.database import Database
from idol_manager.draft import DraftEngine
from idol_manager.draft_session import DraftSession
from idol_manager.game_clock import GameDate,DAYS_PER_SEASON
from idol_manager.match_replay import replay_frames
from idol_manager.season_schedule import load_schedule_rules
from idol_manager.service import GameService
from idol_manager.ui.main_window import MainWindow
from idol_manager.ui.match_page import MatchJob
from idol_manager.bgm import BgmManager
from tests.test_bgm import FakeAudio


def copy_db(source,target):
    with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(target)) as dst:
        src.backup(dst)


class MatchUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.temp=tempfile.TemporaryDirectory(prefix='idol_match_ui_template_');cls.addClassCleanup(cls.temp.cleanup)
        cls.base=Path(cls.temp.name);folder=cls.base/'assets/idols';folder.mkdir(parents=True)
        image=QImage(60,80,QImage.Format.Format_RGB32);image.fill(QColor('#c2d4ef'))
        for i in range(310):image.save(str(folder/f'가상 선수{i:03}.png'))
        service=GameService(cls.base);service.calendar.rng=random.Random(18);service.new_game()
        from tests.game_fixtures import legacy_save
        legacy_save(service.database,schedule=True)
        with closing(service.database.connect()) as c,c:c.execute('UPDATE idols SET health=90')
        service.draft_session.select_agency('ador');service.draft.start(rng=random.Random(4))
        for number,person in enumerate(service.draft.available_candidates()[:160],1):
            service.draft.pick(service.draft.state().next_turn.agency_id,person.id,expected_pick_number=number)
        cls.pending=cls.base/'pending.sqlite3';copy_db(service.database.path,cls.pending)
        service.squads.confirm_initial(tuple(m.id for m in service.squads.snapshot().members[:5]))
        for squad in ('first_team','second_team'):
            state=service.squads.snapshot();person=next(m.id for m in state.members if m.squad==squad)
            service.squads.set_leader(squad,person,expected_revision=state.revision)
        service.calendar.advance_day(expected_absolute_day=0);service.calendar.advance_day(expected_absolute_day=1)
        cls.wednesday=service.database.path

    def setUp(self):
        # Collect closed windows from earlier GUI suites before starting a
        # worker. Qt/Python wrapper finalizers must not race an active replay.
        gc.collect()
        self.app.processEvents()
        self.temp=tempfile.TemporaryDirectory(prefix='idol_match_ui_');self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'게임.sqlite3';copy_db(self.wednesday,self.path)

    def open(self,root=None,path=None):
        self.service=GameService(root or self.base,database_path=path or self.path)
        self.service.matches.seed_factory=lambda:42
        self.window=MainWindow(self.service);self.addCleanup(self.window.close)
        self.window.show();QTest.mouseClick(self.window.match_menu,Qt.MouseButton.LeftButton)
        self.page=self.window.match_page
        return self.page

    def rows(self,sql,args=()):
        with closing(self.service.database.connect()) as c:return [tuple(r) for r in c.execute(sql,args)]

    def dump(self):
        with closing(self.service.database.connect()) as c:return list(c.iterdump())

    def wait(self,predicate,seconds=20):
        end=time.monotonic()+seconds
        while not predicate() and time.monotonic()<end:
            QTest.qWait(10);time.sleep(.005)
        self.assertTrue(predicate(),'정규 경기 GUI 작업 시간 초과')

    def select(self,identity):
        table=self.page.fixture_table
        row=next(i for i in range(table.rowCount()) if table.item(i,0).data(Qt.ItemDataRole.UserRole)==identity)
        table.setCurrentCell(row,0)
        QTest.mouseClick(table.viewport(),Qt.MouseButton.LeftButton,pos=table.visualItemRect(table.item(row,0)).center())
        self.assertEqual(self.page.selection.fixture.id,identity)

    def player_fixture(self,order=1):
        return next(f for f in self.service.matches.fixtures() if f.player_participates and f.day_order==order)

    def choose_players(self):
        table=self.page.lineup_table
        needed=self.page.selection.selection_count
        identities=tuple(table.item(i,0).data(Qt.ItemDataRole.UserRole) for i in range(needed))
        for identity in identities:
            row=next(i for i in range(table.rowCount()) if table.item(i,0).data(Qt.ItemDataRole.UserRole)==identity)
            if table.item(row,0).checkState()!=Qt.CheckState.Checked:
                table.setCurrentCell(row,0);QTest.keyClick(table,Qt.Key.Key_Space)
        self.assertEqual(set(self.page.selected_ids()),set(identities))
        self.assertTrue(self.page.start_button.isEnabled())
        return identities

    def play_player(self,identity=None,skip=True):
        identity=identity or self.player_fixture().id
        self.select(identity);chosen=self.choose_players()
        QTest.mouseClick(self.page.start_button,Qt.MouseButton.LeftButton)
        self.wait(lambda:self.page.job is None and self.page.current_result is not None)
        if skip and self.page.replaying:QTest.mouseClick(self.page.skip_button,Qt.MouseButton.LeftButton)
        return self.page.current_result,chosen

    def ai_batch(self):
        if self.page.ai_button.isEnabled():
            QTest.mouseClick(self.page.ai_button,Qt.MouseButton.LeftButton)
            self.wait(lambda:self.page.job is None)

    def test_required_configs_present_valid_and_28_week_calendar_unchanged(self):
        self.assertTrue((ROOT/'config/generation.json').is_file())
        self.assertTrue((ROOT/'config/season_schedule.json').is_file())
        self.assertEqual(len(load_schedule_rules().contents),30)
        self.assertEqual(load_settings()['initial_candidates'],200)
        self.assertEqual(DAYS_PER_SEASON,217)

    def test_injury_disabled_fatigue_preview_matches_saved_probability_and_skip(self):
        self.open();fixture=self.player_fixture()
        members=self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='first_team' ORDER BY person_id")
        injured=members[0][0]
        with closing(self.service.database.connect()) as c,c:
            c.execute('UPDATE player_conditions SET last_appearance_day=1,consecutive_days=2')
            c.execute('UPDATE player_conditions SET injured=1,recovery_day=8 WHERE person_id=?',(injured,))
        self.window.show_matches();self.select(fixture.id)
        table=self.page.lineup_table
        row=next(i for i in range(table.rowCount()) if table.item(i,0).data(Qt.ItemDataRole.UserRole)==injured)
        self.assertFalse(table.item(row,0).flags() & Qt.ItemFlag.ItemIsUserCheckable)
        self.assertIn('출전 불가',table.item(row,14).text())
        self.assertEqual(table.item(row,13).text(),'-10%')
        if self.app.platformName()=='windows':
            self.window.resize(1600,950);self.app.processEvents()
            table.horizontalScrollBar().setValue(table.horizontalScrollBar().maximum())
            self.window.grab().save(str(ROOT/'.test-artifacts/fatigue_windows_selection.png'))
            table.horizontalScrollBar().setValue(0)
        eligible=[o.player.id for o in self.page.selection.options if o.available]
        for person in eligible[:self.page.selection.selection_count]:
            row=next(i for i in range(table.rowCount()) if table.item(i,0).data(Qt.ItemDataRole.UserRole)==person)
            table.item(row,0).setCheckState(Qt.CheckState.Checked)
        QTest.mouseClick(self.page.start_button,Qt.MouseButton.LeftButton)
        self.wait(lambda:self.page.job is None)
        result=self.page.current_result
        self.assertIsNotNone(result)
        self.assertNotIn(injured,{p['person_id'] for p in result.players})
        original={o.player.id:o.player for o in self.page.selection.options}
        for e in result.events:
            if e.person_id in original:self.assertAlmostEqual(e.probability,original[e.person_id].value(e.skill)/100*.9)
        before=self.dump()
        QTest.mouseClick(self.page.skip_button,Qt.MouseButton.LeftButton)
        self.assertEqual(before,self.dump())

    def test_bgm_follows_actual_replay_only_not_start_or_results_or_ai_batch(self):
        audio_root=Path(self.temp.name)/'music'
        for category in ('default','battle'):
            folder=audio_root/'assets/audio/bgm'/category;folder.mkdir(parents=True)
            (folder/f'{category}.mp3').write_bytes(b'fake backend music')
        manager=BgmManager(audio_root,backend_factory=FakeAudio,transition_ms=0,fade_ms=0)
        self.addCleanup(manager.shutdown)
        self.service=GameService(self.base,database_path=self.path);self.service.matches.seed_factory=lambda:42
        self.window=MainWindow(self.service,bgm=manager);self.addCleanup(self.window.close)
        self.window.show();self.window.show_matches();self.page=self.window.match_page
        self.wait(lambda:manager.current_track is not None)
        self.assertEqual(manager.category,'default')
        original=self.service.matches.play;contexts=[]
        def play(*args,**kwargs):
            contexts.append(manager.desired_category)
            return original(*args,**kwargs)
        with patch.object(self.service.matches,'play',side_effect=play) as calculation:
            result,_=self.play_player(skip=False)
            bgm_before=self.dump()
            self.assertEqual(contexts,['default'])
            self.wait(lambda:manager.category=='battle')
            self.page.tabs.setCurrentIndex(3);self.wait(lambda:manager.category=='default')
            self.page.tabs.setCurrentIndex(1);self.wait(lambda:manager.category=='battle')
            QTest.mouseClick(self.page.skip_button,Qt.MouseButton.LeftButton)
            self.wait(lambda:manager.category=='default')
            self.assertEqual(calculation.call_count,1)
            self.assertEqual(self.dump(),bgm_before)
        self.assertEqual(result,self.service.matches.result(result.match_id))
        self.ai_batch();self.assertEqual(manager.desired_category,'default')

    def test_ai_batch_never_spills_into_another_day_if_external_window_advances(self):
        self.open()
        original=next(f for f in self.service.matches.fixtures() if not f.player_participates and not f.block_reason)
        tomorrow=replace(original,id='another-day-match',weekday=3)
        outcomes=[]
        job=MatchJob(self.service.matches);job.signals.finished.connect(lambda result,error:outcomes.append((result,error)))
        with patch.object(self.service.matches,'fixtures',side_effect=[(original,),(original,),(tomorrow,)]),patch.object(self.service.matches,'play') as play:
            job.run()
        play.assert_called_once_with(original.id)
        self.assertEqual(outcomes,[([original.id],'')])

    def test_today_public_first_team_exact_selection_and_numeric_sort(self):
        self.open();fixture=self.player_fixture();self.select(fixture.id)
        self.assertIn(len(self.service.matches.fixtures()),(5,10))
        self.assertIn(fixture.content_name,self.page.detail.text())
        self.assertTrue(all(label in self.page.detail.text() for label in fixture.main_abilities))
        own={r[0] for r in self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='first_team'")}
        options={p.player.id for p in self.page.selection.options}
        self.assertEqual(options,own);self.assertEqual(len(options),5)
        self.assertFalse(self.page.start_button.isEnabled())
        self.page.lineup_table.sortItems(2,Qt.SortOrder.DescendingOrder)
        chosen=self.choose_players();self.assertEqual(len(chosen),fixture.required)
        if fixture.required<5:
            extra=next(i for i in range(5) if self.page.lineup_table.item(i,0).data(Qt.ItemDataRole.UserRole) not in chosen)
            self.page.lineup_table.setCurrentCell(extra,0);QTest.keyClick(self.page.lineup_table,Qt.Key.Key_Space)
            self.assertFalse(self.page.start_button.isEnabled())

    def test_manual_play_saved_once_skip_records_and_schedule_standings_refresh(self):
        self.open()
        with patch.object(self.service.matches,'play',wraps=self.service.matches.play) as play:
            result,chosen=self.play_player(skip=False)
            self.assertTrue(self.page.replaying);self.assertFalse(self.window.day_button.isEnabled())
            self.assertFalse(self.window.new_button.isEnabled());self.assertFalse(self.window.squad_menu.isEnabled())
            before=self.dump()
            self.window.advance_day();self.window.request_new_game()
            self.assertEqual(before,self.dump())
            QTest.mouseClick(self.page.skip_button,Qt.MouseButton.LeftButton)
            self.assertEqual(play.call_count,1)
        self.assertEqual({p['person_id'] for p in result.players if p['agency_id']=='ador'},set(chosen))
        self.assertEqual(self.rows('SELECT status FROM scheduled_matches WHERE id=?',(result.match_id,)),[('completed',)])
        self.assertEqual(sum(r['points'] for r in self.service.matches.standings(1)),1)
        self.assertEqual(self.page.records_table.rowCount(),len(result.players))
        self.assertEqual(self.page.standings_table.rowCount(),10)
        self.assertEqual(self.page.tabs.currentIndex(),2)
        self.assertEqual(self.page.current_result,self.service.matches.result(result.match_id))
        self.assertEqual(dict(self.page.live_scores),{t['agency_id']:t['total_score'] for t in result.teams})
        self.assertTrue(all(p['base_attempts']==60 and p['main_attempts']==p['support_attempts']==30 for p in result.players))
        leader=dict(self.service.squads.snapshot().leaders)['first_team']
        for p in result.players:
            if p['agency_id']=='ador':self.assertEqual(p['leader_attempts'],2 if p['person_id']==leader else 0)
        self.assertTrue(any(e.id==result.match_id and e.status=='completed' for e in self.window.schedule_page.model.rows))

    def test_native_30_second_watch_and_skip_are_exactly_same_saved_result(self):
        self.open();self.assertEqual(self.page.timer.interval(),500)
        result,chosen=self.play_player(skip=False)
        self.assertGreaterEqual(len(self.page.frames),60)
        original=self.dump();started=time.monotonic()
        self.wait(lambda:not self.page.replaying,seconds=len(self.page.frames)*.5+15)
        self.assertGreaterEqual(time.monotonic()-started,27)
        self.assertEqual(self.dump(),original)
        self.assertEqual(dict(self.page.live_scores),{t['agency_id']:t['total_score'] for t in result.teams})
        self.window.close()
        other=Path(self.temp.name)/'skip.sqlite3';copy_db(self.wednesday,other)
        self.open(path=other)
        skipped,other_chosen=self.play_player()
        self.assertEqual(chosen,other_chosen);self.assertEqual(result,skipped)

    def test_ai_batch_and_all_current_games_then_day_advance_and_saved_history(self):
        self.open()
        before=self.dump()
        with patch.object(QMessageBox,'warning') as warning:
            __import__("tests.game_fixtures",fromlist=["confirm_day"]).confirm_day(self.window)
            self.assertIn('미처리',warning.call_args.args[2])
        self.assertEqual(before,self.dump())
        self.ai_batch()
        self.assertTrue(all(f.player_participates for f in self.service.matches.fixtures() if f.status!='completed' and not f.block_reason))
        for order in sorted({f.day_order for f in self.service.matches.fixtures()}):
            fixture=self.player_fixture(order)
            if fixture.status!='completed':self.play_player(fixture.id)
            self.ai_batch()
        today=self.service.matches.fixtures()
        self.assertTrue(all(f.status=='completed' for f in today))
        self.assertEqual(sum(r['points'] for r in self.service.matches.standings(1)),len(today))
        self.assertFalse(self.page.ai_button.isEnabled())
        __import__("tests.game_fixtures",fromlist=["confirm_day"]).confirm_day(self.window)
        self.assertEqual(self.service.calendar.state().date,GameDate(3))
        self.page.view_combo.setCurrentIndex(1)
        self.assertEqual(self.page.fixture_table.rowCount(),len(today))
        self.select(today[0].id)
        with patch.object(self.service.matches,'play',side_effect=AssertionError('completed games must not reroll')):
            QTest.mouseClick(self.page.start_button,Qt.MouseButton.LeftButton)
        self.assertEqual(self.page.current_result.match_id,today[0].id)

    def test_doubleheader_second_game_locked_until_all_first_games_completed(self):
        self.open()
        week,weekday=self.rows('SELECT week,weekday FROM scheduled_matches WHERE day_order=2 ORDER BY match_order LIMIT 1')[0]
        with closing(self.service.database.connect()) as c,c:c.execute('UPDATE game_clock SET absolute_day=?',((week-1)*7+weekday,))
        self.service.calendar.ensure_current_schedule();self.window.show_matches()
        second=self.player_fixture(2);self.select(second.id)
        self.assertFalse(self.page.start_button.isEnabled());self.assertIn('1차',self.page.selection_hint.text())
        self.ai_batch()
        self.assertEqual(self.rows('SELECT COUNT(*) FROM scheduled_matches WHERE week=? AND weekday=? AND day_order=2 AND status!=?',(week,weekday,'scheduled')),[(0,)])
        self.play_player(self.player_fixture(1).id)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM scheduled_matches WHERE week=? AND weekday=? AND day_order=1 AND status='completed'",(week,weekday)),[(5,)])
        self.select(second.id);self.assertFalse(self.page.selection.fixture.block_reason)
        self.play_player(second.id);self.ai_batch()
        self.assertTrue(all(f.status=='completed' for f in self.service.matches.fixtures()))

    def test_sql_public_projection_never_reads_potential_or_archetype(self):
        self.open();original=self.service.database.connect;reads=[]
        def connect():
            c=original()
            def authorize(action,table,column,*rest):
                if action==sqlite3.SQLITE_READ:
                    reads.append((table,column))
                    if (table,column) in (('abilities','potential'),('idols','archetype')):return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            c.set_authorizer(authorize);return c
        with patch.object(self.service.database,'connect',side_effect=connect):
            self.window.show_matches();result,_=self.play_player()
        self.assertTrue(result.players)
        self.assertNotIn(('abilities','potential'),reads);self.assertNotIn(('idols','archetype'),reads)
        self.assertNotIn('potential',repr(self.page.selection))

    def test_restart_during_replay_reads_completed_result_without_play(self):
        self.open();result,_=self.play_player(skip=False);original=self.dump()
        self.window.close();self.open()
        self.select(result.match_id)
        self.assertEqual(self.page.start_button.text(),'저장 결과 보기')
        with patch.object(self.service.matches,'play',side_effect=AssertionError('no reroll')):
            QTest.mouseClick(self.page.start_button,Qt.MouseButton.LeftButton)
        self.assertEqual(result,self.page.current_result);self.assertEqual(original,self.dump())

    def test_storage_error_shows_message_then_frozen_lineup_resumes_safely(self):
        self.open();self.select(self.player_fixture().id);chosen=self.choose_players()
        with closing(self.service.database.connect()) as c,c:
            c.execute("CREATE TRIGGER match_ui_fail BEFORE INSERT ON match_events BEGIN SELECT RAISE(ABORT,'failure'); END")
        with patch.object(QMessageBox,'warning') as warning:
            QTest.mouseClick(self.page.start_button,Qt.MouseButton.LeftButton)
            self.wait(lambda:self.page.job is None)
            self.assertTrue(warning.called);self.assertIn('저장',warning.call_args.args[2])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM match_results'),[(0,)])
        self.assertEqual(set(self.page.selection.fixed_ids),set(chosen))
        self.assertEqual(self.page.start_button.text(),'저장된 경기 재개')
        self.assertTrue(all(not(self.page.lineup_table.item(i,0).flags() & Qt.ItemFlag.ItemIsUserCheckable) for i in range(self.page.lineup_table.rowCount())))
        with closing(self.service.database.connect()) as c,c:c.execute('DROP TRIGGER match_ui_fail')
        QTest.mouseClick(self.page.start_button,Qt.MouseButton.LeftButton)
        self.wait(lambda:self.page.replaying)
        QTest.mouseClick(self.page.skip_button,Qt.MouseButton.LeftButton)
        self.assertEqual({p['person_id'] for p in self.page.current_result.players if p['agency_id']=='ador'},set(chosen))

    def test_no_available_players_forfeit_result_and_no_fake_appearances(self):
        self.open()
        class Nobody:
            def available(self,p):return False
        self.service.matches.availability=Nobody();self.page.reload();self.select(self.player_fixture().id)
        self.assertEqual(self.page.selection.selection_count,0)
        self.assertIn('몰수패',self.page.selection_hint.text())
        QTest.mouseClick(self.page.start_button,Qt.MouseButton.LeftButton)
        self.wait(lambda:self.page.job is None and self.page.current_result is not None)
        self.assertEqual(self.page.current_result.resolution,'double_forfeit')
        self.assertIn('양측 몰수패',self.page.result_summary.text())
        self.assertEqual(self.page.records_table.rowCount(),0)

    def test_special_day_never_auto_completed_or_skipped(self):
        self.open()
        with closing(self.service.database.connect()) as c,c:
            c.execute("UPDATE scheduled_matches SET status='completed'")
            c.execute('UPDATE game_clock SET absolute_day=27')
        self.window.show_matches()
        self.assertEqual(self.page.fixture_table.rowCount(),0);self.assertFalse(self.page.ai_button.isEnabled())
        with patch.object(QMessageBox,'warning') as warning:
            __import__("tests.game_fixtures",fromlist=["confirm_day"]).confirm_day(self.window)
            self.assertIn('특별전',warning.call_args.args[2])
        self.assertEqual(self.service.calendar.state().date,GameDate(27))
        self.assertTrue(all(r==('scheduled',) for r in self.rows('SELECT status FROM special_events')))

    def test_real_save_copy_full_formation_to_wednesday_match_and_next_day(self):
        copy_db(ROOT/'data/idol_manager.sqlite3',self.path);self.open(root=ROOT)
        recovery=self.service.calendar.initial_recovery_status()
        if recovery.allowed:
            with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes),patch.object(QMessageBox,'information'):
                QTest.mouseClick(self.window.recovery_button,Qt.MouseButton.LeftButton)
        if self.service.calendar.state().date!=GameDate(0):self.skipTest('Actual save no longer starts at initial formation')
        if self.service.draft.state().status!='completed':self.skipTest('Actual save has not completed the initial draft')
        QTest.mouseClick(self.window.squad_menu,Qt.MouseButton.LeftButton);squads=self.window.squad_page
        if not squads.snapshot.initialized:
            for row in range(5):
                squads.table.setCurrentIndex(squads.proxy.index(row,0));QTest.keyClick(squads.table,Qt.Key.Key_Space)
            with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):
                QTest.mouseClick(squads.confirm_button,Qt.MouseButton.LeftButton)
            self.wait(lambda:squads.job is None)
        for combo,button in ((squads.first_leader_combo,squads.first_leader_button),(squads.second_leader_combo,squads.second_leader_button)):
            combo.setFocus();QTest.keyClick(combo,Qt.Key.Key_Home);QTest.keyClick(combo,Qt.Key.Key_Down);QTest.mouseClick(button,Qt.MouseButton.LeftButton)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM squad_formations'),[(10,)])
        with closing(self.service.database.connect()) as c:
            protected={t:list(c.execute(f'SELECT * FROM {t} ORDER BY 1')) for t in ('people','idols','abilities','agencies','roster_memberships','squad_leaders','draft_picks','draft_turns')}
            fixtures=[tuple(r)[:11]+tuple(r)[12:13] for r in c.execute('SELECT * FROM scheduled_matches ORDER BY id')]
        __import__("tests.game_fixtures",fromlist=["confirm_day"]).confirm_day(self.window);__import__("tests.game_fixtures",fromlist=["confirm_day"]).confirm_day(self.window)
        self.assertEqual(self.service.calendar.state().date,GameDate(2))
        QTest.mouseClick(self.window.match_menu,Qt.MouseButton.LeftButton)
        first=self.player_fixture();self.select(first.id);self.choose_players()
        self.wait(lambda:not self.window.thumbnails.pending)
        self.assertTrue(self.window.grab().save(str(ROOT/'.test-artifacts/match_ui_selection.png')))
        QTest.mouseClick(self.page.start_button,Qt.MouseButton.LeftButton);self.wait(lambda:self.page.replaying)
        self.page.timer.stop()
        for _ in range(8):self.page.advance_frame()
        self.assertTrue(self.window.grab().save(str(ROOT/'.test-artifacts/match_ui_replay.png')))
        QTest.mouseClick(self.page.skip_button,Qt.MouseButton.LeftButton)
        self.assertTrue(self.window.grab().save(str(ROOT/'.test-artifacts/match_ui_result.png')))
        for order in sorted({f.day_order for f in self.service.matches.fixtures()}):
            self.ai_batch()
            own=self.player_fixture(order)
            if own.status!='completed':self.play_player(own.id)
            self.ai_batch()
        self.assertTrue(all(f.status=='completed' for f in self.service.matches.fixtures()))
        __import__("tests.game_fixtures",fromlist=["confirm_day"]).confirm_day(self.window)
        self.assertEqual(self.service.calendar.state().date,GameDate(3))
        with closing(self.service.database.connect()) as c:
            for t,rows in protected.items():self.assertEqual(rows,list(c.execute(f'SELECT * FROM {t} ORDER BY 1')))
            after=[tuple(r)[:11]+tuple(r)[12:13] for r in c.execute('SELECT * FROM scheduled_matches ORDER BY id')]
            self.assertEqual(fixtures,after)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM scheduled_matches'),[(585,)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM special_events'),[(6,)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM draft_picks'),[(160,)])


if __name__=='__main__':unittest.main()
