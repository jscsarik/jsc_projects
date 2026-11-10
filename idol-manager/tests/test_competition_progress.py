"""Bounded tournament/UI regression checks against disposable databases only."""
import os,json,random,time,unittest
os.environ.setdefault('QT_QPA_PLATFORM','windows')
from contextlib import closing
from unittest.mock import patch
from dataclasses import replace
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from tests import test_season32 as fixture
from idol_manager.game_clock import regular_day
from idol_manager.finals_service import FinalsService
from idol_manager.match_engine import calculate_match
from idol_manager.config import SKILLS
from idol_manager.ui.main_window import MainWindow

class CompetitionProgressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        fixture.Season32Tests.setUpClass.__func__(cls)
    setUp=fixture.Season32Tests.setUp
    rows=fixture.Season32Tests.rows
    day=fixture.Season32Tests.day

    def dump(self):
        with closing(self.db.connect()) as c:return list(c.iterdump())

    def open(self):
        self.window=MainWindow(self.service);self.addCleanup(self.window.close)
        self.window.resize(1600,950);self.window.show();QTest.qWait(120)
        return self.window

    def wait(self,predicate):
        end=time.monotonic()+15
        while not predicate() and time.monotonic()<end:QTest.qWait(10);time.sleep(.003)
        self.assertTrue(predicate())

    def special(self,week=4):
        self.day(regular_day(1,week,6))
        with closing(self.db.connect()) as c,c:
            c.execute("UPDATE scheduled_matches SET status='completed'")
            c.execute("UPDATE special_events SET status='completed' WHERE week<?",(week,))
        event=next(e for e in self.service.specials.events() if e['today'])
        self.service.specials.seed_factory=lambda:1827
        self.service.specials.start(event['id'])
        return event

    def finalists(self):
        self.day(182)
        from idol_manager.league import standings
        with closing(self.db.connect()) as c,c:
            c.execute("UPDATE scheduled_matches SET status='completed'")
            c.execute("UPDATE special_events SET status='completed'")
            table=[dict(r,points=100-i) for i,r in enumerate(standings(c,1))]
            # ADOR remains outside the top four to exercise AI-only playoffs.
            table.sort(key=lambda r:r['agency_id']=='ador')
            table=[dict(r,points=100-i) for i,r in enumerate(table)]
            with patch('idol_manager.finals_service.standings',return_value=table):FinalsService.ensure_started(c,1)
        return [r['agency_id'] for r in table]

    def desired(self,identity,winner):
        def calculate(match,rng,**kwargs):
            probabilities={p.id:{s:float(t.agency_id==winner) for s in SKILLS} for t in match.teams for p in t.players}
            return calculate_match(replace(match,probabilities=probabilities),random.Random(1),**kwargs)
        with patch('idol_manager.finals_service.calculate_match',side_effect=calculate):return self.service.finals.play(identity)

    def test_all_special_dates_auto_select_and_past_date_separate(self):
        self.open();page=self.window.special_page
        for week in (4,8,12,16,20,24):
            self.day(regular_day(1,week,6));page.reload()
            event=next(e for e in self.service.specials.events() if e['today'])
            self.assertEqual(page.event_combo.currentData(),event['id'])
        self.day(182);page.reload()
        self.assertIn('지난 경기 결과 조회',page.group_label.text())
        before=self.rows('SELECT absolute_day FROM game_clock')
        page.event_combo.setCurrentIndex(0);page.go_current()
        self.assertEqual(page.event_combo.currentIndex(),5)
        self.assertEqual(before,self.rows('SELECT absolute_day FROM game_clock'))

    def test_special_stages_refresh_results_without_reroll_or_empty_lineup(self):
        event=self.special();self.open();page=self.window.special_page
        for stage in ('upper','lower','final'):
            r=next(r for r in self.service.specials.state(event['id'])['rounds'] if r['stage']==stage)
            result=self.service.specials.play(r['id'])
            page.reload();page.choose_stage(r['id'])
            self.assertEqual(page.current_result,result)
            self.assertFalse(page.tabs.isTabVisible(0));self.assertTrue(page.lineup_table.isHidden())
            before=self.dump()
            with patch.object(self.service.specials,'play',side_effect=AssertionError('reroll')):
                page.reload_button.click();page.choose_stage(r['id'])
            self.assertEqual(before,self.dump())
        self.assertEqual(page.summary_table.rowCount(),10)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM special_points'),[(14,)])
        self.assertEqual(self.service.specials.state(event['id'])['status'],'completed')
        self.assertEqual(self.rows('SELECT COUNT(*) FROM scheduled_matches'),[(585,)])
        from pathlib import Path
        out=Path(__file__).resolve().parents[1]/'reports/competition_0369';out.mkdir(exist_ok=True)
        self.window.show_specials();self.window.grab().save(str(out/'special.png'))

    def test_special_ai_button_and_player_selection_protection(self):
        event=self.special();self.open();page=self.window.special_page
        r=next(r for r in page.event_state['rounds'] if 'ador' not in r['agencies'])
        page.choose_stage(r['id']);self.assertTrue(page.lineup_table.isHidden())
        self.assertEqual(page.start_button.text(),'AI 경기 진행')
        QTest.mouseClick(page.start_button,Qt.MouseButton.LeftButton);self.wait(lambda:page.job is None)
        if page.replaying:page.skip()
        self.assertIsNotNone(self.service.specials.result(r['id']))
        own=next(r for r in page.event_state['rounds'] if 'ador' in r['agencies'])
        page.choose_stage(own['id']);self.assertFalse(page.lineup_table.isHidden())
        self.assertIsNone(self.service.specials.result(own['id']))

    def test_post_monday_bracket_current_round_and_ai_play_resume(self):
        self.finalists();self.open();self.window.show_finals();page=self.window.finals_page
        self.assertEqual(page.fixture_table.rowCount(),2)
        self.assertIn('다음 경기:',page.series_card.text())
        self.assertFalse(page.start_button.isEnabled())
        self.day(184);page.reload()
        self.assertEqual(page.start_button.text(),'AI 경기 진행')
        self.assertTrue(page.start_button.isEnabled());self.assertTrue(page.lineup_table.isHidden())
        page.start_button.click();self.wait(lambda:page.job is None)
        if page.replaying:page.skip()
        self.assertIsNotNone(page.current_result)
        bodies=[page.stage_progress.box.itemAt(i).widget().layout().itemAt(1).widget().text() for i in range(page.stage_progress.box.count())]
        self.assertTrue(any('1승' in text for text in bodies),bodies)
        self.assertFalse(page.tabs.isTabVisible(0))
        before=self.dump();identity=page.current_result.match_id
        with patch.object(self.service.finals,'play',side_effect=AssertionError('reroll')):page.reload_button.click()
        self.assertEqual(before,self.dump())
        self.assertIsNotNone(FinalsService(self.db).result(identity))
        page.view_combo.setCurrentIndex(1);page.go_current();self.assertTrue(page.view_combo.currentData())
        from pathlib import Path
        out=Path(__file__).resolve().parents[1]/'reports/competition_0369';out.mkdir(exist_ok=True)
        QTest.qWait(120);self.window.grab().save(str(out/'postseason.png'))

    def test_series_two_wins_skip_friday_next_round_champion(self):
        order=self.finalists();protected={t:self.rows(f'SELECT * FROM {t}') for t in ('draft_picks','roster_memberships','idols','scheduled_matches')}
        for round_number in (1,2,3):
            for weekday in (2,3):
                self.day(182+(round_number-1)*7+weekday)
                row=self.service.finals.rows()[0];self.desired(row['id'],order[2])
                before=self.rows('SELECT * FROM final_contests')
                self.service.finals.play(row['id']);self.assertEqual(before,self.rows('SELECT * FROM final_contests'))
        self.assertEqual(self.rows('SELECT champion_id,status FROM season_finals'),[(order[2],'completed')])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM final_contests WHERE game_number=3'),[(0,)])
        for table,rows in protected.items():self.assertEqual(rows,self.rows(f'SELECT * FROM {table}'),table)

    def test_one_one_opens_friday_and_date_boundary(self):
        order=self.finalists()
        for day,winner in ((184,order[2]),(185,order[3])):
            self.day(day);self.desired(self.service.finals.rows()[0]['id'],winner)
        self.day(186);row=self.service.finals.rows()[0]
        self.assertEqual(row['game_number'],3);self.desired(row['id'],order[2])
        self.assertEqual(self.rows('SELECT agency_b FROM final_series WHERE round_number=2'),[(order[2],)])
        from idol_manager.game_clock import GameDate
        self.assertEqual(GameDate(regular_day(1,24,6)).after().absolute_day,182)
        self.assertTrue(GameDate(182).is_postseason)

    def test_day_ai_does_not_play_player_stage_and_never_repeats(self):
        from idol_manager.competition_actions import pending_ai,play_pending_ai
        event=self.special()
        own=next(r for r in self.service.specials.state(event['id'])['rounds'] if 'ador' in r['agencies'])
        self.assertEqual(len(pending_ai(self.service)),1)
        self.open()
        from PySide6.QtWidgets import QMessageBox
        with patch.object(QMessageBox,'warning'):
            self.window.advance_day();self.wait(lambda:self.window.job is None)
        self.assertEqual(self.service.calendar.state().date.absolute_day,regular_day(1,4,6))
        self.assertIsNone(self.service.specials.result(own['id']))
        before=self.dump();self.assertEqual(play_pending_ai(self.service),())
        self.assertEqual(before,self.dump())
        self.service.specials.play(own['id'])
        final=next(r for r in self.service.specials.state(event['id'])['rounds'] if r['stage']=='final')
        if 'ador' in final['agencies']:self.service.specials.play(final['id'])
        self.window.advance_day()
        self.wait(lambda:self.window.job is None)
        self.assertEqual(self.service.calendar.state().date.absolute_day,regular_day(1,4,6)+1)
        self.assertIsNotNone(self.service.specials.result(final['id']))

    def test_missing_first_monday_bracket_repaired_without_results(self):
        self.day(182)
        with closing(self.db.connect()) as c,c:
            c.execute("UPDATE scheduled_matches SET status='completed'")
            c.execute("UPDATE special_events SET status='completed'")
        self.service.finals.prepare_current()
        self.assertIsNotNone(self.service.finals.season_state())
        before=self.rows('SELECT * FROM final_contests')
        self.service.finals.prepare_current();self.assertEqual(before,self.rows('SELECT * FROM final_contests'))
        self.assertFalse(self.rows("SELECT 1 FROM final_contests WHERE status='completed'"))

    def test_calendar_enters_postseason_and_completed_finals_enters_offseason(self):
        self.day(181)
        with closing(self.db.connect()) as c,c:
            c.execute("UPDATE scheduled_matches SET status='completed'")
            c.execute("UPDATE special_events SET status='completed'")
        # Finished regular fixtures are a bounded setup, not a 585-game simulation.
        day=self.service.calendar.advance_day(expected_absolute_day=181)
        self.assertEqual(day.absolute_day,182);self.assertTrue(day.is_postseason)
        self.assertIsNotNone(self.service.finals.season_state())
        # Isolate the exit gate from awards, which require actual full-season stats.
        with closing(self.db.connect()) as c,c:
            c.execute("UPDATE season_finals SET status='completed',champion_id='ador'")
            c.execute("UPDATE final_contests SET status='completed'")
        self.day(202)
        with patch('idol_manager.awards.finalize'):
            day=self.service.calendar.advance_day(expected_absolute_day=202)
        self.assertEqual(day.absolute_day,203);self.assertTrue(day.is_offseason)

