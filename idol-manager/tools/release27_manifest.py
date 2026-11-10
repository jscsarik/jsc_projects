"""Assemble user instructions/notices and audit the actual onedir payload."""
from pathlib import Path
import hashlib,importlib.metadata as metadata,json,shutil,sys
ROOT=Path(__file__).resolve().parents[1];DIST=ROOT/'dist/IDOL_Manager';OUT=ROOT/'reports/release27'
def main():
    if not (DIST/'IDOL_Manager.exe').exists():raise ValueError('Build first')
    licenses=DIST/'LICENSES';licenses.mkdir(exist_ok=True);packages=[]
    for name in ('pyside6_essentials','pyside6_addons','shiboken6','pyinstaller'):
        d=metadata.distribution(name);packages.append(dict(name=name,version=d.version,license=d.metadata.get('License-Expression') or d.metadata.get('License')))
        for p in d.files or []:
            if '/licenses/' in str(p).replace('\\','/'):
                source=Path(d.locate_file(p))
                if source.is_file():shutil.copyfile(source,licenses/(name+'_'+source.name))
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.exists():shutil.copyfile(python_license,licenses/'PYTHON_LICENSE.txt')
    (DIST/'VERSION.txt').write_text('IDOL Manager 0.27.0\nWindows x64 / PyInstaller onedir\n',encoding='utf8')
    (DIST/'README_실행안내.txt').write_text('''IDOL Manager 0.27.0 · Windows x64

이 폴더 전체를 원하는 위치에 풀고 IDOL_Manager.exe를 실행하세요.
_internal 폴더와 DLL을 함께 유지하세요. Python이나 가상 환경 설치는 필요하지 않습니다.
깨끗한 신규 PC/VM에서는 아직 검증하지 않았습니다. 검증 결과는 release27 보고서를 확인하세요.

기본 사용자 데이터: %LOCALAPPDATA%\\IDOL_Manager\\
  saves: 세이브 및 마이그레이션 백업 / config: 설정 / logs: 오류 로그 / cache: 썸네일
  user_assets\\idols: 사용자가 소유한 아이돌 사진
  user_assets\\audio\\bgm\\default 및 battle: 사용자 MP3/WAV

배포물에는 사용자 사진·음악·기존 세이브를 넣지 않았습니다.
새 게임의 최초 후보 200명을 위해 먼저 본인이 사용할 수 있는 서로 다른 사진을 200명 이상 넣고 재실행하세요.
사진/음악이 없어도 프로그램은 열립니다. 매년 신규 인물 70명 공급에는 추가 사진이 필요합니다.
기존 설치 폴더 data 또는 saves의 단일 세이브는 검증 후 사용자 폴더에 복사하며 원본을 유지합니다.
현재 소스 프로젝트의 게임을 계속하려면 이 배포 폴더의 내용(EXE, _internal 등)을
기존 IDOL_Manager 프로젝트 루트에 복사한 뒤 그곳의 EXE를 실행하세요.
배포물에는 data/saves/assets가 없으므로 원본 DB·사진 폴더를 덮어쓸 필요가 없습니다.
dist 안의 EXE만 바로 실행하면 프로젝트 상위 폴더의 DB까지 자동 탐색하지는 않습니다.
이미 사용자 폴더에 세이브가 있으면 그 파일을 사용하고 덮어쓰지 않습니다.
다른 PC로 옮길 때 사진·음악도 별도로 옮겨야 합니다. 기존 원본 경로의 파일을 자동 배포하지 않습니다.

서명되지 않은 실행 파일입니다. 백신/SmartScreen 오탐 여부는 검증하지 않았습니다.
기본 동작에는 관리자 권한이 필요하지 않습니다.
문의에 필요한 로그는 logs\\idol_manager.log에 있습니다.
''',encoding='utf8')
    (DIST/'THIRD_PARTY_NOTICES.txt').write_text(json.dumps(packages,ensure_ascii=False,indent=2)+'\n\nPython/Qt/PySide/Shiboken/PyInstaller 런타임을 포함합니다. 실제 설치된 라이선스 문서는 LICENSES에 보존했습니다.\nQt for Python: https://doc.qt.io/qtforpython-6/licenses.html\nQt third-party notices: https://doc.qt.io/qt-6/licenses-used-in-qt.html\nFFmpeg: https://ffmpeg.org/legal.html\nPyInstaller: https://pyinstaller.org/en/stable/license.html\n프로젝트 자체의 배포 라이선스나 사용자 자산의 권리를 이 문서에서 새로 부여하지 않습니다.\n',encoding='utf8')
    if (ROOT/'packaging/licenses').exists():
        for p in (ROOT/'packaging/licenses').glob('*.txt'):shutil.copyfile(p,licenses/p.name)
    files=[]
    for p in DIST.rglob('*'):
        if not p.is_file() or p.name=='SHA256SUMS.txt':continue
        relative=p.relative_to(DIST).as_posix()
        if p.suffix.lower() in ('.sqlite3','.db','.mp3','.wav') or any(x in p.parts for x in ('diagnostics','reports','tests','__pycache__','user_assets')):raise ValueError('Unexpected private/development payload: '+relative)
        files.append(dict(path=relative,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    (DIST/'SHA256SUMS.txt').write_text('\n'.join(p['sha256']+'  '+p['path'] for p in files)+'\n',encoding='utf8')
    (OUT/'distribution_manifest.json').write_text(json.dumps(dict(files=files,bytes=sum(p['bytes'] for p in files),packages=packages),ensure_ascii=False,indent=2),encoding='utf8')
    print(len(files),sum(p['bytes'] for p in files))
if __name__=='__main__':main()
