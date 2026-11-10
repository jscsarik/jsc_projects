from pathlib import Path
from contextlib import closing
from dataclasses import replace
import json
import os
import random
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QObject,Signal,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from idol_manager.bgm import BgmManager,BgmPreferences
from idol_manager.bgm_catalog import BgmTrack,ShuffleBag,scan_music,song_title
from idol_manager.service import GameService
from idol_manager.ui.main_window import MainWindow
from idol_manager.ui.bgm_controls import MusicToast


class FakeAudio(QObject):
    started=Signal(str);ended=Signal(str);failed=Signal(str,str);availability_changed=Signal(bool)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.available=True;self.reason='no test device';self.loads=[];self.current=''
        self.playing=False;self.volume=0;self.muted=False;self.stops=0
        self.position=0

    def load(self,path,autoplay,*,position_ms=0):
        self.position=position_ms
        self.current=str(path);self.loads.append((self.current,autoplay));self.playing=autoplay
        if autoplay:self.started.emit(self.current)

    def pause(self):self.playing=False
    def position_ms(self):return self.position
    def resume(self):
        self.playing=True
        if self.current:self.started.emit(self.current)
    def stop(self):self.stops+=1;self.playing=False;self.current=''
    def close(self):self.stop()
    def set_volume(self,value):self.volume=value
    def set_muted(self,value):self.muted=value


class BgmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='idol_bgm_한글_');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.managers=[]

    def wait(self,predicate,seconds=5):
        end=time.monotonic()+seconds
        while not predicate() and time.monotonic()<end:QTest.qWait(10);time.sleep(.005)
        self.assertTrue(predicate(),'BGM 비동기 작업 시간 초과')

    def music(self,category,name):
        folder=self.root/'assets/audio/bgm'/category;folder.mkdir(parents=True,exist_ok=True)
        path=folder/name;path.write_bytes(b'test audio');return path.resolve()

    def manager(self,**kwargs):
        manager=BgmManager(self.root,backend_factory=kwargs.pop('backend_factory',FakeAudio),
                           rng=random.Random(17),transition_ms=0,fade_ms=kwargs.pop('fade_ms',0),**kwargs)
        self.managers.append(manager);self.addCleanup(manager.shutdown)
        return manager

    def start(self,manager):
        manager.start();self.wait(lambda:not manager.scanning and bool(manager.current_track))

    def test_title_music_and_return_from_game(self):
        title=self.music('title','윤하 - 혜성 (Inst.).mp3')
        normal=self.music('default','일반.wav')
        manager=self.manager();manager.set_context('title');self.start(manager)
        self.wait(lambda:manager.current_track.path==title)
        manager.set_context('default');self.wait(lambda:manager.current_track.path==normal)
        manager.set_context('title');self.wait(lambda:manager.current_track.path==title)

    def test_independent_positions_pause_and_shuffle_survive_switches(self):
        for category in ('default','battle'):
            for i in range(3):self.music(category,f'{i}.wav')
        manager=self.manager();self.start(manager);audio=manager.backend
        normal=manager.current_track;remaining=list(manager.bags['default'].remaining)
        audio.position=80000;manager.set_context('battle');self.wait(lambda:manager.category=='battle')
        battle=manager.current_track;audio.position=45000
        manager.set_context('default');self.wait(lambda:manager.category=='default')
        self.assertEqual(manager.current_track,normal);self.assertEqual(audio.position,80000)
        self.assertEqual(manager.bags['default'].remaining,remaining)
        manager.set_paused(True);manager.set_context('battle');self.wait(lambda:manager.category=='battle')
        self.assertEqual(manager.current_track,battle);self.assertEqual(audio.position,45000)
        self.assertTrue(audio.playing)
        audio.position=46000;manager.set_context('default');self.wait(lambda:manager.category=='default')
        self.assertTrue(manager.paused);self.assertFalse(audio.playing);self.assertEqual(audio.position,80000)
        manager.set_paused(False);manager.set_enabled(False);manager.set_enabled(True)
        self.wait(lambda:manager._loaded);self.assertEqual(audio.position,80000)

    def test_rapid_loaded_switches_keep_each_position_and_next_resets(self):
        for category in ('default','battle'):self.music(category,'only.wav')
        manager=self.manager();self.start(manager);audio=manager.backend;audio.position=12345
        for _ in range(8):
            manager.set_context('battle');self.wait(lambda:manager.category=='battle')
            audio.position=54321
            manager.set_context('default');self.wait(lambda:manager.category=='default')
            self.assertEqual(audio.position,12345)
        manager.next_track();self.wait(lambda:audio.position==0)

    def test_scan_two_categories_unicode_absolute_paths_extensions_and_titles(self):
        expected=self.music('default','아이브 2026 - 곡 이름 (Inst.).MP3')
        self.music('battle','English Artist - Round 1.WAV');self.music('default','미분류.mp3')
        self.music('default','ignore.flac')
        catalog=scan_music(self.root)
        self.assertEqual(len(catalog['default']),2);self.assertEqual(len(catalog['battle']),1)
        self.assertTrue(all(t.path.is_absolute() for tracks in catalog.values() for t in tracks))
        self.assertIn(expected,{t.path for t in catalog['default']})
        self.assertEqual(song_title(expected),'아이브 2026 — 곡 이름 (Inst.)')
        self.assertEqual(song_title('NMIXX-Tank(inst.).mp3'),'NMIXX-Tank(inst.).mp3')
        self.assertEqual(song_title('Solo.wav'),'Solo.wav')

    def test_missing_empty_folders_created_and_no_backend_required(self):
        with patch('idol_manager.bgm.qt_backend',side_effect=AssertionError('must not construct player')):
            manager=self.manager(backend_factory=lambda *_: (_ for _ in ()).throw(AssertionError('empty folder')))
            manager.start();self.wait(lambda:not manager.scanning)
            QTest.qWait(40)
        self.assertTrue((self.root/'assets/audio/bgm/default').is_dir())
        self.assertTrue((self.root/'assets/audio/bgm/battle').is_dir())
        self.assertIsNone(manager.backend);self.assertIsNone(manager.current_track)

    def test_shuffle_bag_unique_cycles_no_boundary_repeat_and_independent_categories(self):
        for category in ('default','battle'):
            for i in range(4):self.music(category,f'{i}.mp3')
        tracks=scan_music(self.root)
        bags={key:ShuffleBag(random.Random(3)) for key in tracks}
        for key in bags:bags[key].update(tracks[key])
        sequence=[bags['default'].next().path for _ in range(40)]
        for start in range(0,40,4):self.assertEqual(len(set(sequence[start:start+4])),4)
        self.assertTrue(all(a!=b for a,b in zip(sequence,sequence[1:])))
        self.assertEqual(len(bags['battle'].remaining),4)

    def test_single_song_end_repeats_without_looping_errors(self):
        path=self.music('default','한 곡.wav');manager=self.manager();self.start(manager)
        manager.backend.ended.emit(str(path));self.wait(lambda:len(manager.backend.loads)==2)
        self.assertEqual(manager.current_track.path,path)
        self.assertEqual(len(manager.failed['default']),0)

    def test_large_playlist_refresh_keeps_unplayed_tracks_without_a_fixed_limit(self):
        tracks=tuple(BgmTrack(self.root/f'{i}.mp3',str(i),(1,1)) for i in range(1200))
        bag=ShuffleBag(random.Random(5));bag.update(tracks)
        self.assertEqual(len(bag.remaining),1200)
        played=bag.next().path;remaining=set(bag.remaining)
        bag.update(tracks)
        self.assertEqual(set(bag.remaining),remaining);self.assertNotIn(played,bag.remaining)
        extra=BgmTrack(self.root/'새 곡.mp3','새 곡',(1,2));bag.update((*tracks,extra))
        self.assertEqual(set(bag.remaining),remaining|{extra.path})

    def test_empty_default_can_enter_battle_and_volume_boundaries(self):
        battle=self.music('battle','Only battle.wav');manager=self.manager();manager.start()
        self.wait(lambda:not manager.scanning);QTest.qWait(30)
        self.assertIsNone(manager.current_track)
        manager.set_context('battle');self.wait(lambda:manager.current_track is not None)
        self.assertEqual(manager.current_track.path,battle)
        for value,expected in ((0,0),(100,1),(-5,0),(150,1)):
            manager.set_volume(value);self.assertEqual(manager.backend.volume,expected)

    def test_same_category_keeps_track_and_backend_and_no_repeat_notification(self):
        self.music('default','A - One.mp3');self.music('default','B - Two.mp3')
        manager=self.manager();seen=[];manager.song_started.connect(seen.append);self.start(manager)
        backend=manager.backend;track=manager.current_track
        for _ in range(8):manager.set_context('default')
        QTest.qWait(50)
        self.assertIs(manager.backend,backend);self.assertEqual(manager.current_track,track)
        self.assertEqual(len(backend.loads),1);self.assertEqual(seen,[track.title])

    def test_category_switch_and_return_and_empty_battle_waits_silently(self):
        self.music('default','A.mp3');battle=self.music('battle','B.mp3')
        manager=self.manager();self.start(manager)
        manager.set_context('battle');self.wait(lambda:manager.category=='battle')
        self.assertEqual(manager.current_track.path,battle)
        manager.set_context('default');self.wait(lambda:manager.category=='default')
        battle.unlink();manager.refresh();self.wait(lambda:not manager.scanning)
        manager.set_context('battle');self.wait(lambda:manager.category=='battle')
        self.assertIsNone(manager.current_track);self.assertIn('없습니다',manager.status)
        self.assertFalse(manager.backend.playing)

    def test_refresh_new_song_without_restarting_existing_and_deleted_current_skipped(self):
        first=self.music('default','First.mp3');manager=self.manager();self.start(manager)
        second=self.music('default','Second.wav');manager.refresh()
        self.wait(lambda:not manager.scanning and len(manager.bags['default'].tracks)==2)
        self.assertEqual(len(manager.backend.loads),1)
        first.unlink();manager.refresh();self.wait(lambda:manager.current_track and manager.current_track.path==second)
        self.assertEqual(manager.current_track.path,second)

    def test_corrupt_files_skipped_once_then_wait_all_failed_retry_after_file_change(self):
        paths={self.music('default',f'{i}.mp3') for i in range(3)}
        manager=self.manager();self.start(manager)
        with self.assertLogs('idol_manager.bgm',level='WARNING'):
            for count in range(3):
                path=manager.current_track.path
                manager.backend.failed.emit(str(path),'corrupt')
                self.wait(lambda:len(manager.failed['default'])==count+1 and (not manager.transition.isActive()))
        QTest.qWait(50)
        self.assertEqual(len(manager.backend.loads),3);self.assertIn('재생 가능한 음악이 없습니다',manager.status)
        chosen=next(iter(paths));chosen.write_bytes(b'changed audio signature')
        manager.refresh();self.wait(lambda:manager.current_track and manager.current_track.path==chosen and manager._loaded)
        self.assertNotIn(chosen,manager.failed['default'])

    def test_stale_source_error_cannot_skip_current_category(self):
        default=self.music('default','A.mp3');battle=self.music('battle','B.mp3')
        manager=self.manager();self.start(manager);manager.set_context('battle')
        self.wait(lambda:manager.current_track.path==battle)
        count=len(manager.backend.loads);manager.backend.failed.emit(str(default),'old source')
        QTest.qWait(40);self.assertEqual(len(manager.backend.loads),count)

    def test_volume_mute_enabled_settings_atomic_persist_and_pause_context_stays_paused(self):
        self.music('default','A.mp3');battle=self.music('battle','B.mp3')
        manager=self.manager();self.start(manager)
        manager.set_volume(23);manager.set_muted(True)
        self.assertAlmostEqual(manager.backend.volume,.23);self.assertTrue(manager.backend.muted)
        manager.set_paused(True);manager.set_context('battle')
        self.wait(lambda:manager.current_track.path==battle)
        self.assertFalse(manager.backend.playing);self.assertFalse(manager.backend.loads[-1][1])
        manager.set_paused(False);self.assertTrue(manager.backend.playing)
        manager.set_enabled(False);manager.shutdown()
        restarted=self.manager()
        self.assertEqual(restarted.volume,23);self.assertTrue(restarted.muted);self.assertFalse(restarted.enabled)
        self.assertFalse(list((self.root/'data').glob('*.tmp')))

    def test_pause_resume_same_song_does_not_emit_new_song_notification(self):
        self.music('default','A.mp3');manager=self.manager();seen=[]
        manager.song_started.connect(seen.append);self.start(manager)
        manager.set_paused(True);manager.set_paused(False)
        self.assertEqual(len(seen),1)

    def test_no_device_and_unavailable_multimedia_does_not_raise_or_mark_songs_corrupt(self):
        self.music('default','A.mp3')
        def unavailable(parent):
            audio=FakeAudio(parent);audio.available=False;return audio
        manager=self.manager(backend_factory=unavailable);manager.start()
        self.wait(lambda:not manager.scanning);QTest.qWait(30)
        self.assertFalse(manager._loaded);self.assertFalse(manager.failed['default'])
        manager.backend.available=True;manager.backend.availability_changed.emit(True)
        self.wait(lambda:manager._loaded)
        with self.assertLogs('idol_manager.bgm',level='WARNING'):
            other=self.manager(backend_factory=lambda *_: (_ for _ in ()).throw(ImportError('no Multimedia')))
            other.start();self.wait(lambda:not other.scanning);QTest.qWait(40)
        self.assertFalse(other._loaded)

    def test_fast_context_changes_and_fade_cancellation_do_not_restart_or_silence_current(self):
        self.music('default','A.mp3');self.music('battle','B.mp3')
        manager=self.manager(fade_ms=300);self.start(manager)
        self.wait(lambda:not manager.fade.isActive())
        manager.set_context('battle');self.wait(lambda:manager._fade_phase=='out')
        manager.set_context('default');self.wait(lambda:not manager.fade.isActive())
        self.assertEqual(manager.category,'default');self.assertEqual(len(manager.backend.loads),1)
        self.assertEqual(manager.gain,1)
        manager.set_context('battle');manager.set_context('default');QTest.qWait(50)
        self.assertEqual(len(manager.backend.loads),1)

    def test_volume_mute_changes_during_crossfade_stay_effective(self):
        self.music('default','A.mp3');self.music('battle','B.mp3')
        manager=self.manager(fade_ms=120);self.start(manager)
        self.wait(lambda:not manager.fade.isActive());manager.set_context('battle')
        manager.set_volume(77);manager.set_muted(True)
        self.wait(lambda:manager.category=='battle' and not manager.fade.isActive())
        self.assertAlmostEqual(manager.backend.volume,.77);self.assertTrue(manager.backend.muted)

    def test_bad_settings_file_and_readonly_save_error_are_nonfatal(self):
        path=self.root/'settings.json';path.write_text('bad JSON',encoding='utf-8')
        with self.assertLogs('idol_manager.bgm',level='WARNING'):prefs=BgmPreferences(path)
        self.assertEqual(prefs.volume,50)
        with patch.object(Path,'replace',side_effect=OSError('denied')),self.assertLogs('idol_manager.bgm',level='WARNING'):
            self.assertFalse(prefs.save())

    def test_toast_1500ms_then_300ms_fade_is_mouse_transparent_and_auto_hides(self):
        parent=QApplication.activeWindow()
        from PySide6.QtWidgets import QWidget
        window=QWidget();window.resize(800,200);window.show();self.addCleanup(window.close)
        toast=MusicToast(window);toast.show_song('Artist — Title')
        self.assertTrue(toast.isVisible());self.assertTrue(toast.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        self.assertEqual(toast.hold.interval(),1500);self.assertEqual(toast.animation.duration(),300)
        QTest.qWait(1000);self.assertTrue(toast.isVisible())
        self.wait(lambda:not toast.isVisible(),seconds=2)

    def test_window_controls_and_real_view_state_context_only_no_game_data_writes(self):
        self.music('default','A.mp3');self.music('battle','B.mp3')
        manager=self.manager();service=GameService(self.root)
        with closing(service.database.connect()) as c:before=list(c.iterdump())
        window=MainWindow(service,bgm=manager);self.addCleanup(window.close);window.show()
        self.wait(lambda:manager.current_track is not None)
        initial=manager.current_track.path
        for method in (window.show_roster,window.show_draft,window.show_squads,window.show_schedule,window.show_matches):method()
        QTest.qWait(30);self.assertEqual(manager.current_track.path,initial);self.assertEqual(len(manager.backend.loads),1)
        page=window.match_page
        self.assertFalse(page.replaying);self.assertEqual(manager.desired_category,'default')
        page.replaying=True;page.tabs.setTabEnabled(1,True);page.tabs.setCurrentIndex(1);page.battle_active_changed.emit(True)
        self.wait(lambda:manager.category=='battle')
        page.tabs.setCurrentIndex(3);self.wait(lambda:manager.category=='default')
        page.tabs.setCurrentIndex(1);self.wait(lambda:manager.category=='battle')
        page.replaying=False;page.battle_active_changed.emit(False);self.wait(lambda:manager.category=='default')
        controls=window.bgm_controls
        controls.volume_slider.setValue(31);controls.muted_box.setChecked(True)
        self.assertEqual(manager.volume,31);self.assertTrue(manager.muted)
        controls.enabled_box.setChecked(False);self.assertFalse(manager.enabled)
        with closing(service.database.connect()) as c:self.assertEqual(before,list(c.iterdump()))
        self.assertTrue(manager.preferences.path.is_relative_to(self.root))


if __name__=='__main__':unittest.main()
