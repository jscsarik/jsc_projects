"""Actual frozen-runtime path/DPI/import checks, only on marked QA copies."""
from pathlib import Path
from contextlib import closing
import ctypes,hashlib,json,os,re,shutil,sqlite3,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from release27_exe import run,EXE,OUT

def save(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')

def backup(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():raise ValueError('QA save already exists')
    with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)) as a,closing(sqlite3.connect(target)) as b:a.backup(b)

def tables(path):
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as c:
        return {name:hashlib.sha256(repr(sorted(c.execute('SELECT * FROM "'+name.replace('"','""')+'"').fetchall(),key=repr)).encode()).hexdigest()
                for name, in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}

def main():
    result={};source=OUT/'exe_final_verified/user_data/saves/idol_manager.sqlite3'
    for scale in ('1','1.25','1.5'):
        user=OUT/('dpi_'+scale)/'user_data'
        if not (user/'saves/idol_manager.sqlite3').exists():backup(source,user/'saves/idol_manager.sqlite3')
        elif not (user/'release27-qa.json').exists():raise ValueError('Unmarked existing data')
        os.environ['QT_SCALE_FACTOR']=scale
        value=run(EXE,user);save('exe_dpi_'+scale+'.json',value)
        result['qt_scale_'+scale]=value['success'] and value['exit_code']==0
    os.environ.pop('QT_SCALE_FACTOR',None)
    case=json.loads((OUT/'import_case.json').read_text(encoding='utf8'));install=Path(case['install']).resolve();user=OUT/'release_import_verified'
    user.mkdir(exist_ok=True)
    (user/'release27-qa.json').write_text('{"qa_only":true,"expect_readonly_install":true}',encoding='utf8')
    assert install.is_relative_to(OUT.resolve()) and install.name=='최종 설치 위치 제한 테스트'
    assert not any(p.is_symlink() or p.is_junction() for p in install.rglob('*'))
    shutil.copytree(EXE.parent,install,dirs_exist_ok=True)
    legacy=install/'data/idol_manager.sqlite3';before=tables(legacy)
    identity=subprocess.run(['whoami','/user','/fo','csv','/nh'],capture_output=True,check=True).stdout
    sid=re.search(rb'S-1-\d+(?:-\d+)+',identity).group().decode('ascii')
    # Granular file writes, excluding SYNCHRONIZE (generic W can also prevent
    # CreateProcess from opening an otherwise readable executable).
    acl=subprocess.run(['icacls',str(install),'/deny','*'+sid+':(OI)(CI)(WD,AD,WEA,WA,DC,DE)'],capture_output=True,check=True)
    try:
        value=run(install/'IDOL_Manager.exe',user)
        value['token_is_admin']=bool(ctypes.windll.shell32.IsUserAnAdmin())
        value['source_bytes_unchanged']=hashlib.sha256(legacy.read_bytes()).hexdigest()==case['legacy_sha256']
        after=tables(user/'saves/idol_manager.sqlite3')
        value['preserved_tables']={name:after.get(name)==digest for name,digest in before.items()}
        value['legacy_import_manifest']=(user/'config/legacy_import.json').exists()
        value['migration_backups']=[str(p.relative_to(user)) for p in (user/'saves').rglob('*') if p.is_file() and p.name!='idol_manager.sqlite3']
        save('exe_readonly_import.json',value)
        result['readonly_import']=value['success'] and value['exit_code']==0 and value['install_write_blocked'] and value['source_bytes_unchanged'] and all(value['preserved_tables'].values())
        reopen=run(install/'IDOL_Manager.exe',user);save('exe_readonly_reopen.json',reopen)
        result['readonly_reopen']=reopen['success'] and reopen['exit_code']==0 and value.get('after')==reopen.get('after')
    finally:
        subprocess.run(['icacls',str(install),'/remove:d','*'+sid],capture_output=True,check=True)
    # A separate plain ASCII installation, with an isolated saved game.
    english=Path(os.environ.get('PUBLIC',r'C:\Users\Public'))/'Documents/ESTsoft/CreatorTemp/IDOL_Manager27_ASCII_RC'
    assert english.resolve().parent==Path(r'C:\Users\Public\Documents\ESTsoft\CreatorTemp').resolve()
    if english.exists() and not (english/'VERSION.txt').is_file():raise ValueError('Unmarked ASCII test install')
    shutil.copytree(EXE.parent,english,dirs_exist_ok=True)
    user=OUT/'ascii_rc_user_data'
    if not (user/'saves/idol_manager.sqlite3').exists():backup(source,user/'saves/idol_manager.sqlite3')
    elif not (user/'release27-qa.json').is_file():raise ValueError('Unmarked ASCII user save')
    value=run(english/'IDOL_Manager.exe',user);save('exe_ascii_install.json',value);result['ascii_install']=value['success'] and value['exit_code']==0
    save('exe_matrix.json',result);print(result)
    if not all(result.values()):raise SystemExit(2)
if __name__=='__main__':main()
