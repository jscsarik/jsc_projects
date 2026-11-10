"""Hold a normal packaged app open on disposable default-AppData paths."""
from pathlib import Path
import argparse,json,os,subprocess,time,sqlite3,shutil
from contextlib import closing
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/release28'
parser=argparse.ArgumentParser();parser.add_argument('--case',default='empty_default');parser.add_argument('--final',action='store_true');parser.add_argument('--copy-legacy',action='store_true');args=parser.parse_args()
case=json.loads((OUT/('final_extraction.json' if args.final else 'package_audit.json')).read_text(encoding='utf8'));install=Path(case['install'])
if Path(args.case).name!=args.case:raise ValueError('Plain case name only')
profile=(OUT/'frozen_profiles' if args.copy_legacy else install.parent)/(args.case+' 프로필')/'AppData/Local';profile.mkdir(parents=True,exist_ok=True);user=profile/'IDOL_Manager'
if args.copy_legacy:
    previous=OUT/'frozen_profiles/이전 저장 가져오기/AppData/Local/IDOL_Manager'
    target=user/'saves/idol_manager.sqlite3';target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():raise ValueError('Do not reset an existing physical QA save')
    with closing(sqlite3.connect((previous/'saves/idol_manager.sqlite3').as_uri()+'?mode=ro',uri=True)) as a,closing(sqlite3.connect(target)) as b:a.backup(b)
    (user/'config').mkdir(exist_ok=True)
    shutil.copyfile(previous/'config/legacy_import.json',user/'config/legacy_import.json')
    (user/'config/bgm_settings.json').write_text('{"enabled":false,"muted":true,"volume":0}',encoding='utf8')
env=dict(os.environ,LOCALAPPDATA=str(profile),QT_QPA_PLATFORM='windows',PATH=os.environ['SystemRoot']+'\\System32;'+os.environ['SystemRoot'])
for name in ('IDOL_MANAGER_USER_DATA','PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','QT_PLUGIN_PATH','QML2_IMPORT_PATH','QT_SCALE_FACTOR'):env.pop(name,None)
stdout=(OUT/(args.case+'_stdout.log')).open('ab');stderr=(OUT/(args.case+'_stderr.log')).open('ab')
process=subprocess.Popen([str(install/'IDOL_Manager.exe')],cwd=install,env=env,stdout=stdout,stderr=stderr)
(OUT/(args.case+'_process.json')).write_text(json.dumps(dict(pid=process.pid,install=str(install),user=str(user),normal_launch=True,default_path_via_localappdata=True,python_environment_removed=True,os_localappdata_base_precreated=True),ensure_ascii=False,indent=2),encoding='utf8')
while process.poll() is None:
    if (OUT/('stop-'+args.case)).exists():process.terminate();break
    time.sleep(.25)
code=process.wait();(OUT/(args.case+'_exit.json')).write_text(json.dumps(dict(exit_code=code,forced=(OUT/('stop-'+args.case)).exists())),encoding='utf8')
