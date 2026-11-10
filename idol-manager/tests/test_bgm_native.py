"""Native decoder smoke test; no project music is modified or converted."""
from pathlib import Path
import os
import random
import tempfile
import time
import unittest
import wave

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import QEventLoop,QTimer
from idol_manager.bgm import BgmManager
from idol_manager.bgm_backend import QtBgmBackend


class BgmNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        try:
            from PySide6.QtMultimedia import QMediaDevices,QMediaPlayer
            cls.available=bool(QMediaDevices.audioOutputs()) and QMediaPlayer().isAvailable()
        except ImportError:cls.available=False

    def wait(self,predicate,seconds=8):
        loop=QEventLoop();timer=QTimer();timer.setInterval(15)
        timer.timeout.connect(lambda:loop.quit() if predicate() else None)
        timeout=QTimer();timeout.setSingleShot(True);timeout.timeout.connect(loop.quit)
        timer.start();timeout.start(int(seconds*1000));loop.exec();timer.stop();timeout.stop()
        self.assertTrue(predicate(),'실제 Qt 오디오 디코더 응답 시간 초과')

    def test_native_corrupt_mp3_then_unicode_wav_auto_loop(self):
        if not self.available:self.skipTest('No Multimedia backend or audio device')
        with tempfile.TemporaryDirectory(prefix='idol_audio_한글_') as folder:
            root=Path(folder);music=root/'assets/audio/bgm/default';music.mkdir(parents=True)
            (music/'손상 파일.mp3').write_bytes(b'not an mp3 file')
            manager=BgmManager(root,backend_factory=QtBgmBackend,rng=random.Random(2),transition_ms=0,fade_ms=0)
            self.addCleanup(manager.shutdown);manager.set_volume(0)
            with self.assertLogs('idol_manager.bgm',level='WARNING'):
                manager.start();self.wait(lambda:bool(manager.failed['default']) and not manager._loaded and not manager.transition.isActive())
            path=music/'가상 가수 - 테스트 음악.wav'
            with wave.open(str(path),'wb') as audio:
                audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(22050)
                audio.writeframes(b'\x00\x00'*22050)
            played=[];manager.song_started.connect(played.append);manager.refresh()
            self.wait(lambda:manager.current_track and manager.current_track.path==path and manager._started_track)
            self.assertTrue(manager.backend.player.hasAudio())
            self.wait(lambda:manager.backend.player.position()>100)
            self.wait(lambda:len(played)>=2)
            self.assertTrue(all(title=='가상 가수 — 테스트 음악' for title in played))
            manager.shutdown()

    def test_native_context_seek_restored_after_async_load(self):
        if not self.available:self.skipTest('No Multimedia backend or audio device')
        with tempfile.TemporaryDirectory(prefix='idol_resume_한글_') as folder:
            root=Path(folder)
            for category in ('default','battle'):
                path=root/'assets/audio/bgm'/category/'이어 재생.wav';path.parent.mkdir(parents=True)
                with wave.open(str(path),'wb') as audio:
                    audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(22050)
                    audio.writeframes(b'\x00\x00'*22050*12)
            manager=BgmManager(root,transition_ms=0,fade_ms=0)
            self.addCleanup(manager.shutdown);manager.set_volume(0);manager.start()
            self.wait(lambda:manager._started_track)
            manager.backend.player.setPosition(4000)
            self.wait(lambda:manager.backend.position_ms()>=4000)
            manager.set_context('battle');self.wait(lambda:manager.category=='battle' and manager._started_track)
            saved_normal=manager.memories['default'].position
            manager.backend.player.setPosition(6500)
            self.wait(lambda:manager.backend.position_ms()>=6500)
            manager.set_context('default');self.wait(lambda:manager.category=='default' and manager._started_track)
            self.assertGreaterEqual(manager.backend.position_ms(),saved_normal)
            self.assertLess(manager.backend.position_ms(),saved_normal+1500)
            saved_battle=manager.memories['battle'].position
            manager.set_context('battle');self.wait(lambda:manager.category=='battle' and manager._started_track)
            self.assertGreaterEqual(manager.backend.position_ms(),saved_battle)
            self.assertLess(manager.backend.position_ms(),saved_battle+1500)
            # Switch again before the asynchronous decoder reports LoadedMedia.
            for category in ('default','battle','default'):
                manager.set_context(category);manager._reconcile()
            self.wait(lambda:manager.category=='default' and manager._started_track)
            self.assertGreaterEqual(manager.backend.position_ms(),saved_normal)
            manager.shutdown()


if __name__=='__main__':unittest.main()
