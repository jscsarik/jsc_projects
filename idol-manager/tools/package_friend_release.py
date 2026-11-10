"""Package the verified EXE and media only; never includes live saves."""
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,sys,uuid,zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from idol_manager.catalog import scan_idols,SUPPORTED_EXTENSIONS
from idol_manager.bgm_catalog import scan_music

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def executable_version(path):
    import ctypes
    api=ctypes.windll.version
    size=api.GetFileVersionInfoSizeW(str(path),None)
    if not size:raise ValueError('EXE 버전 정보를 읽을 수 없습니다.')
    data=ctypes.create_string_buffer(size)
    if not api.GetFileVersionInfoW(str(path),0,size,data):raise ValueError('EXE 버전 조회 실패')
    address=ctypes.c_void_p();length=ctypes.c_uint()
    if not api.VerQueryValueW(data,'\\',ctypes.byref(address),ctypes.byref(length)):raise ValueError('EXE 버전 형식 오류')
    info=ctypes.cast(address,ctypes.POINTER(ctypes.c_uint32*13)).contents
    return f'{info[2]>>16}.{info[2]&65535}.{info[3]>>16}'

def remove_staging(staging):
    import stat
    staging=Path(staging).resolve();base=(ROOT/'build').resolve()
    if staging.parent!=base or not staging.name.startswith('friend_release_'):
        raise ValueError('Invalid release staging path')
    def retry_readonly(operation,path,error):
        target=Path(path)
        if not isinstance(error,PermissionError) or target.is_symlink() or not target.resolve().is_relative_to(staging):raise error
        if not (target.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY):raise error
        os.chmod(target,stat.S_IWRITE);operation(path)
    shutil.rmtree(staging,onexc=retry_readonly)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--build-dir',type=Path,default=ROOT/'dist/release_ai_trades/IDOL_Manager');args=parser.parse_args()
    version=re.search(r"setApplicationVersion\(['\"]([^'\"]+)", (ROOT/'idol_manager/app.py').read_text(encoding='utf-8')).group(1)
    source=args.build_dir.resolve()
    staging=ROOT/'build'/('friend_release_'+uuid.uuid4().hex);stage=staging/'IDOL_Manager'
    archive=ROOT/f'dist/IDOL_Manager-{version}-Windows-x64.zip'
    temporary=archive.with_name(archive.name+'.'+uuid.uuid4().hex+'.tmp')
    report=ROOT/'reports'/('friend_release_'+version.replace('.','_'));report.mkdir(exist_ok=True)
    if not (source/'IDOL_Manager.exe').is_file():raise ValueError('Build the release EXE first')
    if executable_version(source/'IDOL_Manager.exe')!=version:raise ValueError('소스와 EXE 버전이 다릅니다. 빌드한 뒤 배포하세요.')
    if not (source/'VERSION.txt').exists():(source/'VERSION.txt').write_text(version,encoding='utf-8')
    if (source/'VERSION.txt').read_text(encoding='utf-8-sig').strip()!=version:raise ValueError('Unexpected EXE version')
    forbidden={'.db','.sqlite','.sqlite3','.py','.pyc','.log'}
    for p in source.rglob('*'):
        if p.is_file() and (p.suffix.lower() in forbidden or p.is_symlink()):raise ValueError('Unexpected build file: '+str(p))
    shutil.copytree(source,stage)
    # PyInstaller COLLECT recreates the build folder. Reuse existing notices.
    notices=ROOT/'packaging/licenses'
    if (ROOT/'dist/release_special_sorting/IDOL_Manager/LICENSES').is_dir():
        shutil.copytree(ROOT/'dist/release_special_sorting/IDOL_Manager/LICENSES',stage/'LICENSES',dirs_exist_ok=True)
    elif notices.is_dir():shutil.copytree(notices,stage/'LICENSES',dirs_exist_ok=True)
    notice=ROOT/'dist/release_special_sorting/IDOL_Manager/THIRD_PARTY_NOTICES.txt'
    if notice.is_file():shutil.copy2(notice,stage/notice.name)
    media=[]
    for category in ('idols','agencies','title','audio'):
        allowed={'.mp3','.wav'} if category=='audio' else SUPPORTED_EXTENSIONS
        for p in sorted((ROOT/'assets'/category).rglob('*')):
            if not p.is_file() or p.suffix.lower() not in allowed:continue
            if p.is_symlink():raise ValueError('Linked media is not packaged')
            relative=p.relative_to(ROOT);target=stage/'_internal'/relative
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
            if digest(p)!=digest(target):raise ValueError('Media copy mismatch')
            media.append(dict(path=relative.as_posix(),sha256=digest(p)))
    (stage/'README_실행안내.txt').write_text(f'''IDOL Manager {version} · Windows x64 배포판

1. ZIP 파일을 폴더 전체로 압축 해제하세요.
2. IDOL_Manager 폴더 안의 IDOL_Manager.exe를 실행하세요.
3. 시작 화면의 새 게임에서 슬롯 1 또는 슬롯 2를 선택하세요.

Python을 별도로 설치할 필요가 없습니다.
압축 파일 안에서 바로 실행하지 마세요.
EXE만 옮기지 말고 _internal과 LICENSES 등 같은 폴더의 파일을 함께 유지하세요.
아이돌 사진, 기획사 로고, 타이틀 이미지, 일반/배틀/타이틀 음악이 포함되어 있습니다.
개인 세이브, 개발용 DB, 백업, 테스트 자료는 포함하지 않았습니다.

저장 데이터와 사용자 설정은 각 PC의 %LOCALAPPDATA%\\IDOL_Manager에 저장됩니다.
시작 화면은 불러오기 / 새 게임이며 저장 슬롯은 2칸입니다.
처음 실행하는 PC는 빈 슬롯에서 시작합니다.
이미 같은 게임을 사용한 PC라면 해당 PC의 기존 슬롯이 표시될 수 있습니다.
새 게임을 만들 때 사용 중인 슬롯을 선택하면 덮어쓰기 확인을 주의해서 읽으세요.

BGM은 게임 상단의 ♪ BGM에서 음소거·볼륨·재생을 조절할 수 있습니다.
사용자가 추가하는 사진·음악은 %LOCALAPPDATA%\\IDOL_Manager\\user_assets에 넣을 수 있습니다.
기존 저장 파일은 별도로 가져오기 기능을 사용할 때만 선택하세요.
''',encoding='utf-8-sig')
    files=[]
    for p in sorted(stage.rglob('*')):
        if not p.is_file():continue
        rel=p.relative_to(stage)
        if p.suffix.lower() in forbidden or any(x.lower() in ('saves','backups','reports','tests','diagnostics','cache','user_assets') for x in rel.parts):raise ValueError('Private payload: '+str(rel))
        files.append(dict(path=rel.as_posix(),bytes=p.stat().st_size,sha256=digest(p)))
    (stage/'SHA256SUMS.txt').write_text(''.join(f["sha256"]+'  '+f["path"]+'\n' for f in files),encoding='utf-8')
    with zipfile.ZipFile(temporary,'x') as z:
        for p in sorted(stage.rglob('*')):
            if p.is_file():
                compression=zipfile.ZIP_STORED if p.suffix.lower() in {'.jpg','.jpeg','.png','.webp','.mp3'} else zipfile.ZIP_DEFLATED
                z.write(p,'IDOL_Manager/'+p.relative_to(stage).as_posix(),compress_type=compression,compresslevel=6)
    with zipfile.ZipFile(temporary) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failure')
    os.replace(temporary,archive)
    from tools.publish_latest import publish_release
    published=publish_release(archive)
    summary=dict(version=version,archive=str(archive),bytes=archive.stat().st_size,sha256=digest(archive),
        images=scan_idols(stage/'_internal').image_count,people=len(scan_idols(stage/'_internal').people),
        bgm={k:len(v) for k,v in scan_music(stage/'_internal',extra_folder=report/'empty_music').items()},
        files=len(files)+1,crc='PASS',private_payload='NONE',published=published)
    (report/'manifest.json').write_text(json.dumps(dict(summary=summary,files=files,original_media=media),ensure_ascii=False,indent=2),encoding='utf-8')
    archive.with_suffix('.zip.sha256').write_text(summary['sha256']+'  '+archive.name+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))
    remove_staging(staging)

if __name__=='__main__':main()
