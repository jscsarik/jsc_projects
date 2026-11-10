"""Optional Qt Multimedia adapter. Imported lazily only when music exists."""
from pathlib import Path
from PySide6.QtCore import QObject,QUrl,Signal,Slot,Qt


class QtBgmBackend(QObject):
    started=Signal(str)
    ended=Signal(str)
    failed=Signal(str,str)
    availability_changed=Signal(bool)

    def __init__(self,parent=None):
        super().__init__(parent)
        from PySide6.QtMultimedia import QAudioOutput,QMediaDevices,QMediaPlayer
        self.Media=QMediaPlayer;self.Devices=QMediaDevices
        self.devices=QMediaDevices(self)
        self.output=QAudioOutput(self)
        self.player=QMediaPlayer(self);self.player.setAudioOutput(self.output)
        self.current_path='';self._reported=False
        self._pending_position=None;self._autoplay=False
        self.available=self.player.isAvailable() and bool(QMediaDevices.audioOutputs())
        self.reason='' if self.available else '오디오 장치 또는 Multimedia 백엔드를 사용할 수 없습니다.'
        # Multimedia callbacks may originate on decoder threads. Explicit queued
        # QObject slots keep all Python/player control on the GUI thread.
        self.player.mediaStatusChanged.connect(self._status,Qt.ConnectionType.QueuedConnection)
        self.player.playbackStateChanged.connect(self._started,Qt.ConnectionType.QueuedConnection)
        self.player.positionChanged.connect(self._started,Qt.ConnectionType.QueuedConnection)
        self.player.errorOccurred.connect(self._error,Qt.ConnectionType.QueuedConnection)
        self.devices.audioOutputsChanged.connect(self._devices_changed)

    @Slot()
    def _devices_changed(self):
        self.available=self.player.isAvailable() and bool(self.Devices.audioOutputs())
        self.reason='' if self.available else '사용 가능한 오디오 출력 장치가 없습니다.'
        if self.available:self.output.setDevice(self.Devices.defaultAudioOutput())
        else:self.player.pause()
        self.availability_changed.emit(self.available)

    @Slot()
    def _started(self):
        if (self._pending_position is None and not self._reported and self.current_path and self.player.hasAudio()
            and self.player.playbackState()==self.Media.PlaybackState.PlayingState
            and self.player.mediaStatus() in (self.Media.MediaStatus.LoadedMedia,
                                             self.Media.MediaStatus.BufferingMedia,self.Media.MediaStatus.BufferedMedia)):
            self._reported=True;self.started.emit(self.current_path)

    @Slot()
    def _status(self):
        status=self.player.mediaStatus()
        if self._pending_position is not None and status in (self.Media.MediaStatus.LoadedMedia,self.Media.MediaStatus.BufferedMedia):
            position=self._pending_position;self._pending_position=None
            self.player.setPosition(position)
            if self._autoplay:self.player.play()
        if status==self.Media.MediaStatus.EndOfMedia:self.ended.emit(self.current_path)
        elif status==self.Media.MediaStatus.InvalidMedia:self.failed.emit(self.current_path,self.player.errorString() or '손상되었거나 지원하지 않는 음악 파일')
        else:self._started()

    @Slot()
    def _error(self):
        error=self.player.error()
        if error!=self.Media.Error.NoError:self.failed.emit(self.current_path,self.player.errorString() or str(error))

    def load(self,path,autoplay,*,position_ms=0):
        self.player.stop();self.current_path=str(Path(path).resolve());self._reported=False
        self._pending_position=max(0,int(position_ms));self._autoplay=autoplay
        self.player.setSource(QUrl.fromLocalFile(self.current_path))

    def position_ms(self):return self._pending_position if self._pending_position is not None else self.player.position()
    def pause(self):self._autoplay=False;self.player.pause()
    def resume(self):
        self._autoplay=True
        if self._pending_position is None:self.player.play()
    def stop(self):
        self._pending_position=None;self._autoplay=False
        self.player.stop();self.player.setSource(QUrl());self.current_path='';self._reported=False
    def set_volume(self,value):self.output.setVolume(max(0.0,min(1.0,value)))
    def set_muted(self,value):self.output.setMuted(value)
    def close(self):self.stop()
