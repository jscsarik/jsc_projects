"""Run the actual onedir EXE on marked synthetic data, never the live save."""
from pathlib import Path
import json,os,subprocess,sys,time,wave,struct,math,argparse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from idol_manager.storage import UserPaths
from tests.test_annual_draft import png
OUT=ROOT/'reports/release27';EXE=ROOT/'dist/IDOL_Manager/IDOL_Manager.exe'

def run(exe,folder,create=False):
    paths=UserPaths(folder);paths.ensure();marker=paths.root/'release27-qa.json'
    options=json.loads(marker.read_text(encoding='utf8')) if marker.exists() else {}
    options.update(qa_only=True,create=create)
    marker.write_text(json.dumps(options),encoding='utf8')
    if create:
        for n in range(310):png(paths.assets/'idols'/f'QA 인물 {n:03}.png',n)
        with wave.open(str(paths.assets/'audio/bgm/default/QA 진단음.wav'),'wb') as f:
            f.setparams((1,2,8000,0,'NONE','not compressed'));f.writeframes(b''.join(struct.pack('<h',int(1000*math.sin(2*math.pi*440*n/8000))) for n in range(8000)))
        (paths.config/'bgm_settings.json').write_text('{"enabled":true,"muted":true,"volume":0}',encoding='utf8')
    env=dict(os.environ,IDOL_MANAGER_USER_DATA=str(paths.root.resolve()),QT_QPA_PLATFORM='windows',PATH=os.environ['SystemRoot']+'\\System32;'+os.environ['SystemRoot'])
    for name in ('PYTHONHOME','PYTHONPATH','VIRTUAL_ENV'):env.pop(name,None)
    started=time.perf_counter();p=subprocess.run([str(exe.resolve()),'--self-check'],cwd=exe.parent,env=env,timeout=180,capture_output=True)
    report=json.loads((paths.logs/'self-check.json').read_text(encoding='utf8')) if (paths.logs/'self-check.json').exists() else dict(success=False,error=p.stderr.decode(errors='replace'))
    report.update(exit_code=p.returncode,wall_seconds=time.perf_counter()-started,python_path_removed=True)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case',default='exe_final_한글 공백');args=parser.parse_args()
    if Path(args.case).name!=args.case:raise ValueError('Use a plain case name')
    folder=OUT/args.case/'user_data'
    if folder.exists() and (folder/'saves/idol_manager.sqlite3').exists():raise SystemExit('Refuse to recreate an existing QA save')
    first=run(EXE,folder,True);(OUT/'exe_fresh.json').write_text(json.dumps(first,ensure_ascii=False,indent=2),encoding='utf8');print(first)
    if not first['success']:raise SystemExit(2)
    second=run(EXE,folder);(OUT/'exe_reopen.json').write_text(json.dumps(second,ensure_ascii=False,indent=2),encoding='utf8');print(second)
    assert second['success'] and first['after']==second['after']
