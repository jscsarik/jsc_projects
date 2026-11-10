"""Own exactly one active game and release all workers before switching slots."""
from contextlib import closing
import logging,sqlite3,time
from PySide6.QtCore import QObject,Signal,Slot,QRunnable,QThreadPool,QTimer,Qt
from PySide6.QtWidgets import QApplication,QMessageBox
from .save_slots import SlotManager
from .save_preview import inspect_save
from .service import GameService
from .ui.start_menu import StartMenu
from .ui.main_window import MainWindow

logger=logging.getLogger(__name__)


class JobSignals(QObject):
    finished=Signal(object,object)


class SlotJob(QRunnable):
    def __init__(self,fn):
        super().__init__();self.fn=fn;self.signals=JobSignals()
    def run(self):
        try:result=self.fn()
        except Exception as error:
            logger.exception('Slot operation failed');self.signals.finished.emit(None,error)
        else:self.signals.finished.emit(result,None)


class StartController(QObject):
    def __init__(self,paths,resource_root,*,legacy_root=None,bgm=None,parent=None):
        super().__init__(parent);self.paths=paths;self.root=resource_root;self.bgm=bgm
        if self.bgm is None:
            from .bgm import BgmManager
            self.bgm=BgmManager(resource_root,paths.config/'bgm_settings.json',self,music_folder=paths.assets/'audio/bgm')
        QApplication.instance().aboutToQuit.connect(self.bgm.shutdown)
        self.manager=SlotManager(paths,resource_root,legacy_root=legacy_root)
        self.title=StartMenu(self.manager);self.game=None;self.active=None;self.lease=None;self.monitor=None
        self.pool=QThreadPool(self);self.job=None
        self.title.continue_requested.connect(self.continue_game)
        self.title.open_requested.connect(self.open_game);self.title.new_requested.connect(self.new_game)
        self.title.delete_requested.connect(self.delete_game);self.title.import_requested.connect(self.import_game)
        self.timer=QTimer(self);self.timer.setInterval(2000);self.timer.timeout.connect(self.poll_save)
        self.title.reload()
    def show(self):
        self.bgm.set_context('title');self.bgm.start();self.title.show()
    def continue_game(self):
        identity=self.manager.latest(self.title.slots)
        if identity is not None:self.open_game(identity)
    def _error(self,label,error):
        logger.warning('%s: %s',label,error,exc_info=isinstance(error,Exception))
        QMessageBox.warning(self.title if self.game is None else self.game,label,str(error)+'\n원본을 초기화하지 않았습니다. 다른 슬롯 또는 보관된 백업을 확인할 수 있습니다.')
    def _job(self,fn,*,open_after=None):
        if self.job or self.game:return
        self.title.set_busy(True);self.job=SlotJob(fn)
        self.open_after=open_after
        self.job.signals.finished.connect(self._job_finished,Qt.ConnectionType.QueuedConnection);self.pool.start(self.job)
    @Slot(object,object)
    def _job_finished(self,result,error):
        self.job=None;self.title.set_busy(False);self.title.reload()
        if error:self._error('슬롯 처리 실패',error)
        elif self.open_after is not None:self.open_game(self.open_after)
    def new_game(self,identity):
        if self.job or self.game:return
        if not self.title.confirm_replace(identity,'덮어쓰기'):return
        self._job(lambda:self.manager.create(identity,approved=True),open_after=identity)
    def import_game(self,source,identity):
        if self.job or self.game:return
        if not self.title.confirm_replace(identity,'가져오기 덮어쓰기'):return
        self._job(lambda:self.manager.import_legacy(source,identity,approved=True))
    def delete_game(self,identity):
        if self.job or self.game:return
        if not self.title.confirm_replace(identity,'삭제'):return
        self._job(lambda:self.manager.delete(identity,approved=True))
    def open_game(self,identity):
        if self.game or self.job:return
        try:
            self.lease=self.manager.lease(identity,active=True);self.manager.prepare_open(identity)
            slot=self.manager.slot(identity)
            service=GameService(self.root,slot.save,storage=slot)
            meta=self.manager.refresh(identity,played=True)
            self.base_playtime=meta.get('playtime_seconds',0);self.started=time.monotonic()
            game=MainWindow(service,bgm=self.bgm,slot_mode=True,before_close=self.before_close)
            self.game=game;self.active=identity
            game.menu_requested.connect(self.return_to_menu);game.closed.connect(self.game_closed)
            game.setWindowTitle(f'IDOL Manager · 슬롯 {identity}')
            self.monitor=sqlite3.connect(slot.save.resolve().as_uri()+'?mode=ro',uri=True,timeout=2)
            self.version=self.monitor.execute('PRAGMA data_version').fetchone()[0]
            self.timer.start();game.show();self.title.hide()
        except Exception as error:
            if self.monitor:self.monitor.close();self.monitor=None
            if self.lease:self.lease.close();self.lease=None
            self.active=None;self.game=None;self._error('불러오기 실패',error)
    def playtime(self):return self.base_playtime+int(max(0,time.monotonic()-self.started))
    def exit_decision(self):
        dialog=QMessageBox(self.game);dialog.setWindowTitle('게임 나가기')
        dialog.setText('저장하겠습니까?')
        dialog.setInformativeText('이미 자동 저장된 진행은 유지됩니다.')
        save=dialog.addButton('저장 후 종료',QMessageBox.ButtonRole.AcceptRole)
        skip=dialog.addButton('저장하지 않고 종료',QMessageBox.ButtonRole.DestructiveRole)
        cancel=dialog.addButton('취소',QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(cancel);dialog.setEscapeButton(cancel);dialog.exec()
        return 'save' if dialog.clickedButton() is save else 'skip' if dialog.clickedButton() is skip else 'cancel'
    def poll_save(self):
        if not self.game or not self.monitor:return
        try:
            version=self.monitor.execute('PRAGMA data_version').fetchone()[0]
            if version!=self.version:
                self.manager.refresh(self.active,saved=True,playtime=self.playtime(),check=False);self.version=version
        except Exception:logger.warning('Metadata update deferred; SQLite is the authority',exc_info=True)
    def before_close(self):
        if self.game is None:return True
        if self.game.job is not None or any(getattr(p,'is_busy',lambda:False)() for p in (self.game.squad_page,self.game.match_page,self.game.special_page,self.game.finals_page,self.game.annual_page)):
            QMessageBox.information(self.game,'저장 작업 진행 중','게임 처리 또는 관전이 끝난 뒤 다시 돌아가기/종료를 선택해 주세요.');return False
        decision=self.exit_decision()
        if decision=='cancel':return False
        if decision=='skip':return True
        while True:
            try:self.manager.save_active(self.active,playtime=self.playtime());return True
            except Exception as error:
                logger.warning('Final save check failed',exc_info=True)
                answer=QMessageBox.warning(self.game,'저장 확인 실패',str(error)+'\n재시도하거나 취소하여 게임 화면을 유지하세요.',QMessageBox.StandardButton.Retry|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)
                if answer!=QMessageBox.StandardButton.Retry:return False
    def return_to_menu(self):
        if self.game:
            game=self.game;game.returning_to_menu=True
            if not game.close():game.returning_to_menu=False
    def game_closed(self):
        old=self.game;returning=old.returning_to_menu
        self.timer.stop()
        if self.monitor:self.monitor.close();self.monitor=None
        self.game=None;self.active=None
        if self.lease:self.lease.close();self.lease=None
        old.deleteLater()
        if returning:self.title.reload();self.title.show_home();self.bgm.set_context('title');self.title.show()
        else:QApplication.instance().quit()
