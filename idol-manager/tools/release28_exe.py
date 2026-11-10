"""Execute only ZIP-extracted binaries with disposable user/profile directories."""
from pathlib import Path
from contextlib import closing
import argparse,ctypes,hashlib,json,os,re,shutil,sqlite3,subprocess,sys,time,wave,zipfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tests.test_annual_draft import png
OUT=ROOT/'reports/release28';BASE=Path(r'C:\Users\Public\Documents\ESTsoft\CreatorTemp\IDOL_Manager28_한글 공백')
def save(name,v):(OUT/name).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
def extract(tag=''):
    info=json.loads((OUT/'final_archive.json').read_text(encoding='utf8'));archive=Path(info['archive'])
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==info['sha256']
    parent=BASE/('최종 배포 ZIP'+tag)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for n in z.namelist():
            p=parent/n
            assert p.resolve().is_relative_to(parent.resolve()) and not Path(n).is_absolute()
        if not parent.exists():z.extractall(parent)
    install=parent/'IDOL_Manager';files=[]
    for line in (install/'SHA256SUMS.txt').read_text(encoding='utf8').splitlines():
        digest,name=line.split('  ',1);assert hashlib.sha256((install/name).read_bytes()).hexdigest()==digest;files.append(name)
    save('final_extraction.json',dict(install=str(install),verified_files=len(files),sha256=info['sha256'],zip_crc='PASS'))
    return install
def run(install,profile,**options):
    # Windows creates AppData/Local as part of a user profile. Simulate that OS
    # base, then let the app create saves/config/cache/logs itself.
    profile.mkdir(parents=True,exist_ok=True);user=profile/'IDOL_Manager';user.mkdir(exist_ok=True)
    (user/'release27-qa.json').write_text(json.dumps(dict(qa_only=True,**options)),encoding='utf8')
    env=dict(os.environ,LOCALAPPDATA=str(profile),PATH=os.environ['SystemRoot']+'\\System32;'+os.environ['SystemRoot'],QT_QPA_PLATFORM='windows')
    for name in ('IDOL_MANAGER_USER_DATA','PYTHONHOME','PYTHONPATH','VIRTUAL_ENV','QT_PLUGIN_PATH','QML2_IMPORT_PATH'):env.pop(name,None)
    started=time.perf_counter();p=subprocess.run([str(install/'IDOL_Manager.exe'),'--self-check'],cwd=install,env=env,capture_output=True,timeout=180)
    report=user/'logs/self-check.json'
    result=json.loads(report.read_text(encoding='utf8')) if report.exists() else dict(success=False,error=p.stderr.decode(errors='replace'))
    result.update(exit_code=p.returncode,wall_seconds=time.perf_counter()-started,profile=str(profile),default_appdata=True)
    if not result.get('success') or p.returncode!=0:raise RuntimeError(json.dumps(result,ensure_ascii=False))
    return result
def snapshot(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():raise ValueError('Do not overwrite a QA save')
    with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)) as a,closing(sqlite3.connect(target)) as b:a.backup(b)
def tables(p):
    with closing(sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)) as c:
        return {n:hashlib.sha256(repr(sorted(c.execute('SELECT * FROM "'+n.replace('"','""')+'"').fetchall(),key=repr)).encode()).hexdigest() for n, in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
def preserved_rows(source,target):
    """Catalogs may append newly added photos; every old row must remain exact."""
    result={};added={}
    with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)) as a,closing(sqlite3.connect(target.resolve().as_uri()+'?mode=ro',uri=True)) as b:
        for name, in a.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            old=a.execute('SELECT * FROM "'+name+'"').fetchall();new=b.execute('SELECT * FROM "'+name+'"').fetchall()
            if name in ('people','annual_assets'):
                result[name]=set(old).issubset(set(new));added[name]=len(new)-len(old)
            else:result[name]=sorted(old,key=repr)==sorted(new,key=repr)
    return result,added
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--legacy-only',action='store_true');parser.add_argument('--tag',default='');args=parser.parse_args()
    if args.tag and Path(args.tag).name!=args.tag:raise ValueError('Plain QA tag only')
    install=extract(args.tag);profile=OUT/'frozen_profiles'/(args.tag+'신규 사용자')/'AppData/Local';user=profile/'IDOL_Manager'
    if not args.legacy_only:
        first=run(install,profile,expect_empty=True);save('exe_empty.json',first)
        assets=user/'user_assets'
        for i in range(310):png(assets/'idols'/f'QA 신규 인물 {i:03}.png',i)
        music=assets/'audio/bgm/default';music.mkdir(parents=True,exist_ok=True)
        with wave.open(str(music/'QA 재생 확인.wav'),'wb') as f:f.setparams((1,2,8000,0,'NONE','not compressed'));f.writeframes(b'\0\0'*8000)
        (user/'config/bgm_settings.json').write_text('{"enabled":true,"muted":true,"volume":0}',encoding='utf8')
        fresh=run(install,profile,create=True,scene_preview=True);save('exe_new_game.json',fresh)
        reopen=run(install,profile,scene_preview=True);save('exe_reopen.json',reopen)
    else:
        fresh=json.loads((OUT/'exe_new_game.json').read_text(encoding='utf8'));reopen=json.loads((OUT/'exe_reopen.json').read_text(encoding='utf8'))
    assert fresh['after']==reopen['after']
    values={}
    for scale in ('1','1.25','1.5'):
        os.environ['QT_SCALE_FACTOR']=scale
        value=json.loads((OUT/('exe_scale_'+scale+'.json')).read_text(encoding='utf8')) if args.legacy_only else run(install,profile,scene_preview=True)
        if not args.legacy_only:save('exe_scale_'+scale+'.json',value)
        values[scale]=all(v['accessible'] for v in value['layouts']) and all(v['visible'] and v['contained'] for v in value['scene_layouts'])
    os.environ.pop('QT_SCALE_FACTOR',None)
    # A legacy install contains a copy, never the actual save/assets.
    legacy=BASE/('기존 버전 업그레이드'+args.tag);shutil.copytree(install,legacy,dirs_exist_ok=True)
    shutil.copytree(ROOT/'assets',legacy/'assets',dirs_exist_ok=True)
    old=legacy/'data/idol_manager.sqlite3'
    if not old.exists():snapshot(OUT/'original_0.sqlite3',old)
    before=tables(old);old_hash=hashlib.sha256(old.read_bytes()).hexdigest()
    sid=re.search(rb'S-1-\d+(?:-\d+)+',subprocess.run(['whoami','/user','/fo','csv','/nh'],capture_output=True,check=True).stdout).group().decode()
    subprocess.run(['icacls',str(legacy),'/deny','*'+sid+':(OI)(CI)(WD,AD,WEA,WA,DC,DE)'],capture_output=True,check=True)
    try:
        profile=OUT/'frozen_profiles'/(args.tag+'이전 저장 가져오기')/'AppData/Local'
        # Verify the ACL outside the game. The old embedded QA probe accepts
        # only EACCES, while this host can report ENOENT for denied creation.
        # Normal game startup never writes such a probe in its install folder.
        probe=legacy/'release28-write-probe.tmp';denial=None
        try:
            with probe.open('xb') as f:f.write(b'QA')
        except OSError as error:
            if error.errno not in (1,2,13) or not legacy.is_dir() or not (legacy/'IDOL_Manager.exe').is_file():raise
            denial=repr(error)
        else:
            probe.unlink();raise ValueError('The install ACL did not block writes')
        imported=run(legacy,profile,scene_preview=True)
        imported['install_write_blocked']=True;imported['install_write_denial']=denial
        imported['source_unchanged']=hashlib.sha256(old.read_bytes()).hexdigest()==old_hash
        target=profile/'IDOL_Manager/saves/idol_manager.sqlite3'
        checks,added=preserved_rows(old,target);imported['preserved_existing_rows']=checks;imported['new_photo_catalog_rows']=added
        imported['all_existing_tables_preserved']=all(checks.values())
        imported['non_admin']=not bool(ctypes.windll.shell32.IsUserAnAdmin());save('exe_legacy_import.json',imported)
        assert imported['source_unchanged'] and imported['all_existing_tables_preserved'] and imported['install_write_blocked']
        again=run(legacy,profile);save('exe_legacy_reopen.json',again);assert imported['after']==again['after']
    finally:subprocess.run(['icacls',str(legacy),'/remove:d','*'+sid],capture_output=True,check=True)
    save('exe_acceptance.json',dict(empty=True,new_game=True,reopen=True,qt_scales=values,legacy_import=True,read_only_install=True,clean_windows='NOT TESTED',physical_gui='NOT TESTED'))
    print('ZIP-extracted frozen acceptance PASS')
if __name__=='__main__':main()
