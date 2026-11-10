"""Interactive QA copy plus automated geometry checks (separate evidence)."""
from pathlib import Path
import argparse,json,os,sys,time,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','windows')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint,QRect,QTimer,QEvent,QCoreApplication
from PySide6.QtTest import QTest
from idol_manager.service import GameService
from idol_manager.storage import UserPaths,import_save
from idol_manager.ui.main_window import MainWindow
from idol_manager.bgm import BgmManager

def main():
    p=argparse.ArgumentParser();p.add_argument('--hold',action='store_true');p.add_argument('--scale',default='1');a=p.parse_args()
    out=ROOT/'reports/release_qa/followup';folder=out/('gui_'+a.scale);folder.mkdir(exist_ok=True)
    paths=UserPaths(folder/'user_data')
    if not paths.save.exists():import_save(out/'user_before.sqlite3',paths)
    (paths.config/'bgm_settings.json').write_text('{"enabled":false,"muted":true,"volume":0}',encoding='utf8')
    app=QApplication([]);errors=[]
    def error(kind,value,tb):errors.append(''.join(traceback.format_exception(kind,value,tb)));sys.__excepthook__(kind,value,tb)
    sys.excepthook=error
    bgm=BgmManager(ROOT,paths.config/'bgm_settings.json',app,music_folder=paths.assets/'audio/bgm')
    w=MainWindow(GameService(ROOT,paths.save,storage=paths),bgm=bgm)
    w.setWindowTitle('IDOL Manager — FOLLOWUP QA (복사본)');w.resize(800,700);w.show();w.show_squads();QTest.qWait(100)
    (out/'interactive_session.json').write_text(json.dumps(dict(pid=os.getpid(),path=str(paths.save),title=w.windowTitle(),platform=app.platformName(),scale=a.scale)),encoding='utf8')
    if a.hold:return app.exec()
    result=[]
    for width,height in ((800,700),(900,1560),(1280,720),(1920,1080)):
        w.resize(width,height);QTest.qWait(150);page=w.squad_page;pager=w.portrait_layout.tables.get(page.table)
        controls=[page.search,page.filter_combo,page.confirm_button,page.swap_button,page.promote_button,page.demote_button,page.first_leader_button,page.second_leader_button]
        if pager and pager.enabled:controls.extend([pager.previous,pager.next,pager.fields,pager.details])
        for control in controls:
            page.page_scroll.ensureWidgetVisible(control);QTest.qWait(20)
            rect=QRect(control.mapTo(page.page_scroll.viewport(),QPoint()),control.size())
            result.append(dict(width=width,height=height,control=control.text() if hasattr(control,'text') else type(control).__name__,accessible=page.page_scroll.viewport().rect().contains(rect),enabled=control.isEnabled()))
        page.page_scroll.verticalScrollBar().setValue(0);QTest.qWait(30);w.grab().save(str(folder/f'{width}x{height}_top.png'))
        if pager and pager.enabled:page.page_scroll.ensureWidgetVisible(pager.bar);QTest.qWait(30)
        w.grab().save(str(folder/f'{width}x{height}_pager.png'))
        page.page_scroll.ensureWidgetVisible(page.second_leader_button);QTest.qWait(30);w.grab().save(str(folder/f'{width}x{height}_bottom.png'))
    w.close();app.processEvents()
    (folder/'geometry.json').write_text(json.dumps(dict(backend=app.platformName(),scale=a.scale,errors=errors,checks=result,all_accessible=all(r['accessible'] for r in result),evidence='QTest geometry and QWidget renders; independent native desktop check required'),ensure_ascii=False,indent=2),encoding='utf8')
    return int(bool(errors) or not all(r['accessible'] for r in result))
if __name__=='__main__':raise SystemExit(main())
