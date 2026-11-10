"""Atomically publish a complete local ZIP; Drive Desktop handles syncing."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,os,shutil,uuid,zipfile
ROOT=Path(__file__).resolve().parents[1]

def validate_archive(path):
    forbidden={'saves','backups','data','.venv','venv','__pycache__','cache','reports','tests','diagnostics','user_assets'}
    with zipfile.ZipFile(path) as z:
        names=set(z.namelist())
        required={'IDOL_Manager/IDOL_Manager.exe','IDOL_Manager/VERSION.txt',
                  'IDOL_Manager/_internal/config/generation.json','IDOL_Manager/_internal/config/season_schedule.json'}
        if not required<=names:raise ValueError('실행 파일·버전 또는 필수 설정이 없는 배포 ZIP입니다.')
        for name in names:
            parts=PurePosixPath(name.replace('\\','/')).parts
            if not parts or parts[0]!='IDOL_Manager' or '..' in parts or any(p.lower() in forbidden for p in parts):raise ValueError('배포 금지 경로: '+name)
            if name.lower().endswith(('.db','.sqlite','.sqlite3','.sqlite3-wal','.sqlite3-shm','.db-wal','.db-shm','.py','.pyc','.log')):raise ValueError('배포 금지 파일: '+name)
        if z.testzip() is not None:raise ValueError('ZIP 무결성 검사 실패')
        return z.read('IDOL_Manager/VERSION.txt').decode('utf-8-sig').strip()

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def publish(archive,directory=None):
    source=Path(archive).resolve();directory=Path(directory or ROOT/'releases').resolve()
    directory.mkdir(parents=True,exist_ok=True)
    target=directory/'IDOL_Manager_Latest.zip'
    if source==target:raise ValueError('원본 ZIP과 게시 대상이 같을 수 없습니다.')
    temporary=directory/f'.IDOL_Manager_Latest.{uuid.uuid4().hex}.tmp'
    try:
        shutil.copyfile(source,temporary)
        version=validate_archive(temporary)
        checksum=digest(temporary)
        if checksum!=digest(source):raise ValueError('ZIP 복사 해시 불일치')
        # Same-directory replacement: a failed copy/check never touches Latest.
        os.replace(temporary,target)
        return dict(path=str(target),version=version,sha256=checksum,bytes=target.stat().st_size)
    finally:temporary.unlink(missing_ok=True)

def publish_release(archive,*,root=ROOT):
    """Keep the local release and explicitly mirror it into Drive Desktop's mount."""
    root=Path(root)
    config=root/'packaging'/'publish_destination.json'
    destination=Path(json.loads(config.read_text(encoding='utf-8'))['google_drive_directory'])
    if not destination.is_absolute() or not destination.parent.is_dir():
        raise OSError('Google Drive 배포 폴더에 접근할 수 없습니다: '+str(destination.parent))
    local=publish(archive,root/'releases')
    drive=publish(local['path'],destination)
    if local['sha256']!=drive['sha256']:raise ValueError('Google Drive 배포 해시 불일치')
    return dict(**local,google_drive=drive)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('archive',type=Path);args=parser.parse_args()
    print(json.dumps(publish_release(args.archive),ensure_ascii=False))
