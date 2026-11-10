"""Assemble this release without touching earlier distributions or user assets."""
from pathlib import Path
import hashlib,importlib.metadata as metadata,json,shutil,sys,zipfile
ROOT=Path(__file__).resolve().parents[1]
DIST=ROOT/'dist/release_start_menu/IDOL_Manager'
OUT=ROOT/'reports/start_menu'


def main():
    if not (DIST/'IDOL_Manager.exe').is_file():raise ValueError('Build the start-menu release first')
    licenses=DIST/'LICENSES';licenses.mkdir(exist_ok=True);packages=[]
    for name in ('pyside6_essentials','pyside6_addons','shiboken6','pyinstaller'):
        distribution=metadata.distribution(name);packages.append(dict(name=name,version=distribution.version))
        for item in distribution.files or []:
            if '/licenses/' in str(item).replace('\\','/'):
                source=Path(distribution.locate_file(item))
                if source.is_file():shutil.copyfile(source,licenses/(name+'_'+source.name))
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.is_file():shutil.copyfile(python_license,licenses/'PYTHON_LICENSE.txt')
    for source in (ROOT/'packaging/licenses').glob('*.txt'):shutil.copyfile(source,licenses/source.name)
    previous=ROOT/'dist/release28/IDOL_Manager/THIRD_PARTY_NOTICES.txt'
    if previous.is_file():shutil.copyfile(previous,DIST/'THIRD_PARTY_NOTICES.txt')
    (DIST/'VERSION.txt').write_text('IDOL Manager 0.29.0\nWindows x64 / onedir / DB 18 / two independent save slots\n',encoding='utf8')
    (DIST/'README_실행안내.txt').write_text(r"""IDOL Manager 0.29.0 · 시작 화면과 2슬롯 저장

폴더 전체를 풀고 IDOL_Manager.exe를 실행하세요. _internal과 DLL을 함께 유지합니다.
Python 설치 없이 실행하는 onedir 배포본입니다. 깨끗한 신규 PC/VM 검증은 별도입니다.

시작 화면: 이어하기 / 새 게임 / 세이브 선택 / 게임 종료.
새 게임: 슬롯을 선택합니다. 사용 중인 슬롯은 두 번 확인해야 교체됩니다.
기존 게임: 시작 화면 아래 이전 저장 파일을 선택하여 슬롯 1 또는 2로 가져옵니다.
여러 원본이 있으면 직접 하나를 선택하며 자동으로 이동·삭제하지 않습니다.
다른 이전 저장 파일 찾기 버튼으로 예전 data/idol_manager.sqlite3도 지정할 수 있습니다.
실행만으로 새 게임 생성·기존 DB 마이그레이션·날짜 진행을 수행하지 않습니다.

저장 위치: %LOCALAPPDATA%\IDOL_Manager\
  saves\slot1\game.sqlite3 · meta.json · thumbnail.png · config\
  saves\slot2\game.sqlite3 · meta.json · thumbnail.png · config\
  saves\slot_backups\slot1 또는 slot2: 교체·삭제 전 SQLite 백업
  saves\.archives: 교체·삭제 이전 슬롯 폴더(원본 보관)
  각 슬롯의 backups: 해당 슬롯만의 스키마 마이그레이션 백업
  config: 공통 BGM 설정·슬롯 활동 시각 / logs: 오류 로그
  user_assets\idols: 사용자가 추가하는 아이돌 사진
  user_assets\audio\bgm\default, battle: 사용자가 추가하는 MP3/WAV

원래 saves\idol_manager.sqlite3와 프로젝트 data의 단일 세이브는 그대로 보존합니다.
최근 플레이한 슬롯으로 이어합니다. 최근 플레이가 없으면 확인된 정상 저장 시각을 사용합니다.
손상된 최근 슬롯은 자동 초기화·삭제하거나 다른 슬롯으로 몰래 바꾸지 않습니다.
메타데이터와 썸네일은 캐시이며 정상 DB에서 다시 생성합니다.
게임 안의 '메인 메뉴로 돌아가기'에서 저장 확인 후 다른 슬롯을 선택할 수 있습니다.
저장 확인 실패 시 재시도 또는 취소로 현재 게임을 유지할 수 있습니다.

배포물에는 기존 세이브·아이돌 원본 사진·음악을 포함하지 않습니다.
새 게임에는 서로 다른 인물 사진 200명 이상이 필요합니다.
사진이 없으면 위 user_assets\idols 폴더에 사진을 넣고 다시 새 게임을 선택하세요.
매년 신규 인물 70명의 공급에는 추가 사진이 필요합니다.
이전 경로의 사진은 가져오기 출처를 이용해 찾으며, 사진이 없어도 게임은 열립니다.

창단 준비 7일·월요일 연습생 동시 신청 및 기존 계약·선수단·경기 규칙을 유지합니다.
DB 18로 올린 슬롯은 0.29.0에서 실행하세요. 이전 EXE/ZIP은 별도 보존되어 있습니다.
새 PC로 이동할 때 user_assets와 외부 원본 사진·음악도 함께 보관하세요.
""",encoding='utf8')
    files=[]
    for path in sorted(DIST.rglob('*')):
        if not path.is_file() or path.name=='SHA256SUMS.txt':continue
        name=path.relative_to(DIST).as_posix()
        if path.suffix.lower() in ('.sqlite3','.db','.mp3','.wav') or any(part in ('reports','tests','diagnostics','user_assets','idols') for part in path.relative_to(DIST).parts):raise ValueError('Private/QA payload: '+name)
        files.append(dict(path=name,bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (DIST/'SHA256SUMS.txt').write_text(''.join(f["sha256"]+'  '+f["path"]+'\n' for f in files),encoding='utf8')
    manifest=dict(version='0.29.0',files=files,packages=packages)
    (OUT/'distribution_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    archive=ROOT/'dist/IDOL_Manager-0.29.0-Windows-x64.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(DIST.rglob('*')):
            if path.is_file():z.write(path,Path('IDOL_Manager')/path.relative_to(DIST))
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    summary=dict(archive=str(archive),sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),bytes=archive.stat().st_size,files=len(files),zip_crc='PASS')
    (OUT/'archive.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(summary))


if __name__=='__main__':main()
