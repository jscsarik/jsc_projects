import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon

from .config import ROOT
from .service import GameService
from .ui.main_window import MainWindow
from .bgm import BgmManager
from .storage import user_paths,install_root
from .start_controller import StartController


def run() -> int:
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('IDOLManager.Game')
    application = QApplication(sys.argv)
    application.setWindowIcon(QIcon(str(ROOT/'assets/title/logo.png')))
    application.setApplicationName("IDOL Manager")
    application.setApplicationVersion('0.37.8')
    application.setOrganizationName("IDOL Manager")
    try:
        paths=user_paths();paths.ensure()
        from .ui.theme_manager import ThemeManager
        ThemeManager(application,paths.config/'appearance.ini')
        if '--self-check' in sys.argv:
            import faulthandler
            application._qa_fault_log=(paths.logs/'native-fault.log').open('w',encoding='utf8')
            faulthandler.enable(file=application._qa_fault_log)
        logging.basicConfig(filename=paths.logs / "idol_manager.log", encoding="utf-8", level=logging.WARNING)
        bgm=BgmManager(ROOT,paths.config/'bgm_settings.json',parent=application,music_folder=paths.assets/'audio/bgm')
        application.aboutToQuit.connect(bgm.shutdown)
        controller=StartController(paths,ROOT,legacy_root=ROOT if not getattr(sys,'frozen',False) else install_root(),bgm=bgm,parent=application)
        application.start_controller=controller
        if '--self-check' in sys.argv:
            from .start_runtime_check import attach
            attach(controller,paths)
    except Exception as error:
        logging.exception("Startup failed")
        QMessageBox.critical(None, "실행 실패", f"프로그램을 시작할 수 없습니다.\n{error}")
        return 1
    controller.show()
    return application.exec()
