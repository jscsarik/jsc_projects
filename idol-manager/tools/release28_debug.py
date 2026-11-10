from pathlib import Path
import argparse,json,os,subprocess
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'reports/release28'
parser=argparse.ArgumentParser();parser.add_argument('--public',action='store_true');args=parser.parse_args()
profile=Path(r'C:\Users\Public\Documents\ESTsoft\CreatorTemp\IDOL_Manager28_한글 공백\신규 사용자\AppData\Local') if args.public else out/'debug_profile/AppData/Local'
user=profile/'IDOL_Manager';user.mkdir(parents=True,exist_ok=True)
(user/'release27-qa.json').write_text('{"qa_only":true,"expect_empty":true}',encoding='utf8')
install=out/'console_dist/IDOL_Manager_console'
env=dict(os.environ,LOCALAPPDATA=str(profile),PATH=os.environ['SystemRoot']+'\\System32;'+os.environ['SystemRoot'],QT_QPA_PLATFORM='windows')
for name in ('IDOL_MANAGER_USER_DATA','PYTHONHOME','PYTHONPATH','VIRTUAL_ENV','QT_PLUGIN_PATH','QML2_IMPORT_PATH'):env.pop(name,None)
suffix='_public' if args.public else ''
with (out/('console_stdout'+suffix+'.log')).open('wb') as stdout,(out/('console_stderr'+suffix+'.log')).open('wb') as stderr:
    p=subprocess.Popen([str(install/'IDOL_Manager_console.exe'),'--self-check'],cwd=install,env=env,stdout=stdout,stderr=stderr)
    try:code=p.wait(25)
    except subprocess.TimeoutExpired:p.kill();code=p.wait()
print(code)
