import os
from collections import Counter
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QSize,QAbstractAnimation
from PySide6.QtGui import QImage,QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from idol_manager.ui.battle_view import BattleView
from idol_manager.ui.thumbnails import ThumbnailCache
from idol_manager.match_types import Judgment
from idol_manager.match_replay import ReplayFrame
from tests import test_match_ui as fixture


class BattleViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        image=QImage(180,240,QImage.Format.Format_RGB32);image.fill(QColor('#98c6cb'))
        image.save(str(self.root/'한글 사진.png'))
        (self.root/'손상.png').write_bytes(b'not an image')
        self.photos=ThumbnailCache(self.root,self.root/'cache',image_size=QSize(360,480));self.addCleanup(self.photos.close)
        self.view=BattleView(self.photos);self.addCleanup(self.view.close);self.view.resize(1100,550);self.view.show()

    def people(self,count):
        return [dict(id=f'{team}{i}',name=f'가상 {team}{i}',agency_id=team,leader=i==0,
            photo_path='한글 사진.png' if i%3==0 else 'missing.png' if i%3==1 else '손상.png') for team in ('a','b') for i in range(count)]

    def configure(self,count):self.view.configure('음악방송',(('a','왼쪽 기획사'),('b','오른쪽 기획사')),self.people(count))

    def event(self,success,phase='main',person='a0',sequence=1):
        return Judgment(sequence,person[0],person,phase,'vocal',1,0,1,.5,.1 if success else .9,success)

    def test_one_two_three_four_five_cards_photos_placeholders_resize_and_leaders(self):
        for count in (1,2,3,4,5):
            self.configure(count);QTest.qWait(30)
            self.assertEqual(len(self.view.cards),count*2)
            self.assertTrue(all(len(team.cards)==count for team in self.view.teams))
            self.assertEqual(sum('리더' in card.badge.text() for card in self.view.cards.values()),2)
            for width in (650,1400):
                self.view.resize(width,550);self.app.processEvents()
                self.assertTrue(all(card.photo.width()>0 for card in self.view.cards.values()))
        for _ in range(100):
            if not self.photos.pending:break
            QTest.qWait(10)
        self.assertFalse(self.photos.pending)
        self.assertGreater(self.view.cards['a0'].photo.original.width(),100)
        for key in ('a1','a2'):
            self.assertFalse(self.view.cards[key].photo.pixmap().isNull())
            self.assertEqual(self.view.cards[key].photo.original.cacheKey(),self.photos.placeholder.cacheKey())

    def test_success_failure_leader_log_five_lines_and_pause_animation(self):
        self.configure(1);card=self.view.cards['a0']
        self.view.show_frame(ReplayFrame('regular',0,1,(self.event(True),)))
        self.assertEqual(card.successes,1);self.assertIn('+1',card.state.text())
        self.assertEqual(card.flash.state(),QAbstractAnimation.State.Running)
        self.view.pause(True);value=card.flash.currentTime();QTest.qWait(100)
        self.assertEqual(card.flash.state(),QAbstractAnimation.State.Paused);self.assertEqual(card.flash.currentTime(),value)
        self.view.pause(False);QTest.qWait(30);self.assertGreater(card.flash.currentTime(),value)
        self.view.show_frame(ReplayFrame('regular',0,2,(self.event(False),)))
        self.assertFalse(card.last_success);self.assertIn('실패',card.state.text());self.assertEqual(card.successes,1)
        self.view.show_frame(ReplayFrame('regular',0,60,tuple(self.event(True,'leader',sequence=i) for i in range(7))))
        self.assertEqual(len(self.view.logs),5);self.assertIn('리더 보너스',self.view.log.text())
        self.view.final_counts(Counter(a0=8,b0=0))
        self.assertEqual(card.flash.state(),QAbstractAnimation.State.Stopped);self.assertIn('8회',card.score.text())

    def test_five_players_are_all_visible_in_centered_three_plus_two_grid(self):
        self.configure(5)
        for width in (650,1100,1700):
            self.view.resize(width,650);QTest.qWait(30)
            for team in self.view.teams:
                positions=[team.grid.getItemPosition(team.grid.indexOf(card)) for card in team.cards]
                self.assertEqual(positions,[(0,0,1,2),(0,2,1,2),(0,4,1,2),(1,1,1,2),(1,3,1,2)])
                for card in team.cards:
                    self.assertTrue(card.isVisible());self.assertTrue(team.host.rect().contains(card.geometry()))
                for index,card in enumerate(team.cards):
                    self.assertFalse(any(card.geometry().intersects(other.geometry()) for other in team.cards[index+1:]))
                center=(team.cards[3].geometry().center().x()+team.cards[4].geometry().center().x())/2
                self.assertAlmostEqual(center,team.host.rect().center().x(),delta=2)
    def test_event_focus_keeps_all_ten_players_visible_and_scores_independent(self):
        self.configure(5);QTest.qWait(20)
        events=tuple(self.event(True,person=f'{team}{i}',sequence=n) for n,(team,i) in enumerate((t,i) for t in ('a','b') for i in range(5)))
        self.view.show_frame(ReplayFrame('regular',0,1,events));self.app.processEvents()
        self.assertTrue(all(card.isVisible() for card in self.view.cards.values()))
        self.assertTrue(all(card.successes==1 for card in self.view.cards.values()))
        self.assertEqual([team.total.text() for team in self.view.teams],['5','5'])


class VisualReplayTests(unittest.TestCase):
    setUpClass=classmethod(fixture.MatchUITests.setUpClass.__func__)
    setUp=fixture.MatchUITests.setUp
    open=fixture.MatchUITests.open
    rows=fixture.MatchUITests.rows
    dump=fixture.MatchUITests.dump
    wait=fixture.MatchUITests.wait
    select=fixture.MatchUITests.select
    player_fixture=fixture.MatchUITests.player_fixture
    choose_players=fixture.MatchUITests.choose_players
    play_player=fixture.MatchUITests.play_player

    def test_five_player_scene_is_inside_all_main_window_ancestors(self):
        from PySide6.QtCore import QPoint,QRect
        self.open();agencies=self.service.agencies()[:2];people=[]
        for agency in agencies:
            for p in self.service.agency_roster(agency.id):
                if p.status=='first_team':people.append(dict(id=p.id,name=p.name,photo_path=p.photo_path,agency_id=agency.id,leader=False))
        self.page.tabs.setCurrentIndex(1);self.page.battle.configure('5인 출전',[(a.id,a.name) for a in agencies],people)
        self.assertEqual(len(people),10)
        for width,height in ((800,700),(1280,720),(1920,1080)):
            self.window.resize(width,height);QTest.qWait(150);self.window.portrait_layout.refresh();QTest.qWait(80)
            for card in self.page.battle.cards.values():
                self.assertTrue(card.isVisible());parent=card.parentWidget()
                while parent is not None:
                    rect=QRect(card.mapTo(parent,QPoint()),card.size())
                    self.assertTrue(parent.rect().contains(rect),f'{width}x{height}: {rect} clipped by {type(parent).__name__} {parent.rect()}')
                    parent=parent.parentWidget()

    def test_pause_resume_tabs_log_score_and_repeated_skip_do_not_change_database(self):
        self.open()
        with patch.object(self.service.matches,'play',wraps=self.service.matches.play) as play:
            result,_=self.play_player(skip=False);self.page.timer.stop()
            original=self.dump();self.page.advance_frame()
            self.assertEqual(len(self.page.battle.cards),len(result.players))
            self.assertEqual(self.page.battle.teams[0].identity,'ador')
            self.assertTrue(self.page.battle.logs)
            # Even if the player was scheduled on the right, score and cards
            # must both use the visual left/right order, without changing DB.
            selection=self.page.selection
            reversed_fixture=replace(selection.fixture,agencies=tuple(reversed(selection.fixture.agencies)))
            self.page.selection=replace(selection,fixture=reversed_fixture)
            self.page._configure_battle(result);self.page._render_live()
            self.assertEqual(self.page.battle.teams[0].identity,'ador')
            self.assertTrue(self.page.score_label.text().startswith('ADOR '))
            self.page.selection=selection;self.page._configure_battle(result)
            self.assertIn(self.page.selection.fixture.content_name,self.page.battle.content.text())
            shown=[e for frame in self.page.frames[:self.page.frame_index] for e in frame.events]
            self.assertEqual(sum(self.page.live_scores.values()),sum(e.success for e in shown))
            self.assertEqual(self.page.judgments_shown,len(shown))
            QTest.mouseClick(self.page.pause_button,Qt.MouseButton.LeftButton)
            before=self.page.frame_index;QTest.qWait(650);self.page.advance_frame()
            self.assertTrue(self.page.paused);self.assertEqual(before,self.page.frame_index)
            QTest.mouseClick(self.page.pause_button,Qt.MouseButton.LeftButton)
            self.wait(lambda:self.page.frame_index>before)
            self.page.tabs.setCurrentIndex(3);self.assertTrue(self.page.paused)
            self.page.tabs.setCurrentIndex(1)
            QTest.mouseClick(self.page.details_button,Qt.MouseButton.LeftButton);self.assertTrue(self.page.live_table.isVisible())
            QTest.mouseClick(self.page.skip_button,Qt.MouseButton.LeftButton);self.page.skip();self.page.skip()
            self.assertFalse(self.page.replaying);self.assertEqual(self.page.tabs.currentIndex(),2)
            self.assertEqual(play.call_count,1);self.assertEqual(original,self.dump())
        self.assertEqual(dict(self.page.live_scores),{t['agency_id']:t['total_score'] for t in result.teams})
        for p in result.players:
            card=self.page.battle.cards[p['person_id']]
            self.assertEqual(card.successes,p['base_successes']+p['leader_successes']+p['deathmatch_successes'])
            self.assertEqual(card.flash.state(),QAbstractAnimation.State.Stopped)
        self.assertEqual(self.service.matches.result(result.match_id),result)

    def test_missing_all_photos_and_zero_players_are_safe(self):
        self.open();result,_=self.play_player(skip=False);self.page.timer.stop();original=self.dump()
        self.page.battle.configure('몰수 시각화',self.page.selection.fixture.agencies,[])
        self.assertEqual(len(self.page.battle.cards),0)
        self.page._configure_battle(result)
        self.page.hide();self.assertTrue(self.page.paused)
        self.page.skip();self.assertEqual(original,self.dump())
