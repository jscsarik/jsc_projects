"""Launch source/frozen Windows UI only against a marked disposable profile."""
from pathlib import Path
import argparse,json,os,struct,subprocess,sys,zlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def png(path,number):
    path.parent.mkdir(parents=True,exist_ok=True)
    def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    color=bytes((number%255,(number*17)%255,(number*31)%255))
    raw=b''.join(b'\0'+color*50 for _ in range(75))
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!IIBBBBB',50,75,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))


def main():
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path);p.add_argument('--tag',required=True)
    p.add_argument('--create',action='store_true');p.add_argument('--expect-empty',action='store_true');p.add_argument('--import-source',type=Path);p.add_argument('--replace',action='store_true')
    p.add_argument('--import-slot',type=int,choices=(1,2),default=1)
    args=p.parse_args()
    if Path(args.tag).name!=args.tag:raise ValueError('Plain QA tag required')
    out=ROOT/'reports/start_menu';profile=out/'profiles'/args.tag
    profile.mkdir(parents=True,exist_ok=True)
    if args.create:
        for n in range(310):png(profile/'user_assets/idols'/f'QA 전용 아이돌 {n:03}.png',n)
    options=dict(qa_only=True,create=args.create,expect_empty=args.expect_empty,replace=args.replace)
    if args.import_source:options['import_source']=str(args.import_source.resolve());options['import_slot']=args.import_slot
    (profile/'start-menu-qa.json').write_text(json.dumps(options),encoding='utf8')
    env=dict(os.environ,IDOL_MANAGER_USER_DATA=str(profile),QT_QPA_PLATFORM='windows')
    if args.exe:
        for key in ('PYTHONHOME','PYTHONPATH','VIRTUAL_ENV','QT_PLUGIN_PATH','QML2_IMPORT_PATH'):env.pop(key,None)
        system=os.environ.get('SystemRoot',r'C:\Windows')
        env['PATH']=system+'\\System32;'+system
        command=[str(args.exe.resolve()),'--self-check'];cwd=args.exe.parent
    else:command=[sys.executable,str(ROOT/'main.py'),'--self-check'];cwd=ROOT
    result=subprocess.run(command,cwd=cwd,env=env,capture_output=True,timeout=180)
    path=profile/'logs/start-menu-check.json'
    report=json.loads(path.read_text(encoding='utf8')) if path.exists() else {'success':False,'error':result.stderr.decode(errors='replace')}
    report['exit_code']=result.returncode
    (out/(args.tag+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    for name in ('title_empty.png','start_screen.png','slot_selection.png','active_game.png'):
        source=profile/'logs'/name
        if source.exists():
            import shutil
            shutil.copy2(source,out/(args.tag+'_'+name))
    print(json.dumps(dict(success=report.get('success'),exit_code=result.returncode,steps=report.get('steps'),error=report.get('error')),ensure_ascii=False))
    if not report.get('success') or result.returncode:raise SystemExit(1)


if __name__=='__main__':main()
