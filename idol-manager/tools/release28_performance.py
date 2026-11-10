"""20-season GUI responsiveness/close probes; no season simulation."""
from pathlib import Path
from contextlib import closing
import argparse,json,os,sqlite3,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer,Qt
from PySide6.QtTest import QTest
from idol_manager.service import GameService
from idol_manager.storage import UserPaths
from idol_manager.ui.main_window import MainWindow
OUT=ROOT/'reports/release28'
def main():
    parser=argparse.ArgumentParser();parser.add_argument('phase');args=parser.parse_args()
    paths=UserPaths(OUT/'performance/user_data');paths.ensure()
    if not paths.save.exists():
        source=ROOT/'diagnostics/followup_a/simulation.sqlite3'
        with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)) as a,closing(sqlite3.connect(paths.save)) as b:a.backup(b)
    app=QApplication([]);errors=[];sys.excepthook=lambda k,e,t:errors.append(repr(e))
    service=GameService(ROOT/'diagnostics/followup_world',storage=paths);w=MainWindow(service);w.resize(1280,720);w.show()
    page=w.records_page;gaps=[];last=[time.perf_counter()];timer=QTimer(w)
    def beat():
        now=time.perf_counter();gaps.append(now-last[0]);last[0]=now
    timer.timeout.connect(beat);timer.start(10)
    def wait(predicate,seconds=60):
        end=time.monotonic()+seconds
        while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.002)
        if not predicate():raise TimeoutError('Performance probe deadline')
    metrics=dict(phase=args.phase,qt_platform=app.platformName())
    t=time.perf_counter();w.show_records();app.processEvents();metrics['basic_frame']=time.perf_counter()-t
    wait(lambda:page.rendered_generation==page.query_generation)
    page.kind.setCurrentIndex(page.kind.findData(None));page.tabs.setCurrentIndex(1)
    t=time.perf_counter();wait(lambda:page.player_table.rowCount()>0);metrics['first_rows_seconds']=time.perf_counter()-t;metrics['first_rows']=page.player_table.rowCount()
    metrics['loading_notice']=page.notice.text()
    # Actual unrelated UI input while SQLite runs.
    t=time.perf_counter();QTimer.singleShot(100,w.bgm_controls.menu.close);QTest.mouseClick(w.bgm_controls,Qt.MouseButton.LeftButton);app.processEvents();metrics['unrelated_control_seconds']=time.perf_counter()-t
    wait(lambda:page.rendered_generation==page.query_generation);metrics['full_query_and_ui_seconds']=time.perf_counter()-t;metrics['rows']=page.player_table.rowCount()
    w.grab().save(str(OUT/(args.phase+'_records.png')))
    t=time.perf_counter();w.show_finance();w.show_records();wait(lambda:page.rendered_generation==page.query_generation);metrics['cached_reentry_seconds']=time.perf_counter()-t
    page.api.values.clear();page.player_table.setRowCount(0);page.reload();wait(lambda:page.query_pool.activeThreadCount()>0);QTest.qWait(150)
    t=time.perf_counter();QTest.mouseClick(w.finance_menu,Qt.MouseButton.LeftButton);app.processEvents();metrics['switch_while_loading_seconds']=time.perf_counter()-t
    generation=page.query_generation;QTest.qWait(100);metrics['hidden_result_not_rendered']=page.rendered_generation!=generation
    wait(lambda:page.query_pool.activeThreadCount()==0)
    w.show_records();wait(lambda:page.rendered_generation==page.query_generation)
    page.api.values.clear();page.reload();wait(lambda:page.query_pool.activeThreadCount()>0);QTest.qWait(250)
    t=time.perf_counter();w.close();metrics['close_during_query_seconds']=time.perf_counter()-t
    timer.stop();app.processEvents();metrics['max_heartbeat_gap']=max(gaps,default=0);metrics['errors']=errors
    metrics['remaining_workers']=page.query_pool.activeThreadCount()
    with closing(service.database.connect()) as c:metrics['saved_regular_matches']=c.execute('SELECT COUNT(*) FROM match_results').fetchone()[0]
    (OUT/(args.phase+'_performance.json')).write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf8');print(metrics)
if __name__=='__main__':main()
