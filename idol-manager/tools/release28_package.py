"""Build metadata and archive for 0.28.0; never overwrite the 0.27 ZIP."""
from pathlib import Path
import hashlib,json,shutil,zipfile
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/release28';DIST=ROOT/'dist/release28/IDOL_Manager'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for data in iter(lambda:f.read(1048576),b''):h.update(data)
    return h.hexdigest()
def main():
    if not (DIST/'IDOL_Manager.exe').exists():raise ValueError('Build 0.28 into dist/release28 first')
    shutil.copytree(ROOT/'dist/IDOL_Manager/LICENSES',DIST/'LICENSES',dirs_exist_ok=True)
    shutil.copyfile(ROOT/'dist/IDOL_Manager/THIRD_PARTY_NOTICES.txt',DIST/'THIRD_PARTY_NOTICES.txt')
    (DIST/'VERSION.txt').write_text('IDOL Manager 0.28.0\nWindows x64 / PyInstaller onedir / release candidate\n',encoding='utf8')
    (DIST/'README_실행안내.txt').write_text('''IDOL Manager 0.28.0 — 배포 후보

1. 실행: 압축을 풀고 IDOL_Manager.exe를 실행합니다.
   _internal과 DLL을 포함한 폴더 전체를 유지하세요.
   EXE 실행에는 별도 Python/.venv가 필요하지 않습니다.
   개발 장비 Windows x64에서 검증했으며 깨끗한 새 PC/VM은 미검증입니다.
   모든 Windows 10/11 장비의 호환성을 보장하는 안내가 아닙니다.

2. 사용자 파일: %LOCALAPPDATA%\\IDOL_Manager\\
   saves\\idol_manager.sqlite3: 게임 / saves\\backups: 마이그레이션 백업
   config: 사용자 설정 / cache: 썸네일 / logs\\idol_manager.log: 오류 로그
   user_assets\\idols: 사용자 사진(JPG/JPEG/PNG/WEBP)
   user_assets\\audio\\bgm\\default, battle: 사용자 음악(MP3/WAV)
   EXE 설치 폴더에 DB나 사용자 파일을 저장하지 않습니다.

3. 처음 시작: 사용자 폴더는 첫 실행에 만들어집니다.
   사진/음악이 없어도 창은 열리며 음악은 조용히 대기합니다.
   먼저 사진을 200명 이상 넣고 프로그램을 다시 열어 새 게임을 만드세요.
   파일명이 이름으로 인식됩니다. 같은 이름의 여러 포맷은 한 사람으로 처리됩니다.
   매년 새 인물 70명을 계속 공급하려면 미등장 사진이 더 필요합니다.
   직접 소유하거나 사용할 권한이 있는 파일을 사용하세요.

4. 기본 흐름: 새 게임 → 운영 기획사 선택 → 최초 드래프트 160턴
   → 1군 5명 선택/확정 → 1·2군 리더 지정 → 하루 진행 → 수요일 경기.
   후보의 추정 범위는 실제 CA/숨겨진 PA와 구분됩니다.
   출전자 선택 후 시작하고, 관전 또는 스킵으로 저장된 동일 결과를 확인합니다.
   5인 대결은 팀마다 윗줄 3명·아랫줄 가운데 2명을 모두 표시합니다.

5. 기존 게임 업그레이드:
   게임을 완전히 종료하고 기존 saves/config/user_assets를 별도 백업하세요.
   이 배포 폴더 내용(EXE, _internal 등)을 기존 설치 루트에 복사하세요.
   배포물에는 data/saves/assets가 없으므로 원본 DB·사진을 덮어쓸 필요가 없습니다.
   기존 루트 data 또는 saves의 단일 DB는 SQLite backup API로 검증·복사합니다.
   AppData의 저장 파일이 이미 있으면 그 게임을 우선 사용하며 덮어쓰지 않습니다.
   이전 DB가 여러 개면 임의로 선택하지 않습니다. 파일을 삭제하지 말고 경로를 확인하세요.
   dist 안의 EXE는 상위 프로젝트 DB까지 자동 탐색하지 않습니다.
   가져온 사진은 기존 assets 경로를 읽습니다. 다른 PC로 옮길 때 자산도 별도로 옮기세요.

6. 백업/복원:
   종료 후 saves 폴더 전체와 config/user_assets를 다른 위치에 복사하세요.
   실행 중 DB 파일 하나만 복사하지 마세요(WAL에 아직 기록이 있을 수 있습니다).
   복원 전 현재 파일도 별도 보관하고, 게임을 종료한 상태에서 복원하세요.
   자동 마이그레이션 백업은 정기적인 사용자 백업을 대신하지 않습니다.

7. 알려진 제한:
   20시즌 통산 전체 첫 조회는 약 10~14초 걸릴 수 있으며 로딩 중 다른 화면 사용이 가능합니다.
   첫 페이지를 먼저 표시하고 이후 전체 정렬을 갱신합니다. 화면 변경/종료 시 읽기 쿼리를 취소합니다.
   깨끗한 Python 미설치 PC/VM, 실제 OS DPI, 백신/SmartScreen은 아직 미검증입니다.
   실행 파일은 미서명입니다. Windows x64 개발 장비의 자동 Qt 검증과 물리 수동 검증을 구분합니다.
   경기/성장/부상/재정/계약 수치는 이번 버전에서 바꾸지 않았습니다.

8. 오류 제보: 버전 0.28.0, 실행 경로, 재현 순서와 logs\\idol_manager.log를 확인하세요.
   로그나 DB를 다른 사람에게 보낼 때 개인 경로/사진/저장 데이터 포함 여부를 먼저 확인하세요.
   배포물 파일 SHA256은 SHA256SUMS.txt에 있습니다.
''',encoding='utf8')
    files=[]
    for p in sorted(DIST.rglob('*')):
        if not p.is_file() or p.name=='SHA256SUMS.txt':continue
        name=p.relative_to(DIST).as_posix()
        if p.suffix.lower() in ('.sqlite3','.db','.mp3','.wav','.png','.jpg','.jpeg','.webp','.py') or any(n in p.parts for n in ('tests','reports','diagnostics','user_assets','__pycache__')):raise ValueError('Private/developer payload: '+name)
        files.append(dict(path=name,bytes=p.stat().st_size,sha256=sha(p)))
    (DIST/'SHA256SUMS.txt').write_text('\n'.join(r['sha256']+'  '+r['path'] for r in files)+'\n',encoding='utf8')
    (OUT/'final_manifest.json').write_text(json.dumps(dict(version='0.28.0',bytes=sum(r['bytes'] for r in files),files=files),ensure_ascii=False,indent=2),encoding='utf8')
    archive=ROOT/'dist/IDOL_Manager-0.28.0-Windows-x64.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(DIST.rglob('*')):
            if p.is_file():z.write(p,'IDOL_Manager/'+p.relative_to(DIST).as_posix())
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('Archive CRC failed')
    result=dict(version='0.28.0',archive=str(archive),sha256=sha(archive),bytes=archive.stat().st_size,files=len(files)+1,crc='PASS')
    (ROOT/'dist/IDOL_Manager-0.28.0-SHA256.txt').write_text(result['sha256']+'  '+archive.name+'\n',encoding='utf8')
    (OUT/'final_archive.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(result)
if __name__=='__main__':main()
