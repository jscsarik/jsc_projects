"""Application-wide BGM controller; preferences are independent of SQLite."""
from pathlib import Path
import json
import logging
import uuid
from dataclasses import dataclass

from PySide6.QtCore import QObject,QRunnable,QThreadPool,QTimer,Signal,Slot
from .bgm_catalog import CATEGORIES,ShuffleBag,scan_music,song_title

logger=logging.getLogger(__name__)

@dataclass
class PlaybackMemory:
    track: object=None
    index: int=-1
    position: int=0
    paused: bool=False
    announced: bool=False


class BgmPreferences:
    def __init__(self,path):
        self.path=Path(path);self.enabled=True;self.muted=False;self.volume=50
        try:
            data=json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(data.get('enabled'),bool):self.enabled=data['enabled']
            if isinstance(data.get('muted'),bool):self.muted=data['muted']
            if type(data.get('volume')) is int:self.volume=max(0,min(100,data['volume']))
        except FileNotFoundError:pass
        except (OSError,ValueError,TypeError,AttributeError):logger.warning('BGM settings unreadable: %s',self.path,exc_info=True)

    def save(self):
        temporary=self.path.with_name(f'{self.path.name}.{uuid.uuid4().hex}.tmp')
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temporary.write_text(json.dumps({'version':1,'enabled':self.enabled,'muted':self.muted,'volume':self.volume},indent=2),encoding='utf-8')
            temporary.replace(self.path)
        except OSError:
            logger.warning('BGM settings save failed: %s',self.path,exc_info=True)
            return False
        finally:
            try:temporary.unlink(missing_ok=True)
            except OSError:pass
        return True


class ScanSignals(QObject):
    finished=Signal(object)


class MusicScan(QRunnable):
    def __init__(self,root,resolver,extra_folder=None):
        super().__init__();self.root,self.resolver=root,resolver;self.extra_folder=extra_folder;self.signals=ScanSignals()

    def run(self):
        try:result=scan_music(self.root,self.resolver,extra_folder=self.extra_folder) if self.extra_folder else scan_music(self.root,self.resolver)
        except Exception:
            logger.exception('BGM scan failed');result={c:() for c in CATEGORIES}
        self.signals.finished.emit(result)


def qt_backend(parent):
    from .bgm_backend import QtBgmBackend
    return QtBgmBackend(parent)


class BgmManager(QObject):
    song_started=Signal(str)
    state_changed=Signal()
    playlists_changed=Signal()

    def __init__(self,root,settings_path=None,parent=None,*,backend_factory=qt_backend,rng=None,
                 title_resolver=song_title,transition_ms=120,fade_ms=600,music_folder=None):
        super().__init__(parent)
        self.root=Path(root).resolve()
        self.music_folder=music_folder
        self.preferences=BgmPreferences(settings_path or self.root/'data/bgm_settings.json')
        self.factory,self.resolver=backend_factory,title_resolver
        self.bags={c:ShuffleBag(rng) for c in CATEGORIES};self.failed={c:{} for c in CATEGORIES}
        self.category='default';self.desired_category='default';self.current_track=None
        self.memories={c:PlaybackMemory() for c in CATEGORIES}
        self._resume_announced=False
        self.backend=None;self.paused=False;self.scanning=False;self._scan_again=False
        self._loaded=False;self._started_track=False;self._closed=False;self._started=False
        self._force_next=False;self._generation=0;self.status='음악 목록을 불러오기 전입니다.'
        self.gain=1.0;self.fade_ms=max(0,fade_ms);self._fade_phase=None;self._fade_steps=0
        self.pool=QThreadPool(self);self.pool.setMaxThreadCount(1);self.scan_job=None
        self.transition=QTimer(self);self.transition.setSingleShot(True);self.transition.setInterval(transition_ms);self.transition.timeout.connect(self._reconcile)
        self.fade=QTimer(self);self.fade.setInterval(30);self.fade.timeout.connect(self._fade_tick)
        self.watchdog=QTimer(self);self.watchdog.setSingleShot(True);self.watchdog.setInterval(10000)
        self.watchdog.timeout.connect(lambda:self._on_failed(str(self.current_track.path) if self.current_track else '', '음악을 제한 시간 내 시작하지 못했습니다.'))
        self.save_timer=QTimer(self);self.save_timer.setSingleShot(True);self.save_timer.setInterval(250);self.save_timer.timeout.connect(self.flush_settings)

    @property
    def enabled(self):return self.preferences.enabled
    @property
    def muted(self):return self.preferences.muted
    @property
    def volume(self):return self.preferences.volume

    def start(self):
        if self._started or self._closed:return
        self._started=True;self.refresh()

    def refresh(self):
        if self._closed:return
        if self.scanning:self._scan_again=True;return
        self.scanning=True;self.scan_job=MusicScan(self.root,self.resolver,self.music_folder)
        self.scan_job.signals.finished.connect(self._scanned);self.pool.start(self.scan_job);self.state_changed.emit()

    @Slot(object)
    def _scanned(self,result):
        self.scanning=False;self.scan_job=None
        if self._closed:return
        for category in CATEGORIES:
            self.bags[category].update(result[category])
            signatures={t.path:t.signature for t in result[category]}
            self.failed[category]={p:s for p,s in self.failed[category].items() if signatures.get(p)==s}
        if self.current_track:
            replacement=self.bags[self.category].tracks.get(self.current_track.path)
            if replacement is None or replacement.signature!=self.current_track.signature:
                self._force_next=True
        self.playlists_changed.emit();self.transition.start()
        if self._scan_again:self._scan_again=False;self.refresh()

    def set_context(self,category):
        category=str(category).lower()
        if category not in CATEGORIES:raise ValueError('BGM context must be default, battle or title')
        if self._closed or category==self.desired_category:return
        self.desired_category=category;self.transition.start();self.state_changed.emit()

    def _ensure_backend(self):
        if self.backend is not None:return bool(self.backend.available)
        try:
            backend=self.factory(self)
            backend.started.connect(self._on_started);backend.ended.connect(self._on_ended)
            backend.failed.connect(self._on_failed);backend.availability_changed.connect(self._availability)
            self.backend=backend;self._apply_output()
        except Exception:
            logger.warning('BGM Multimedia backend unavailable',exc_info=True)
            self.status='음악 재생 백엔드를 사용할 수 없습니다.';return False
        return bool(self.backend.available)

    def _apply_output(self):
        if self.backend is None:return
        try:
            self.backend.set_volume(self.volume/100*self.gain)
            self.backend.set_muted(self.muted or not self.enabled)
        except Exception:logger.warning('BGM output control failed',exc_info=True)

    def set_volume(self,value):
        if type(value) is not int:return
        self.preferences.volume=max(0,min(100,value));self._apply_output();self.save_timer.start();self.state_changed.emit()

    def set_muted(self,value):
        self.preferences.muted=bool(value);self._apply_output();self.save_timer.start();self.state_changed.emit()

    def set_enabled(self,value):
        self.preferences.enabled=bool(value);self._apply_output();self.save_timer.start()
        if not self.enabled:self._remember();self._stop();self.status='BGM 꺼짐'
        else:self.transition.start()
        self.state_changed.emit()

    def toggle_pause(self):self.set_paused(not self.paused)

    def set_paused(self,value):
        self.paused=bool(value)
        self.memories[self.category].paused=self.paused
        if self.backend and self._loaded:
            try:
                if self.paused:self.backend.pause();self.watchdog.stop()
                else:
                    self.backend.resume()
                    if not self._started_track:self.watchdog.start()
                self.status='일시정지' if self.paused else ('재생 중' if self._started_track else '음악을 불러오는 중입니다.')
            except Exception:logger.warning('BGM pause/resume failed',exc_info=True)
        if not self.paused and not self._loaded:self.transition.start()
        self.state_changed.emit()

    def next_track(self):
        if self._closed:return
        self._force_next=True;self.transition.start()

    def _remember(self):
        memory=self.memories[self.category]
        memory.track=self.current_track;memory.paused=self.paused
        if self._loaded and self.backend:
            self.backend.pause()
            memory.position=max(0,int(self.backend.position_ms()))
        tracks=list(self.bags[self.category].tracks)
        memory.index=tracks.index(memory.track.path) if memory.track and memory.track.path in tracks else -1
        memory.announced=self._started_track or self._resume_announced

    def _stop(self):
        self.fade.stop();self._fade_phase=None;self.gain=1;self.watchdog.stop();self._loaded=False
        self._generation+=1
        if self.backend:
            try:self.backend.stop()
            except Exception:logger.warning('BGM stop failed',exc_info=True)

    def _reconcile(self):
        if self._closed:return
        if not self.enabled:self.status='BGM 꺼짐';self.state_changed.emit();return
        switch=self.category!=self.desired_category or self._force_next
        if self.fade.isActive():
            if self._fade_phase=='out' and switch:return
            self.fade.stop();self._fade_phase=None
        if switch and self._loaded and not self.paused and self.fade_ms:
            self._fade_phase='out';self._fade_steps=max(1,self.fade_ms//2//30);self.fade.start();return
        self._load_desired(switch)

    def _load_desired(self,switch):
        self._fade_phase=None
        changed=self.category!=self.desired_category
        if switch:
            if changed:self._remember()
            self._stop();self.current_track=None
        self.category=self.desired_category;self._force_next=False
        memory=self.memories[self.category]
        if changed:
            if memory.track is not None:self.paused=memory.paused
            else:memory.paused=self.paused
        if switch and not changed:
            memory.track=None;memory.position=0;memory.announced=False
        if not self.bags[self.category].tracks:
            self.status={'default':'일반','battle':'배틀','title':'타이틀'}[self.category]+' BGM이 없습니다.'
            self.state_changed.emit();return
        if not self._ensure_backend():
            self.status=getattr(self.backend,'reason','음악 재생 백엔드를 사용할 수 없습니다.')
            self.state_changed.emit();return
        if self._loaded:
            self.gain=1.0;self._apply_output();self.state_changed.emit();return
        track=self.current_track or memory.track
        if track is None or track.path not in self.bags[self.category].tracks or track.path in self.failed[self.category]:
            track=self.bags[self.category].next(self.failed[self.category])
            memory.position=0;memory.announced=False
        elif self.bags[self.category].tracks[track.path].signature!=track.signature:
            track=self.bags[self.category].tracks[track.path];memory.position=0;memory.announced=False
        if track is None:
            self.status='재생 가능한 음악이 없습니다. 파일을 확인하고 목록을 새로고침해 주세요.'
            self.state_changed.emit();return
        self.current_track=track
        memory.track=track;memory.index=list(self.bags[self.category].tracks).index(track.path)
        self._resume_announced=memory.announced
        if not track.path.is_file():
            self._on_failed(str(track.path),'음악 파일이 이동되었거나 삭제되었습니다.');return
        self._loaded=True;self._started_track=False;self._generation+=1
        self.gain=0.0 if self.fade_ms and not self.paused else 1.0;self._apply_output()
        self.status='일시정지' if self.paused else '음악을 불러오는 중입니다.'
        if not self.paused:self.watchdog.start()
        try:self.backend.load(track.path,not self.paused,position_ms=memory.position)
        except Exception as error:self._on_failed(str(track.path),str(error));return
        if self.fade_ms and not self.paused and self._loaded:
            self._fade_phase='in';self._fade_steps=max(1,self.fade_ms//2//30);self.fade.start()
        self.state_changed.emit()

    def _fade_tick(self):
        step=1/self._fade_steps
        if self._fade_phase=='out':
            self.gain=max(0,self.gain-step);self._apply_output()
            if self.gain<=0:
                self.fade.stop();self._load_desired(self.category!=self.desired_category or self._force_next)
        else:
            self.gain=min(1,self.gain+step);self._apply_output()
            if self.gain>=1:self.fade.stop();self._fade_phase=None

    def _is_current(self,path):
        return bool(not self._closed and self.current_track and str(self.current_track.path)==path)

    @Slot(str)
    def _on_started(self,path):
        if not self._is_current(path) or self._started_track:return
        self.watchdog.stop();self._started_track=True;self.status='재생 중'
        if not self._resume_announced:self.song_started.emit(self.current_track.title)
        self.memories[self.category].announced=True;self.state_changed.emit()

    def _queue_next(self):
        self.memories[self.category]=PlaybackMemory(paused=self.paused)
        self.current_track=None;self._started_track=False;self._resume_announced=False
        self._loaded=False;self._force_next=True;self.watchdog.stop();self.transition.start()

    @Slot(str)
    def _on_ended(self,path):
        if not self._is_current(path):return
        if not self._started_track:self._on_failed(path,'오디오 판정 없이 종료된 음악 파일');return
        self._queue_next()

    @Slot(str,str)
    def _on_failed(self,path,message):
        if not self._is_current(path):return
        track=self.current_track
        if self.failed[self.category].get(track.path)==track.signature:return
        self.failed[self.category][track.path]=track.signature
        logger.warning('BGM playback failed: %s: %s',path,message)
        self.status='음악 오류: '+message;self._queue_next();self.state_changed.emit()

    @Slot(bool)
    def _availability(self,available):
        if self._closed:return
        if available:self.transition.start()
        else:
            self._remember();self._stop();self.status=getattr(self.backend,'reason','오디오 장치를 사용할 수 없습니다.');self.state_changed.emit()

    def flush_settings(self):
        self.save_timer.stop()
        if not self.preferences.save():self.status='음악 설정을 저장할 수 없습니다.';self.state_changed.emit()

    def shutdown(self):
        if self._closed:return
        self._closed=True;self.transition.stop();self.watchdog.stop();self.fade.stop()
        if self.save_timer.isActive():self.flush_settings()
        self._stop()
        if self.backend:
            try:self.backend.close()
            except Exception:logger.warning('BGM backend shutdown failed',exc_info=True)
        self.pool.waitForDone()
