"""Temporarily deny writes to this task's new distribution; always restore ACL."""
from pathlib import Path
import hashlib,json,os,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
INSTALL=(ROOT/'dist/release_start_menu/IDOL_Manager').resolve()
OUT=ROOT/'reports/start_menu'


def files():
    return {str(p.relative_to(INSTALL)):hashlib.sha256(p.read_bytes()).hexdigest() for p in INSTALL.rglob('*') if p.is_file()}


def main():
    assert INSTALL.is_relative_to((ROOT/'dist/release_start_menu').resolve()) and INSTALL.name=='IDOL_Manager'
    before=files();identity=subprocess.run(['whoami','/user','/fo','csv','/nh'],capture_output=True,check=True).stdout
    sid=re.search(rb'S-1-\d+(?:-\d+)+',identity).group().decode()
    report={'install':str(INSTALL),'acl_restored':False}
    try:
        command=subprocess.run(['icacls',str(INSTALL),'/deny','*'+sid+':(OI)(CI)(WD,AD,WEA,WA,DC,DE)'],capture_output=True,check=True)
        probe=INSTALL/'start-menu-write-probe.tmp'
        try:
            with probe.open('xb') as f:f.write(b'QA only')
        except OSError as error:report['write_denied']=dict(errno=error.errno,winerror=error.winerror)
        else:probe.unlink();raise AssertionError('Write-denial probe unexpectedly succeeded')
        for create in (True,False):
            args=[sys.executable,str(ROOT/'tools/start_menu_qa.py'),'--tag','exe_readonly_final','--exe',str(INSTALL/'IDOL_Manager.exe')]
            if create:args+=['--create','--expect-empty']
            result=subprocess.run(args,cwd=ROOT,capture_output=True,timeout=180)
            if result.returncode:raise RuntimeError(result.stdout.decode(errors='replace')+result.stderr.decode(errors='replace'))
        report['create_and_reopen']='PASS';report['install_files_unchanged']=before==files()
        assert report['install_files_unchanged']
    finally:
        restore=subprocess.run(['icacls',str(INSTALL),'/remove:d','*'+sid],capture_output=True)
        report['acl_restored']=restore.returncode==0
        (OUT/'readonly_install.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        if restore.returncode:raise RuntimeError('QA install ACL restore failed: '+restore.stderr.decode(errors='replace'))
    print(json.dumps(report))


if __name__=='__main__':main()
