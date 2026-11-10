"""Native Qt audio probe using a temporary save/settings; never writes the game DB."""
from contextlib import closing
from pathlib import Path
import json
import platform
import random
import sqlite3
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))


def main():
    from PySide6.QtCore import QTimer,qVersion
    from PySide6.QtWidgets import QApplication
    output=ROOT/'.test-artifacts/bgm_native_playback.json'
    output.parent.mkdir(exist_ok=True)
    report={'platform':platform.platform(),'python':sys.version.split()[0],'qt':qVersion(),
            'human_audible_verification':False,'game_db_modified':False}
    try:
        from PySide6.QtMultimedia import QMediaDevices,QAudioBufferOutput
    except ImportError as error:
        report.update(skipped=True,reason=str(error));output.write_text(json.dumps(report,indent=2),encoding='utf-8');return 0
    app=QApplication([])
    report['devices']=[d.description() for d in QMediaDevices.audioOutputs()]
    if not report['devices']:
        report.update(skipped=True,reason='No audio output device');output.write_text(json.dumps(report,indent=2),encoding='utf-8');return 0
    from idol_manager.bgm import BgmManager
    from idol_manager.service import GameService
    from idol_manager.ui.main_window import MainWindow
    with tempfile.TemporaryDirectory(prefix='idol_bgm_native_') as directory:
        folder=Path(directory);path=folder/'copy.sqlite3'
        with closing(sqlite3.connect((ROOT/'data/idol_manager.sqlite3').resolve().as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(path)) as dst:src.backup(dst)
        manager=BgmManager(ROOT,folder/'bgm_settings.json',parent=app,rng=random.Random(5))
        manager.set_volume(10);manager.set_muted(False);manager.set_enabled(True)
        service=GameService(ROOT,database_path=path)
        with closing(service.database.connect()) as c:original=list(c.iterdump())
        window=MainWindow(service,bgm=manager);window.show()
        state={'phase':'default','buffers':{'default':0,'battle':0},'tap':None,'started':time.monotonic()}
        report['phases']={}
        def received(buffer):
            if buffer.isValid() and buffer.byteCount()>0:state['buffers'][state['phase']]+=1
        def finish():
            timer.stop();window.close();app.quit()
        def poll():
            if time.monotonic()-state['started']>25:
                report.update(skipped=False,passed=False,error=manager.status);finish();return
            backend=manager.backend
            if backend is None:return
            if state['tap'] is None:
                state['tap']=QAudioBufferOutput(backend.player);backend.player.setAudioBufferOutput(state['tap'])
                state['tap'].audioBufferReceived.connect(received)
            phase=state['phase']
            if manager.category!=phase or backend.player.position()<900 or state['buffers'][phase]==0:return
            report['phases'][phase]={'track':str(manager.current_track.path),'title':manager.current_track.title,
                'position_ms':backend.player.position(),'has_audio':backend.player.hasAudio(),
                'playing':backend.player.playbackState()==backend.Media.PlaybackState.PlayingState,
                'decoded_buffers':state['buffers'][phase],'device':backend.output.device().description(),
                'volume':round(backend.output.volume(),3),'muted':backend.output.isMuted()}
            window.grab().save(str(ROOT/f'.test-artifacts/bgm_native_{phase}.png'))
            if phase=='default':state['phase']='battle';manager.set_context('battle')
            else:
                report.update(skipped=False,passed=all(v['playing'] and v['has_audio'] and not v['muted'] for v in report['phases'].values()))
                finish()
        timer=QTimer();timer.timeout.connect(poll);timer.start(50)
        app.exec();manager.shutdown()
        with closing(service.database.connect()) as c:report['copied_game_rows_unchanged']=original==list(c.iterdump())
        state['tap']=None
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))
    return 0 if report.get('passed') or report.get('skipped') else 1


if __name__=='__main__':raise SystemExit(main())
