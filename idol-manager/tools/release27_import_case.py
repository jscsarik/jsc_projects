"""Prepare an install-location case without changing source saves/assets."""
from contextlib import closing
from pathlib import Path
import hashlib,json,shutil,sqlite3,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from idol_manager.storage import UserPaths,user_paths
out=ROOT/'reports/release27';install=out/'최종 설치 위치 제한 테스트';user=out/'final_import_user_data'
if install.exists():raise ValueError('Existing QA install is preserved; choose a new case folder')
assert install.resolve().is_relative_to(out.resolve())
shutil.copytree(ROOT/'dist/IDOL_Manager',install)
shutil.copytree(ROOT/'assets/idols',install/'assets/idols');shutil.copytree(ROOT/'assets/agencies',install/'assets/agencies')
(install/'data').mkdir()
source=ROOT/'data/idol_manager.sqlite3'
def ro(p):return sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
with closing(ro(source)) as a,closing(sqlite3.connect(install/'data/idol_manager.sqlite3')) as b:a.backup(b)
paths=UserPaths(user);paths.ensure();(paths.root/'release27-qa.json').write_text('{"qa_only":true,"create":false,"expect_readonly_install":true}',encoding='utf8')
(out/'import_case.json').write_text(json.dumps(dict(install=str(install),user=str(user),legacy_sha256=hashlib.sha256((install/'data/idol_manager.sqlite3').read_bytes()).hexdigest()),ensure_ascii=False,indent=2),encoding='utf8')
actual=user_paths().save
info=dict(default_user_save=str(actual),exists=actual.exists(),project_save=str(source))
if actual.exists():
    with closing(ro(actual)) as a,closing(sqlite3.connect(out/'appdata_before.sqlite3')) as b:
        a.backup(b);info['version']=a.execute('PRAGMA user_version').fetchone()[0];info['day']=a.execute('SELECT absolute_day FROM game_clock').fetchone()[0]
(out/'save_locations.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf8');print(info)
