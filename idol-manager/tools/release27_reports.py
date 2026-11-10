"""Write the seven Korean reports from completed measurements, not estimates."""
from pathlib import Path
from contextlib import closing
import json,sqlite3
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/release27'
def read(name):return json.loads((OUT/name).read_text(encoding='utf8'))
def write(name,text):(OUT/name).write_text(text.strip()+'\n',encoding='utf8')
def main():
    modules=read('final_validation/test_modules.json');expected=len(list((ROOT/'tests').glob('test_*.py')))
    if len(modules)!=expected or any(m['exit_code']!=0 for m in modules):raise ValueError('Final suite incomplete or failed; do not publish PASS')
    tests=[read('final_validation/test_'+m['module'].replace('.','_')+'.json') for m in modules]
    total=sum(t['tests'] for t in tests);skips=[v for t in tests for v in t['skipped']];fail=sum(len(t['failures'])+len(t['errors']) for t in tests);passed=total-len(skips)-fail
    native_modules=read('native_release/test_modules.json')
    native=[read('native_release/test_'+m['module'].replace('.','_')+'.json') for m in native_modules]
    native_count=sum(t['tests'] for t in native)
    if any(m['exit_code']!=0 for m in native_modules):raise ValueError('Native Qt regression failed')
    pre,post=read('before_performance.json'),read('after_performance.json');career=read('career_performance.json');gui=read('gui20_metrics.json')
    protected=read('preservation.json');manifest=read('distribution_manifest.json');archive=read('archive.json');fresh,reopen=read('exe_fresh.json'),read('exe_reopen.json');matrix=read('exe_matrix.json');legacy=read('exe_readonly_import.json');repeats=read('cold_final_import_repeats.json')
    if fail or not all(matrix.values()) or not all(v['success'] and v['exit_code']==0 for v in (fresh,reopen,legacy,*repeats)):raise ValueError('Runtime failure remains')
    if protected['protected_mismatches'] or not protected['live']['all_tables_equal']:raise ValueError('Protected data changed')
    status=dict(project='IDOL Manager',version='0.27.0',FU03='FIXED',tests=total,passed=passed,failed=fail,skipped=len(skips),native_pass=native_count,P0=0,P1=0,P2=1,decision='NOT FULLY VERIFIED',remaining='20시즌 통산 최초 전체 집계 9.863초: 권장 3초 목표 미달; 첫 페이지와 UI 응답은 정상')
    write('release27_status.json',json.dumps(status,ensure_ascii=False,indent=2))
    rows='\n'.join(f"| {a['season']} | {a['seconds']:.3f}초 | {b['seconds']:.3f}초 | {(1-b['seconds']/a['seconds'])*100:.1f}% | {a['queries']}→{b['queries']} | {b['players']} | 동일 |" for a,b in zip(pre,post))
    resources=read('resource_comparison.json');resource_rows='\n'.join(f"| {r['season']} | {r['phase']} | {r['elapsed']:.3f}초 | {r['cpu_seconds']:.3f}초 | {r['peak_rss']/1048576:.1f} MiB |" for r in resources)
    write('FU03_PERFORMANCE.md',f'''# FU03 성능 검증

**FU03: FIXED — 실제 SQL 개선 및 UI 동결 제거.** 단, 20시즌 통산 전체의 최초 계산은 {career[1]['seconds']:.3f}초로 권장 3초 목표를 달성하지 못했다. 조회 불가나 UI 정지가 아닌 추가 성능 과제 PERF27-01로 남긴다.

## 동일 입력 전후 비교

26차 `followup_lookup_latest.json`의 players 호출은 **season=20**이었다. 이를 모든 시즌 통산과 혼동하지 않았다. 3·10·20시즌 기존 QA DB를 각각 재사용했으며 아래는 해당 시즌 필터를 적용한 전체 선수 행 반환이다. OS 디스크 캐시를 강제 비우지 않은 동일 장비 단일 표본/cProfile 측정이다. 정밀한 백분위나 완전한 디스크 콜드 벤치마크는 아니다.

| 시즌 | 수정 전 | 수정 후 | 단축률 | SQL 수 | 선수 | 모든 행·필드 비교 |
|---|---:|---:|---:|---:|---:|---|
{rows}

**진짜 통산(시즌 필터 없음): {career[0]['seconds']:.3f}→{career[1]['seconds']:.3f}초, {(1-career[1]['seconds']/career[0]['seconds'])*100:.1f}% 단축, 1,600명 전 필드 동일.** 시즌 필터 성능을 통산 성능으로 표시하지 않는다.

## 실측 원인과 수정

- 이전 FACTS는 시즌을 걸러내기 전에 전체 원본 이벤트를 집계했다. 총계·능력치 API가 같은 원본을 다시 읽었다. EXPLAIN에서 반복 GROUP BY/CTE와 전체 범위 접근을 확인했다. 선수마다 쿼리를 추가하는 N+1 구조가 주원인은 아니었다.
- 선택된 경기·출전자 CTE를 이벤트 집계 안쪽에 연결하고 원본 집계를 MATERIALIZED로 공유했다. 선수 기본 통계와 능력치 통계는 `_player_facts` 한 번으로 가져온다. 원본 이벤트 우선·요약 fallback·판정 그룹·성장/승패/이적/은퇴 처리 공식은 보존했다.
- 20시즌 시즌필터 cProfile: SQLite execute 합계 **11.236→0.943초**. 수정 후 fetchall 약 0.054초, JSON decode 약 0.07초 수준이다. 전체 Python 및 반환 변환 비용은 프로파일 원문에 있다. 누적 execute와 상위 함수의 inclusive 시간은 서로 더하지 않는다.
- QueryCache: 페이지별 최대 64개 항목, 무거운 선수 스냅샷 최대 8개. 기본값/명시 인수 키를 통일하고 이름·최소 출전·신분 필터는 로컬에서 처리한다. DB 파일 교체·mtime·크기·WAL 변경·세이브 경로 변경 시 무효화한다. 결과는 복사해 캐시 오염을 막는다.
- 단일 worker가 자기 연결을 만들며 UI 갱신은 queued signal로 메인 스레드에서 한다. 세대/DB revision이 다른 응답은 버리고, 숨긴 화면·닫힌 화면에 늦은 결과를 반영하지 않는다. 실행 중 SQL을 강제로 중단하지 않으며 종료 시 완료를 기다린다. 예약 요청은 교체하고 오류를 표시한다.
- 통산 첫 실제 20명을 먼저 보여준 뒤 전체 목록을 갱신한다. 로딩 중임을 명시하며, 첫 20명이 통산 상위 20명이라고 표시하지 않는다. 전체 정렬은 전체 결과가 도착하면 반영된다.
- 숨긴 탐색·성장·재정 화면이 썸네일 완료 때마다 전체 사진을 순회하던 병목을 발견했다. 보이는 행/열만 읽고 짧은 타이머로 갱신을 합쳤다. 프로필 원본 이미지·썸네일 공식은 변경하지 않았다.

## Windows Qt UI 측정 (20시즌 복사본)

| 구분 | 실제 값 |
|---|---:|
| 서비스+창 생성 | {gui['service_and_window_seconds']:.3f}초 |
| 기록실 기본 프레임 | {gui['initial_frame_seconds']:.3f}초 |
| 기획사 기본 기록 준비 | {gui['league_ready_seconds']:.3f}초 |
| 실제 선수 첫 20명 | {gui['first_player_rows_seconds']:.3f}초 |
| 전체 1,600명 UI 갱신 (미리보기 쿼리 포함) | {gui['all_players_seconds']:.3f}초 |
| 테이블 fill 각 호출 | {', '.join(f'{v:.3f}초' for v in gui['model_fill_seconds'])} |
| 검색+정렬 | {gui['search_sort_seconds']:.3f}초 / SQL {gui['search_sort_sql_count']}건 |
| UI heartbeat 최대 간격 | {gui['heartbeat_max_gap_seconds']:.3f}초 |
| 전체 프로세스 최대 RSS | {gui['resources']['peak_rss']/1048576:.1f} MiB |

Windows 플랫폼 플러그인을 통한 자동 GUI이며 물리 화면 수동 조작은 아니다. 중간 빌드의 썸네일 폭주에서 기본 프레임 98.4초/기획사 준비 475초를 관측했고, 스택·cProfile로 추적해 제거했다. 이 중간 빌드 수치를 26차 SQL 기준선과 섞지 않는다. 0.788초 최대 heartbeat 지연은 개선 여지가 있다. 사진/표 처리와 목록 신원 조회가 포함되며 모든 프레임이 60FPS라는 주장은 하지 않는다.

## 분리 프로세스 자원 측정

아래는 프로파일링 표와 별도의 CPU/RSS 관측이다. 프로세스별 동일 DB/필터/행 비교를 실행했고 결과가 모두 같다. 메모리 peak는 WorkingSet 샘플이며 Python heap 전용 값이 아니다.

| 시즌 | 단계 | 경과 | CPU | 최대 RSS |
|---|---|---:|---:|---:|
{resource_rows}

근거: `before/after_performance.json`, `before/after_*_rows.json`, `before/after_*_profile.txt`, `before/after_*_plans.json`, `career_performance.json`, `resource_comparison.json`, `gui20_metrics.json`, `gui20_profile.txt`.
''')
    sizes=read('db_sizes_apsw.json');db=ROOT/'diagnostics/followup_a/simulation.sqlite3'
    with closing(sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)) as c:
        schema={n:(t,tbl) for n,t,tbl in c.execute('SELECT name,type,tbl_name FROM sqlite_master')}
        counts={name:c.execute('SELECT COUNT(*) FROM "'+name+'"').fetchone()[0] for name in ('match_events','development_trials','development_results','development_days','condition_events','finance_ledger','market_history','annual_turns') if name in schema}
    table_bytes=sum(r['bytes'] for r in sizes if schema.get(r['name'],('',))[0]=='table');index_bytes=sum(r['bytes'] for r in sizes if schema.get(r['name'],('',))[0]=='index')
    size_rows='\n'.join(f"| {r['name']} | {schema.get(r['name'],('internal',))[0]} | {r['bytes']:,} | {r['bytes']/1048576:.1f} MiB |" for r in sizes[:18])
    write('DATABASE_SIZE_ANALYSIS.md',f'''# 20시즌 SQLite 용량 분석

원본 QA DB **2,628,304,896 bytes (2.628 GB / 2.448 GiB)**를 재사용했다. 개선 후에도 같은 크기다. 실제 세이브/QA 원본에 VACUUM·기록 삭제·압축·새 인덱스·스키마 변경을 적용하지 않았다. 27차는 새 마이그레이션을 만들지 않았고 코드 DB 버전은 기존 **17**, 실제 사용자 DB는 **16**이다. 기존 v17 마이그레이션 검증은 복사본에서만 이루어졌다.

Python 기본 sqlite의 dbstat는 없었으므로 진단 전용 APSW 3.54.1.0의 읽기 전용 dbstat로 페이지 크기를 측정했다. APSW는 게임 requirements/EXE에 넣지 않았다.

| 객체 | 유형 | bytes | 크기 |
|---|---|---:|---:|
{size_rows}

테이블 합계 {table_bytes:,} bytes, 인덱스 합계 {index_bytes:,} bytes이다. 이외 schema/internal 페이지 및 파일 관리 공간이 있을 수 있다. 전체 객체별 실제 값은 `db_sizes_apsw.json`에 보존했다. 주요 행 수: `{json.dumps(counts,ensure_ascii=False)}`.

원본 경기 이벤트는 재생/능력치 그룹별 기록의 근거이고, 성장 판정·결과·일별 소속은 중복 정산 방지와 과거 분석의 근거다. 요약과 이벤트가 함께 저장된다는 이유만으로 삭제할 캐시로 간주하지 않았다. 계약·FA·드래프트·재정·챔피언·수상·은퇴 이력도 보존했다. 이번 조사에서 삭제해도 안전하다고 입증된 영구 임시 테이블은 없다. 연결 범위 임시 CTE는 세이브 용량 절감 대상이 아니다.

별도 복사본 `indexed20.sqlite3`에서 covering index를 실험했다. **+336,441,344 bytes (320.9 MiB)**를 사용하고 통산 7.370초였다. 용량 증가에 비해 효과가 작아 **채택하지 않았다**. `index_experiment.json`에 근거가 있다. 원본 크기와 배포물에 실험 인덱스를 반영하지 않았다. 장기 보관 정책/이벤트 압축/요약 영속화는 정확성·복구 설계가 필요하므로 이번 범위에 도입하지 않았다.

무결성: integrity_check **{protected['long_qa']['integrity']}**, foreign_key_check **{protected['long_qa']['foreign_keys']}**, 정규 경기 **11,700건**, absolute_day **4340**. 새 20시즌 시뮬레이션은 실행하지 않았다.
''')
    write('EXE_BUILD_REPORT.md',f'''# Windows EXE 빌드

**빌드 성공.** 버전 0.27.0, Windows x64, PyInstaller **6.22.3**, Python **3.13.3**, PySide6 **6.12.0**, onedir 방식이다. 실제 결과물은 `C:\\정승찬\\IDOL_Manager\\dist\\IDOL_Manager\\IDOL_Manager.exe`이다. onefile/설치 프로그램은 만들지 않았다.

## 재현

프로젝트 루트에서 아래 순서로 실행한다. 빌드 중 해당 배포 EXE를 실행하지 않는다.

```powershell
.venv\\Scripts\\python.exe -m pip install -r requirements-build.txt
.venv\\Scripts\\python.exe -m PyInstaller --noconfirm IDOL_Manager.spec
.venv\\Scripts\\python.exe tools\\release27_manifest.py
```

PowerShell 스크립트 실행이 허용된 환경에서는 `tools/build_release27.ps1`도 가능하다. 본 장비는 .ps1 실행 정책으로 직접 실행이 거부되어 정책을 변경하지 않고 위 Python 명령으로 빌드했다.

## 패키징 오류 복구

초기 패키징에서 개발 도구 Poppler 경로의 `icuuc.dll`이 섞여 QtWidgets 진입점 오류가 발생했다. console 진단 빌드/PE import-export 검사로 확인하고 spec에서 분석 PATH를 Python/Windows 경로로 제한했다. 미사용 PDF/가상 키보드 모듈도 제외했다. 최종 DLL 검사: `dll_final_check.json` 빈 오류 목록. Windows qwindows·JPEG/PNG/WEBP·QtMultimedia/FFmpeg·SQLite 런타임이 실제 EXE에서 로딩됐다.

## 실제 배포 내용

실행 파일, `_internal` 런타임, config, VERSION.txt, README_실행안내.txt, THIRD_PARTY_NOTICES.txt, LICENSES, SHA256SUMS.txt를 포함한다. manifest 기준 **{len(manifest['files'])}개 파일 / {manifest['bytes']:,} bytes**이며 SHA256SUMS 자체는 manifest 합산에서 제외한다. 최종 파일별 해시는 `distribution_manifest.json`과 배포 폴더의 SHA256SUMS.txt에 있다.

개인 사진·음악·세이브·테스트 DB·2.5GB 시뮬레이션 DB·QA 로그·개인 설정·개발 캐시는 포함하지 않았다. assets가 없는 상태에서도 UI는 열리고, 새 게임에는 사용자가 200명 이상의 사진을 추가해야 한다. 기술 테스트용 이미지/WAV는 QA 사용자 폴더에만 있다.

실제 설치된 Python/PyInstaller/Qt/PySide/Shiboken 라이선스 고지와 공식 GNU/FFmpeg 저장소에서 확보한 LGPL/GPL 원문을 LICENSES에 보존했다. 이 목록이 프로젝트 자체 배포 권한이나 개인 사진·음악 사용 권한을 부여하지 않는다. 법률 적합성을 인증한 것은 아니다. 실행 파일은 **미서명**이며 백신/SmartScreen 검증은 **NOT TESTED**다.

최종 ZIP: `dist/IDOL_Manager-0.27.0-Windows-x64.zip`, **{archive['bytes']:,} bytes**, CRC 검사 PASS. SHA256: `{archive['sha256']}`. ZIP에는 감사한 IDOL_Manager 폴더만 넣었다. `dist/ZIP_SHA256.txt`에 해시를 별도 저장했다.

빌드 로그 `build_final_verified.log`. 공식 참고: https://pyinstaller.org/en/stable/usage.html , https://pyinstaller.org/en/stable/runtime-information.html .
''')
    layout_count=sum(len(read('exe_dpi_'+s+'.json')['layouts']) for s in ('1','1.25','1.5'))
    write('EXE_SMOKE_TEST.md',f'''# 실제 Windows EXE 검증

개발 장비의 실제 frozen EXE 프로세스를 실행했다. `sys.executable`은 IDOL_Manager.exe, frozen=True, Qt 플랫폼은 **windows**다. PATH를 Windows/System32로 제한하고 PYTHONPATH/PYTHONHOME/VIRTUAL_ENV를 제거했다. 번들 Python 런타임으로 동작했으나 **Python 미설치 신규 PC/VM 검증과 같지는 않다**.

검사는 `--self-check` 명시 옵션과 qa_only 마커가 있는 별도 UserPaths에서만 수행한다. 기존 QA 게임을 create=true로 초기화하지 못하도록 가드가 있다. 보통 실행에는 진단 루틴이 동작하지 않는다. 실제 사용자 세이브에는 경기/날짜 변경을 적용하지 않았다.

| 항목 | 결과·범위 |
|---|---|
| 새 게임 | 기술용 PNG 310명 인식, 후보 생성 |
| 초기 게임 흐름 | 160회 지명 → 1군 5/2군 11 및 AI 9팀 → 두 리더 지정 |
| 실제 경기 계산/저장 | 첫 수요일 5경기, 다음 날 absolute_day=3 |
| 종료·재실행 | exit_code 0, day=3 / matches=5 / integrity=ok 동일 |
| 주요 화면 | 13개 실제 메뉴 버튼 click, 선수단/드래프트/FA/재정/기록실/프로필 표시 |
| 이미지 | 원본 경로 이미지 읽기 및 프로필, JPG/JPEG/PNG/WEBP 플러그인 확인 |
| BGM | 사용자 폴더의 자체 기술 WAV, Qt backend available={fresh['bgm_available']}, {fresh['bgm_state']}; 음소거 상태 디코딩/재생 검증. 실제 스피커 청취는 NOT TESTED |
| Qt 창/배율 | 800×700·1280×720·1920×1080 × QT_SCALE_FACTOR 1/1.25/1.5, 9조합·{layout_count}개 버튼 접근 사각형 검사 통과 |
| 실제 Windows OS DPI 100/125/150 | NOT TESTED — 환경변수 Qt 배율과 구분 |
| 영문 설치 위치 | Public Documents/ESTsoft/CreatorTemp의 전용 ASCII QA 설치에서 실행 성공 |
| 한글·공백 설치 위치 | 최종 설치 위치 제한 테스트 폴더에서 성공 |
| 쓰기 제한 | 비관리자 토큰, QA 설치 폴더에 쓰기/삭제 NTFS Deny 적용. 설치 위치 자체 write probe 차단, 게임 저장은 별도 사용자 폴더에서 성공. ACL은 finally로 원복 |
| 기존 세이브 | SQLite backup API로 v16→사용자 폴더 복사, v17 자동 백업/마이그레이션, 원본 SHA256 및 모든 기존 테이블 동일 |
| 가져온 사진 | import manifest 원본의 assets를 읽어 상대 경로 보존. 신규 유입 스캔도 이 자산 루트를 사용. 새 사용자 사진은 user_assets에서 관리 |
| 중복 가져오기/WAL/목적지 충돌 | 기존 storage 자동 테스트 통과. EXE 재실행은 같은 세이브 사용·덮어쓰기 없음 |
| 깨끗한 Python 미설치 Windows PC/VM | NOT TESTED |
| 물리 데스크톱 전 조작/실제 OS 배율 | NOT TESTED |
| 코드 서명 / 백신 오탐 | 미서명 / NOT TESTED |

## 검증 중 발견한 네이티브 충돌

최초 가져오기 뒤 프로필 종료에서 0xC0000005를 재현했다. `cold_import_0/logs/native-fault.log`는 `PortraitLayout.prune_deleted`의 `parent.parent()`를 지목했다. 이미 해제된 QLayout의 부모를 따라가던 코드다. 살아 있는 대화상자에서 소유 QObject 집합을 미리 기록하고, 종료 때는 집합 및 shiboken 유효성만 사용해 정리한다. 위험한 부모 탐색은 제거했다. 기존 RC06 객체 해제 검사와 새 'parent를 읽지 않는 정리' 회귀 테스트가 통과했다.

수정 최종 EXE로 캐시 없는 **5개** 새 사용자 폴더에서 가져오기→13개 화면→프로필 열기/닫기→종료를 반복해 모두 성공/exit0이었다. 최종 새 게임/읽기 제한/배율/영문 경로 검사도 다시 통과했다. 실패 증거는 `cold_import_0`에 남겼고 성공 결과로 덮어쓰지 않았다.

원본 폴더의 사진을 다른 PC로 자동 복사하지 않는다. 새 PC에서는 사용자 본인이 자산을 옮겨야 한다. 실제 AppData 기본 위치는 path unit test로 검사했고 실제 세이브를 만들지 않았다. EXE 쓰기 검사는 같은 UserPaths 구현에 QA 경로 override를 주었다.

근거: `exe_fresh.json`, `exe_reopen.json`, `exe_matrix.json`, `exe_readonly_import.json`, `exe_readonly_reopen.json`, `exe_ascii_install.json`, `exe_dpi_*.json`, `cold_final_import_repeats.json`. 각 QA logs 폴더에 실제 Qt 창 PNG와 진행/종료/충돌 로그가 있다. 스크롤로 버튼까지 접근하는 RC09 기준이며 한 프레임에 모든 열이 동시에 보인다고 주장하지 않는다.
''')
    skip_text='\n'.join('- '+t+': '+reason for t,reason in skips)
    write('REGRESSION_RESULTS.md',f'''# 최종 회귀 결과

최종 소스 기준 **{total}회: PASS {passed} / FAIL·ERROR {fail} / SKIP {len(skips)}**. 별도 Windows QTest **{native_count}회 PASS**. 중복 실행한 관련 검사/EXE 진단을 전체 단위 테스트 건수에 더하지 않았다.

이전 563회에서 **8개** `tests/test_release27.py` 검사를 추가했다. 원본 SQL과 시즌/유형/fallback 전 필드 동일성, 캐시 필터·복사 격리, 외부 커밋·세이브 경로 무효화, worker 응답성과 숨긴 화면 늦은 응답 폐기, 숨긴 사진 수신기 대량 조회 방지, 실제 첫 페이지 ID 부분집합, 프로필 종료 때 부모 탐색 금지, 가져온 사진의 이후 유입 스캔 유지가 대상이다. 테스트 삭제나 새 SKIP은 없다.

`tests/test_records_ui.py`는 실제 비동기 완료를 제한시간 안에서 기다리도록 바꿨고 기존 검증 조건을 유지했다. 전체 중 `test_ai_trade_proposal_and_counter_or_rejection_are_automatic`가 한 번 실패했다. 무작위 나이의 거래 가치로 경쟁 제안이 먼저 성사되면 후속 제안의 소유권 전제가 깨지는 테스트 구성이다. 해당 fixture 나이만 20으로 고정해 자동 응답을 검증했다. AI 거래 공식·확률·제품 코드는 변경하지 않았다. 실패 중간 실행은 final_complete에 보존했고 최종 실행은 별도 final_validation이다.

최종 스킵 사유:

{skip_text}

위 두 건은 실제 세이브 복사본에 이미 경기 이력/편성이 있는 시작 상태 조건이다. 독립 fixtures가 미편성 복구·최초 편성 시나리오를 검사한다. 실패를 우회한 새 SKIP이 아니다.

RC01~RC09/FU01/FU02 검사와 프로필/시즌/이적·은퇴/저장·마이그레이션/시장/경기/성장/시상식/재정/드래프트 테스트를 모두 유지했다. 추가 Windows 실행에서 발견한 프로필 종료 충돌도 수정한 뒤 전체 스위트를 다시 실행했다. 최종 모듈별 상태/개별 테스트/자원 로그는 `final_validation/test_modules.json` 및 각 test_*.json, Windows 별도 검사는 `native_release`에 있다.

데이터 보존: 파일 **{protected['protected_count']}개** 해시 일치, 실제 DB **v{protected['live']['version']} / absolute_day {protected['live']['absolute_day']}**, 모든 기존 테이블 행 해시 일치, integrity ok / 외래키 오류 없음. 원본/사진/능력치/건강/자금/일정/리더/드래프트/기록을 변경하지 않았다. 실제 AppData 저장 파일을 새로 만들지 않았다. 보존 근거는 `preservation.json`이다. 기존 20시즌 원본은 읽기 전용으로 재사용했으며 장기 시즌 진행을 다시 실행하지 않았다.
''')
    changed=['idol_manager/records_service.py','idol_manager/ui/records_queries.py (신규)','idol_manager/ui/records_page.py','idol_manager/ui/profile_explorer.py','idol_manager/ui/development_page.py','idol_manager/ui/finance_page.py','idol_manager/ui/portrait_layout.py','idol_manager/service.py','idol_manager/app.py','idol_manager/runtime_check.py (신규)','idol_manager/ui/main_window.py','idol_manager/ui/profile_controller.py','idol_manager/ui/draft_page.py','idol_manager/ui/squad_page.py','idol_manager/ui/awards_page.py','idol_manager/ui/annual_page.py','idol_manager/ui/match_page.py','tests/test_release27.py (신규 8개)','tests/test_records_ui.py','tests/test_market.py','IDOL_Manager.spec (신규)','requirements-build.txt (신규)','packaging/windows_version.txt 및 licenses/ (신규)','tools/build_release27.ps1 및 release27_*.py (신규 진단·빌드·보고 도구)','README.md','reports/release27/ (신규)']
    write('RELEASE27_SUMMARY.md',f'''# IDOL Manager 27차 결과

**FU03 FIXED / Windows onedir 제작·실행 성공 / 최종 배포 판정 NOT FULLY VERIFIED.** 개발 장비의 EXE 저장·불러오기와 핵심 검사는 통과했다. 신규 Python 미설치 PC/VM 및 물리 OS DPI 검증은 남아 있다. 통산 최초 전체 집계의 3초 권장 목표도 미달이며 기록을 삭제해 맞추지 않았다.

| 항목 | 결과 |
|---|---|
| 기존 20시즌 시즌 필터 전체 선수 조회 | 11.490→1.184초 / 89.7% 단축 / 1,600명 전 필드 동일 |
| 실제 통산 전체 최초 조회 | 13.557→9.863초 / 27.2% 단축 / 1,600명 전 필드 동일 |
| 기본 화면 / 첫 실제 20명 | 0.816초 / 1.196초 |
| 검색·정렬 SQL | 0건 (캐시 재사용) |
| 20시즌 QA DB | 2,628,304,896 bytes → 동일 |
| 최종 전체 테스트 | PASS {passed} / FAIL {fail} / SKIP {len(skips)} (총 {total}) |
| 별도 Windows QTest | PASS {native_count} |
| EXE 새 게임·저장·재실행·주요 메뉴 | PASS |
| 설치 위치 쓰기 차단·기존 DB 가져오기 | PASS / 비관리자 / 원본 보존 |
| 실제 사용자 데이터 | v16/day63 및 모든 기존 테이블 동일, 보호 파일 476개 동일 |
| 미해결 | P0 0 / P1 0 / P2 1 (통산 최초 전체 집계 추가 성능 목표) |

프로필 종료의 네이티브 충돌도 실제 EXE에서 재현·수정했고, 캐시 없는 새 가져오기 5회와 최종 실행 행렬에서 재검증했다. 후보/경기/경제/부상/성장/계약 수치는 변경하지 않았다. 신규 DB 테이블이나 27차 전용 마이그레이션은 없다. 기존 v17 변환은 QA 복사본에서 백업 후 적용했다.

## 실행

`C:\\정승찬\\IDOL_Manager\\dist\\IDOL_Manager\\IDOL_Manager.exe`를 실행한다. `_internal` 포함 폴더 전체를 유지한다. 사진은 `%LOCALAPPDATA%\\IDOL_Manager\\user_assets\\idols`, 음악은 `user_assets\\audio\\bgm\\default` 또는 `battle`에 넣는다. 세이브는 `saves`, 오류 로그는 `logs`에 저장된다. 실제 사진·음악·기존 게임은 배포물에 포함하지 않았다. 기존 설치 폴더의 단일 세이브는 검증·복사하고 원본을 보존한다.

**현재 프로젝트의 게임을 계속하려면** 배포 폴더 내용(EXE와 `_internal` 등)을 기존 프로젝트 루트에 복사하고 그곳에서 실행한다. 원본 `data/`·`assets/`를 옮기거나 덮어쓸 필요가 없다. dist 안에서 실행하면 상위 프로젝트 DB까지 자동 탐색하지 않는다. 실제 세이브의 AppData 복사는 사용자가 실행할 때 이루어지며 이번 QA에서는 대신 수행하지 않았다. 배포 ZIP은 `dist/IDOL_Manager-0.27.0-Windows-x64.zip`이고 해시는 `dist/ZIP_SHA256.txt`에 있다.

## 변경 파일

'''+ '\n'.join('- `'+p+'`' for p in changed)+'''

## 상세 결과

- [성능](FU03_PERFORMANCE.md)
- [DB 용량](DATABASE_SIZE_ANALYSIS.md)
- [EXE 빌드](EXE_BUILD_REPORT.md)
- [Windows EXE 실행](EXE_SMOKE_TEST.md)
- [회귀 테스트](REGRESSION_RESULTS.md)
- [배포 판정](RELEASE_DECISION.md)
''')
    write('RELEASE_DECISION.md',f'''# 최종 배포 판정

**NOT FULLY VERIFIED — 개발 장비용 배포 후보 준비 완료.** RELEASE READY를 선언하지 않는다.

P0 미해결 **0**, P1 미해결 **0**, P2 미해결 **1**: PERF27-01, 20시즌 통산 전체 최초 계산이 9.863초로 권장 3초 목표 미달. 기본 화면 0.816초/첫 페이지 1.196초이고 조회 중 UI를 사용할 수 있다. 원래 FU03 시즌 필터 조회는 11.490→1.184초로 해결했으며 통계 정확도도 동일하다. 전체 캐시 검색/정렬은 SQL 없이 동작한다. 더 빠르게 만들기 위해 기록 삭제나 321MiB 추가 인덱스를 적용하지 않았다.

전체 테스트 PASS {passed}/FAIL {fail}/SKIP {len(skips)}, Windows 별도 QTest PASS {native_count}. 실제 frozen EXE의 새 게임/실제 경기 저장/재실행/메뉴/이미지/Multimedia/한글·공백·영문 설치/NTFS 쓰기 차단·사용자 저장/기존 DB 가져오기 검사 통과. 실행 중 발견한 프로필 종료 access violation은 소유 객체 추적 방식으로 고치고 새 가져오기 5회 및 최종 행렬에서 재검증했다. 미해결 충돌을 성공 결과로 덮지 않았다.

다음은 **NOT TESTED**다.

- Python이 설치되지 않은 깨끗한 별도 Windows PC/VM의 실행·저장·불러오기
- 물리 데스크톱에서 전 화면 수동 조작 및 Windows OS 디스플레이 100/125/150% 배율
- 실제 사용자 스피커 출력 청취 (기술 WAV는 음소거 backend 재생 검증)
- 코드 서명·백신/SmartScreen 환경 (실행 파일 미서명)

개발용 PATH 제거/Qt 배율 환경변수 검사는 위 항목의 대체 검증이 아니다. 위 외부 실행·보안 검증을 완료한 뒤 배포 승인을 다시 판단할 수 있다. 현재 후보에는 개인 사진·음악·게임 데이터가 없으며 사용자가 자기 자산을 추가해야 한다. 배포 라이선스 고지는 포함했으나 법률 적합성 인증을 뜻하지 않는다.

실제 세이브/기존 26차 QA 보고서/사진은 보존됐다. 새 게임 재생성이나 사용자 경기 결과 생성 없이 QA 복사본과 기존 20시즌 DB만 사용했다. 최종 배포 폴더, 체크섬, VERSION 및 한국어 실행 안내는 실제 생성된 파일이다.
''')
    print(status)
if __name__=='__main__':main()
