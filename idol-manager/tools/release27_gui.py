"""20-season GUI timings on an isolated save, measured separately from desktop QA."""
from pathlib import Path
from contextlib import closing
import json,os,sqlite3,sys,time,cProfile,pstats,faulthandler
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['IDOL_MANAGER_QA_REPORT_DIR']=str(ROOT/'reports/release27')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer,Qt
from idol_manager.service import GameService
from idol_manager.storage import UserPaths
from idol_manager.ui.main_window import MainWindow
from idol_manager.bgm import BgmManager
from tools.release_qa import Monitor

def main():
    out=ROOT/'reports/release27';paths=UserPaths(out/'gui20/user_data');paths.ensure()
    if not paths.save.exists():
        with closing(sqlite3.connect((ROOT/'diagnostics/followup_a/simulation.sqlite3').as_uri()+'?mode=ro',uri=True)) as a,closing(sqlite3.connect(paths.save)) as b:a.backup(b)
    (paths.config/'bgm_settings.json').write_text('{"enabled":false,"muted":true,"volume":0}',encoding='utf8')
    app=QApplication([]);errors=[];sys.excepthook=lambda k,e,t:errors.append(str(e));result={}
    trace=(out/'gui20_stack_live.txt').open('w',encoding='utf8');faulthandler.dump_traceback_later(30,repeat=True,file=trace)
    profile=cProfile.Profile();profile.enable()
    with Monitor() as monitor:
        t=time.perf_counter();service=GameService(ROOT/'diagnostics/followup_world',paths.save,storage=paths)
        bgm=BgmManager(service.root,paths.config/'bgm_settings.json',music_folder=paths.assets/'audio/bgm')
        w=MainWindow(service,bgm=bgm);w.resize(1280,720);w.show();result['service_and_window_seconds']=time.perf_counter()-t
        gaps=[];last=[time.perf_counter()];timer=QTimer(w)
        def heartbeat():
            now=time.perf_counter();gaps.append(now-last[0]);last[0]=now
        timer.timeout.connect(heartbeat);timer.start(10)
        def until(predicate,limit=90):
            end=time.monotonic()+limit
            while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.001)
            if not predicate():raise TimeoutError('GUI query deadline')
        t=time.perf_counter();w.show_records();page=w.records_page;app.processEvents();result['initial_frame_seconds']=time.perf_counter()-t
        until(lambda:page.rendered_generation==page.query_generation);result['league_ready_seconds']=time.perf_counter()-t
        model=[];original=page.fill
        def fill(*args,**kwargs):
            start=time.perf_counter();value=original(*args,**kwargs);model.append(time.perf_counter()-start);return value
        page.fill=fill;t=time.perf_counter();page.tabs.setCurrentIndex(1)
        until(lambda:page.player_table.rowCount()>0);result['first_player_rows_seconds']=time.perf_counter()-t;result['first_rows']=page.player_table.rowCount()
        until(lambda:page.rendered_generation==page.query_generation);result['all_players_seconds']=time.perf_counter()-t;result['all_rows']=page.player_table.rowCount()
        result['model_fill_seconds']=model
        queries=[];original_connect=service.database.connect
        def connect():
            c=original_connect();c.set_trace_callback(queries.append);return c
        service.database.connect=connect;t=time.perf_counter();page.search.setText('QA 가상 인물 00')
        until(lambda:page.rendered_generation==page.query_generation);page.player_table.sortItems(5,Qt.SortOrder.DescendingOrder)
        result['search_sort_seconds']=time.perf_counter()-t;result['search_sort_sql_count']=len(queries)
        result['heartbeat_max_gap_seconds']=max(gaps,default=0);result['qt_platform']=app.platformName();result['errors']=errors
        w.grab().save(str(out/'gui20/records.png'));timer.stop();w.close();app.processEvents()
    faulthandler.cancel_dump_traceback_later();trace.close();profile.disable()
    with (out/'gui20_profile.txt').open('w',encoding='utf8') as f:pstats.Stats(profile,stream=f).sort_stats('cumulative').print_stats(35)
    result['resources']=monitor.result();(out/'gui20_metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print({k:v for k,v in result.items() if k!='resources'})
if __name__=='__main__':main()
