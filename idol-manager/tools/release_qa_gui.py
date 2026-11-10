"""Native GUI / measured read-only navigation using an isolated save copy."""
from pathlib import Path
from contextlib import closing
from collections import defaultdict
import argparse,sqlite3,sys,time,json,gc,statistics,os
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.release_qa import OUT,Monitor,rss,save,protect_connections

def main():
    p=argparse.ArgumentParser();p.add_argument('--bench',action='store_true');p.add_argument('--startup',action='store_true');p.add_argument('--scale',default='1');p.add_argument('--width',type=int,default=1500);a=p.parse_args()
    protect_connections()
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer,QCoreApplication,QEvent
    from PySide6.QtTest import QTest
    from idol_manager.service import GameService
    from idol_manager.ui.main_window import MainWindow
    folder=OUT/('gui_'+a.scale);folder.mkdir(exist_ok=True)
    path=folder/'qa.sqlite3'
    with closing(sqlite3.connect((OUT/'user_save_snapshot.sqlite3').as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(path)) as dst:src.backup(dst)
    (folder/'bgm_settings.json').write_text('{"enabled":false,"muted":true,"volume":25}',encoding='utf8')
    startup=time.perf_counter();app=QApplication([]);times=defaultdict(list);errors=[]
    import traceback
    def qt_error(kind,value,tb):
        errors.append(''.join(traceback.format_exception(kind,value,tb)))
        sys.__excepthook__(kind,value,tb)
    sys.excepthook=qt_error
    def measure(name,fn):
        t=time.perf_counter();v=fn();times[name].append(time.perf_counter()-t);return v
    with Monitor() as monitor:
        service=measure('save_load',lambda:GameService(ROOT,path))
        w=measure('main_window_construct',lambda:MainWindow(service));w.setWindowTitle('IDOL Manager — QA 전용 복사본');w.resize(a.width,950);w.show();QTest.qWait(50)
        exposed=QTest.qWaitForWindowExposed(w,5000)
        times['qapplication_to_exposed'].append(time.perf_counter()-startup)
        if a.startup:
            save('startup.json',dict(seconds=times['qapplication_to_exposed'][0],exposed=exposed,platform=app.platformName(),scope='QApplication creation through native window exposure; excludes Python/imports and QA-only DB copy',resources=monitor.result()))
            w.close();return 0
        save('gui_session.json',dict(pid=os.getpid(),path=str(path),scale=a.scale,platform=app.platformName(),screen=app.primaryScreen().availableGeometry().getRect()))
        if not a.bench:return app.exec()
        navigations=[]
        for iteration in range(3):
            for button,page in w.navigation_pages:
                measure('page:'+button.text(),button.click);QTest.qWait(40)
                navigations.append(dict(page=button.text(),visible=w.pages.currentWidget() is page,iteration=iteration))
            w.grab().save(str(folder/f'navigation_{iteration}.png'))
        person=next(p['id'] for p in service.profiles.search() if p['exact'])
        memory=[]
        for i in range(20):
            measure('profile_open',lambda:w.profiles.open(person));QTest.qWait(20)
            if w.profiles.dialog:w.profiles.dialog.close()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents();gc.collect()
            memory.append(dict(iteration=i,rss=rss(),portrait_tables=len(w.portrait_layout.tables),layouts=len(w.portrait_layout.boxes)))
        for i in range(10):measure('records_players',service.records.players)
        for width,height in ((1920,1080),(900,1560),(800,700)):
            w.resize(width,height);app.processEvents();QTest.qWait(120);w.show_squads();QTest.qWait(80)
            w.grab().save(str(folder/f'layout_{width}x{height}.png'))
        w.close();app.processEvents()
    metrics=[]
    for name,values in times.items():
        s=sorted(values);metrics.append(dict(operation=name,count=len(s),mean=statistics.mean(s),median=statistics.median(s),p95=s[max(0,__import__('math').ceil(len(s)*.95)-1)],maximum=max(s),p95_limit='small n; descriptive only' if len(s)<20 else 'nearest rank'))
    from tools.simulate_game import csvfile
    csvfile(OUT/f'gui_timings_{a.scale}.csv',metrics)
    save(f'gui_benchmark_{a.scale}.json',dict(metrics=metrics,navigations=navigations,memory_cycles=memory,resources=monitor.result(),errors=errors,backend=app.platformName()))
    return int(bool(errors))
if __name__=='__main__':raise SystemExit(main())
