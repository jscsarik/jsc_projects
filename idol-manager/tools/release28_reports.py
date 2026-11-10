"""Publish measured release28 acceptance, keeping untested items explicit."""
from pathlib import Path
import json,platform,shutil
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/release28'
def read(n):return json.loads((OUT/n).read_text(encoding='utf8'))
def write(n,t):(OUT/n).write_text(t.strip()+'\n',encoding='utf8')
def suite(folder):
    modules=read(folder+'/test_modules.json')
    if any(m['exit_code']!=0 for m in modules):raise ValueError('Failed test module')
    results=[read(folder+'/test_'+m['module'].replace('.','_')+'.json') for m in modules]
    total=sum(r['tests'] for r in results);skips=[s for r in results for s in r['skipped']]
    if any(not r['success'] for r in results):raise ValueError('Test failures')
    return total,total-len(skips),skips,len(modules)
def main():
    total,passed,skips,modules=suite('final_tests_v2')
    if modules!=len(list((ROOT/'tests').glob('test_*.py'))):raise ValueError('Full suite still running')
    native,native_pass,ns,nmods=suite('windows_acceptance')
    old=read('package_audit.json');archive=read('final_archive.json');manifest=read('final_manifest.json');exe=read('exe_acceptance.json');new=read('exe_new_game.json');reopen=read('exe_reopen.json');legacy=read('exe_legacy_import.json');preserved=read('preservation.json');before=read('before_performance.json');after=read('after_performance.json');baseline=read('baseline.json')
    if not all(exe[k] for k in ('empty','new_game','reopen','legacy_import','read_only_install')) or not all(exe['qt_scales'].values()):raise ValueError('EXE acceptance incomplete')
    if not legacy['source_unchanged'] or not legacy['all_existing_tables_preserved']:raise ValueError('Legacy preservation failed')
    if preserved['changed_protected_files'] or not preserved['real_saves'][0]['identical']:raise ValueError('Protected original changed')
    delta=preserved['real_saves'][1] if len(preserved['real_saves'])>1 else None
    live_note=(f"실제 AppData 저장 파일은 시작 absolute_day {baseline['saves'][1]['day']}에서 {delta['day']}로 달라져 전체 행 동일성 판정은 **NOT COMPARABLE**로 남겼다. 작업 시작 때 별도 Python 게임 창이 실행 중이었다. QA는 기록된 별도 UserPaths/LOCALAPPDATA와 복사본만 사용했다. 변경 원인을 임의로 단정하거나 실제 진행을 되돌리지 않았다. 현재 integrity_check={delta['integrity']}, foreign_key_check={delta['foreign_keys']}이며 시작 시점 SQLite 스냅샷도 보존했다." if delta and not delta['identical'] else '실제 AppData 저장 파일도 시작 스냅샷과 동일하다.')
    status=dict(version='0.28.0',decision='CONDITIONAL RELEASE',P0=0,P1=0,P2=1,tests=total,PASS=passed,FAIL=0,SKIP=len(skips),windows_qtest=native_pass,clean_windows='NOT TESTED',physical_mouse_play='NOT TESTED',physical_keyboard_exit='PASS',physical_OS_DPI='NOT TESTED',archive=archive,live_save_comparison='NOT COMPARABLE' if delta and not delta['identical'] else 'IDENTICAL')
    write('release28_status.json',json.dumps(status,ensure_ascii=False,indent=2))
    write('CLEAN_INSTALL_TEST.md',f'''# 클린 설치 및 기본 경로 검증

**깨끗한 Python 미설치 Windows PC/VM: NOT TESTED.** 접근 가능한 별도 PC/VM이 없어 환경을 갖췄다고 가정하지 않았다. 프로젝트 소스가 없는 장비에서의 독립 실행을 최종 입증한 것은 아니다.

실제 장비: `{baseline['environment']['windows']}` / Windows x64. 빌드용 Python 3.13.3/PySide6 6.12.0이 있는 개발 장비다. 배포 EXE에는 Python DLL이 포함돼 별도 Python 설치 없이 실행하도록 제작됐지만, 새 PC 호환성은 별도 확인해야 한다.

기존 ZIP을 보존해 검사하고, 수정본 ZIP만 Public Documents/ESTsoft/CreatorTemp의 한글·공백 설치 경로에 해제했다. EXE 실행 PATH는 Windows/System32만 남기고 PYTHONHOME/PYTHONPATH/VIRTUAL_ENV/Qt 개발 플러그인 경로를 제거했다. frozen=True, executable=추출된 EXE, resource_root=설치의 _internal을 확인했다. 사용자 데이터는 원본 AppData와 분리한 QA용 LOCALAPPDATA 기본 경로로 만들었다. IDOL_MANAGER_USER_DATA 강제 경로는 사용하지 않았다.

실제 수행:

1. ZIP CRC 및 SHA256/내부 파일 해시 확인
2. 빈 사진·음악·게임 상태에서 앱 실행, saves/config/logs/cache/user_assets 생성 및 주요 메뉴 표시
3. 사용자 사진 폴더에 서로 다른 기술 PNG 310개와 자체 무음 WAV 추가
4. 재실행해 새 게임 생성 → 초기 드래프트 160회 → 양 선수단 편성/리더 → 수요일 5경기 저장 → 목요일
5. 정상 종료 후 재실행하여 day=3 / match_results=5 / integrity=ok 유지
6. 사용자 설정, 이미지·BGM 및 5인 배치를 실제 frozen Qt 창에서 확인

위 4번의 진행은 EXE 안의 opt-in 진단 루틴이 실제 서비스 API를 호출한 통합 검증이다. 전 과정을 물리 마우스로 플레이했다는 의미는 아니다. 소스 Windows QTest 버튼 조작 검사는 별도로 수행했다.

최초 외부 QA 경로 실행에는 호스트 샌드박스의 폴더 생성 제한으로 FileNotFoundError/대기 오류가 있었다. console 진단본과 같은 파일/같은 경로의 허용된 실행으로 제품 오류와 분리했다. 최종 저장 경로는 명시적으로 허용된 QA 폴더에 두었다. 실제 OS 사용자 프로필처럼 AppData/Local 기반 폴더를 준비한 뒤 앱 하위 디렉터리 생성을 확인했다. 이 제한을 숨기거나 새 PC 성공으로 바꾸지 않았다.

기존 세이브 복사본(v16→17) 업그레이드도 검증했다. 원본 SHA256 동일, 모든 기존 행 보존. 현재 assets에 DB 등록 당시보다 사진 62개가 더 있어 people/annual_assets에 각각 62개가 추가됐다. 이것은 사진 자동 인식의 정상 동작이며 기존 CA/PA/자금/드래프트/결과를 재생성하지 않았다. 카탈로그 외 테이블은 전체 일치를 요구했다.

증거: package_audit.json, final_extraction.json, exe_empty.json, exe_new_game.json, exe_reopen.json, exe_legacy_import.json, exe_legacy_reopen.json. 원본 27차 ZIP은 변경하지 않았다.
''')
    write('WINDOWS_GUI_ACCEPTANCE.md',f'''# Windows GUI 승인 검사

## 검증 방식 구분

- 실제 frozen EXE/Windows Qt: 추출한 0.28.0 실행 파일로 새 게임·저장·불러오기·13개 메뉴·프로필·이미지·BGM·선수단·5인 장면을 확인했다. 진단의 경기/드래프트 진행은 실제 서비스 API, 메뉴 전환은 Qt 버튼 클릭이다.
- 소스 Windows QTest: **{native}회 / PASS {native_pass} / FAIL 0 / SKIP {len(ns)}**. 초기 드래프트 플레이어 확인/AI 160턴, 1군 5명·2군 11명/리더/교체, 시장 입찰·트레이드 확인, 재정/프로필/기록/날짜·성장 화면을 기존 임시 DB에서 버튼·키 이벤트로 검사했다. `windows_acceptance/` 8개 모듈의 상세 로그를 보존했다. 전체 단위 테스트와 합산하지 않았다.
- 별도 경기/포스트시즌/특별전 UI 및 전원 표시·저장 동일성 관련 검사는 scene_related, bounds_v2와 최종 전체 스위트에 있다. 스킵은 저장된 결과와 같고 중복 계산하지 않는다.
- 실제 데스크톱: 원본과 다른 EXE 경로·QA 저장 폴더의 창을 컴퓨터 사용 도구로 선택했다. 접근성 트리는 읽었지만 캡처가 `FrameArrived timed out`/`window capture timed out`, 클릭이 `coordinate input geometry is unavailable`로 실패했다. 마우스 플레이 완료는 **NOT TESTED**다. 키보드 Alt+F4 뒤 QA 프로세스가 exit0/forced=false로 종료된 것은 확인했다. 이 한 건을 전체 수동 플레이 성공으로 확대하지 않는다.

## 5인 대결 요청 반영

각 팀 실제 출전자가 5명이면 **윗줄 3명·아랫줄 가운데 2명**이다. 한 명씩 바꾸는 드롭다운을 없애고 10명을 동시에 표시한다. 판정 이벤트는 해당 카드만 강조하며 다른 카드를 숨기지 않는다. 사진 비율과 프로필 클릭·주요/일반 능력치 성공 기록은 유지했다. 작은 두 줄 배치에서는 리더는 이름의 ★, 개인 합계/추가 판정은 툴팁으로 간결하게 표현한다. 경기 점수·판정·저장 규칙은 바꾸지 않았다.

초기 배치에서 상위 DockWorkspace가 옛 최소 높이를 유지해 아랫줄을 자르는 문제를 추가 재현했다. 사진 라벨의 이전 pixmap이 최소 높이를 고정하지 않도록 하고, 다인 카드 밀도를 조절했으며 BattleView 최소 크기 힌트를 도크 할당 공간에 맞췄다. 테스트는 카드 내부뿐 아니라 **모든 상위 패널과 메인 창** 안에 있는지도 검사한다. 실패 중간 로그 full_scene_bounds와 최종 성공 bounds_v2를 구분했다.

## 창 크기 / 배율

800×700·1280×720·1920×1080 × QT_SCALE_FACTOR 1/1.25/1.5의 **9조합**에서 선수단 편성·리더·페이지 버튼 접근과 양 팀 10명 전원 표시를 검사했다. 최종 EXE의 scene_layouts는 조상 위젯까지 사각형 포함을 검증했다. 이미지가 없거나 손상되어도 대체 표시와 경기 재생은 정상이다.

실제 Windows OS 배율 100/125/150 변경 검사는 **NOT TESTED**. Qt 환경변수 배율은 그 대체가 아니다. Source Windows QTest와 frozen EXE 렌더링을 물리 수동 검증과 혼동하지 않는다. BGM은 자체 무음 WAV의 backend available/PlayingState 확인이며 실제 스피커 청취는 미검증이다.

증거: exe_scale_*.json, exe_legacy_import.json, 실제 QA user_root/logs/five_players_*.png, physical_acceptance_process.json / physical_acceptance_exit.json. 5인 그림은 명시적인 QA 배치 미리보기이며 경기·결과를 생성하지 않는다.
''')
    write('FINAL_PERFORMANCE.md',f'''# 최종 기록실 체감 성능

20시즌 기존 DB를 복사해 사용했다. 정규 11,700경기를 다시 시뮬레이션하지 않았고 기록을 삭제하지 않았다. 순수 SQL 집계식은 27차와 동일하다. 새로운 변경은 UI worker의 읽기 전용 조회 취소다.

| 지표 | 측정 |
|---|---:|
| 기본 프레임 | {after['basic_frame']:.3f}초 |
| 첫 실제 20명 | {after['first_rows_seconds']:.3f}초 |
| 첫 20명 이후 전체 1,600명 완료 | {after['full_query_and_ui_seconds']:.3f}초 |
| 통산 탭 진입부터 전체 표시 (위 두 구간 합) | {after['first_rows_seconds']+after['full_query_and_ui_seconds']:.3f}초 |
| 조회 중 BGM 입력 호출 반환 | {after['unrelated_control_seconds']:.3f}초 |
| 재정 페이지 방문+기록실 복귀 합계 | {after['cached_reentry_seconds']:.3f}초 |
| 재정으로 전환/자체 데이터 표시 | {after['switch_while_loading_seconds']:.3f}초 |
| 조회 중 종료 수정 전 | {before['close_during_query_seconds']:.3f}초 |
| 조회 중 종료 수정 후 | {after['close_during_query_seconds']:.3f}초 |
| 종료 후 남은 worker | {after['remaining_workers']} |

27차 9.863초는 서비스의 순수 통산 조회다. 이번 표는 전체 유형/미리보기/표 렌더링을 포함한 GUI 흐름이며 그 수치를 순수 SQL과 직접 비교하지 않는다. 재진입 합계에는 재정 화면 로딩 약 2초가 포함되어 기록실 캐시 자체 시간이 아니다. 전체 heartbeat 최대 {after['max_heartbeat_gap']:.3f}초 역시 이 재정 로딩을 포함한다. 모든 화면이 무지연이라고 주장하지 않는다.

초기 20명과 '전체 선수 집계 중' 안내를 표시하고, worker가 SQLite 조회를 처리하는 동안 입력을 받을 수 있었다. 숨긴 화면의 이전 결과를 반영하지 않았고 재진입은 revision-aware 캐시를 사용한다. 오류는 사용자에게 표시하며 실제 오류를 무조건 성공 처리하지 않는다.

## 수정한 종료 대기

기존 closeEvent는 query_pool.waitForDone()으로 실제 SQL 종료를 기다려 약 14초 멈췄다. records_read.cancellation_scope와 SQLite progress handler로 **해당 worker의 기록 조회만** 취소한다. 재요청·화면 숨김·종료 때 취소 Event를 설정하고, 읽기 트랜잭션/연결을 정리한다. ContextVar는 finally로 복원해 다른 스레드나 게임 쓰기 트랜잭션에 적용되지 않는다. 중단된 결과를 캐시에 넣지 않고 진짜 SQL 오류와 구분한다.

잠재력·경기·성장·경제 수치와 집계 SQL은 변경하지 않았다. 기록 동일성/캐시 무효화/스레드/취소 전후 DB 보존 회귀 검사 통과. 현재 P2 PERF27-01은 통산 최초 전체 집계의 추가 성능 과제이며 기본 화면 사용을 막는 무응답은 아니다. 근거: before_performance.json, after_performance.json, related 및 최종 tests.test_release28 결과.
''')
    write('RELEASE_PACKAGE_AUDIT.md',f'''# 배포 패키지 감사

기존 27차 ZIP: `{old['archive']}`

SHA256 `{old['sha256']}` — 시작/종료 해시 동일. 원본 ZIP/보고서를 보존했다. 압축 CRC/내부 체크섬 {old['verified_files']}개/필수 EXE·python313.dll·qwindows.dll 확인 후 별도 위치에 해제했다.

최종 28차 ZIP: `{archive['archive']}`

버전 **0.28.0 배포 후보**, {archive['bytes']:,} bytes / {archive['files']}개 파일. SHA256:

`{archive['sha256']}`

최종 해제 후 CRC와 내부 파일별 SHA256을 다시 검사했다. EXE와 _internal 전체를 함께 배포한다. config 2개, Qt/SQLite/Multimedia/이미지 포맷 런타임, 버전/한국어 실행 안내/라이선스/해시가 있다. 개인 사진·음악·세이브·QA DB·시뮬레이션·로그·개발용 Python 소스·__pycache__는 없다. 최종 manifest의 파일 바이트 합계는 {manifest['bytes']:,}이며 SHA256SUMS 자체는 제외한다.

코드 서명은 없으며 백신/SmartScreen 검사는 NOT TESTED다. 라이선스 고지를 보존했지만 프로젝트 배포 권한·개인 자산 권리를 새로 부여하거나 법률 적합성을 인증한 것은 아니다. 필요한 사진·음악은 사용자가 추가한다.

빌드: 기존 IDOL_Manager.spec 및 PyInstaller 6.22.3 사용, `--distpath dist/release28 --workpath build/release28`. 기존 Poppler ICU 혼입 방지 PATH 제한과 미사용 DLL 제외를 유지했다. 오류 진단용 console_dist는 reports/release28에만 있고 최종 ZIP에 포함하지 않았다. 빌드 로그 build_final.log, 파일 목록 final_manifest.json, 해시 final_archive.json 및 dist/IDOL_Manager-0.28.0-SHA256.txt 참조.

## 데이터 보호

원본 프로젝트 DB v16/day63: 모든 행 동일 / 무결성 ok. 사진·설정·기존 보고서·27차 ZIP 등 보호 파일 **{preserved['protected_files']}개**의 해시 동일. 기존 세이브 복사본의 모든 기존 행을 보존했고 새 사진 62개의 카탈로그 추가만 별도 검사했다. 원본 삭제·초기화·VACUUM·경기 결과 생성은 하지 않았다. 28차 DB 스키마/테이블/마이그레이션 추가 없음(기존 v17 유지).

{live_note}

근거: baseline.json, preservation.json, exe_legacy_import.json. 실제 AppData의 전후 완전 동일성을 PASS라고 표시하지 않는다.
''')
    write('RELEASE_APPROVAL.md',f'''# 최종 배포 판정

**CONDITIONAL RELEASE — 0.28.0 후보. v1.0 정식 RELEASE READY 승인은 보류한다.**

검증 범위 내 미해결 P0 **0**, P1 **0**, P2 **1**(PERF27-01: 20시즌 통산 최초 전체 집계 추가 개선). 새로 찾은 조회 중 종료 약 14초 대기와 5인 장면의 상위 패널 잘림은 수정·재검증했다.

전체 **{total}회 / PASS {passed} / FAIL 0 / SKIP {len(skips)}**. 별도 Windows QTest **{native_pass} PASS**. 기존 571개에서 취소/스레드 격리/오류 구분/DB 보존 4개, 5인 배치·이벤트 전원 표시·메인 창 조상 경계 3개를 더했다. 기존 테스트 삭제나 새 SKIP은 없다. 기존 SKIP 2개는 실제 원본 세이브가 초기 미편성 상태가 아니라 해당 시작 조건이 맞지 않는 검사이며 독립 fixture로 그 흐름을 검사한다.

실제 ZIP EXE의 빈 실행·사진 추가·새 게임·실제 경기 저장·정상 종료·재실행, 읽기 전용 설치·사용자 저장·기존 세이브 가져오기·기존 행 보존 통과. UI는 소스 Windows QTest와 frozen Qt 자동 검증을 구분했다. 물리 창의 키보드 종료는 exit0으로 확인했지만 전체 마우스 플레이는 도구 오류로 미검증이다.

RELEASE READY에 남은 확인:

- Python 미설치/프로젝트 없는 깨끗한 Windows PC 또는 VM: **NOT TESTED**
- 물리 마우스·키보드로 모든 핵심 플레이, 실제 OS DPI 100/125/150%: **NOT TESTED** (Alt+F4 종료만 별도 확인)
- 실제 오디오 청취, 백신/SmartScreen 환경: **NOT TESTED** / 실행 파일 미서명

실제 AppData는 작업 중 진행 상태가 변해 전후 동일성은 NOT COMPARABLE이다. 이 파일을 QA 진행 대상으로 쓰지 않았으며 현재 무결성은 ok다. 프로젝트 원본과 보호 파일은 동일하고, 복사본 업그레이드는 모든 기존 행 보존을 통과했다. 현재 진행을 임의로 복구하거나 덮어쓰지 않았다.

위 제한을 고지한 개발 장비/테스터 대상 사용은 가능하나, 확인하지 않은 환경까지 정식 승인했다고 주장하지 않는다. 배포용 사용법은 USER_GUIDE.md 및 ZIP의 README_실행안내.txt에 있다.
''')
    write('RELEASE28_SUMMARY.md',f'''# IDOL Manager 28차 최종 결과

**0.28.0 배포 후보 / CONDITIONAL RELEASE.** 새 게임 콘텐츠·게임 수치·DB 스키마를 추가하지 않았다. 기존 27차 배포 ZIP/보고서는 보존했다.

## 구현·수정

- **5명 전원 표시:** 팀마다 윗줄 3명·아랫줄 가운데 2명. 사진 선택 드롭다운을 제거하고 판정 중에도 10명을 유지한다. 이름/리더 ★/주요·일반 성공을 표시하고 프로필 열기와 사진 비율을 유지한다.
- 작은 창에서 DockWorkspace가 이전 무대 최소 높이를 유지해 아랫줄을 자르는 현상을 수정했다. 모든 조상 위젯까지 경계를 검증한다.
- 통산 조회 중 종료 대기 **{before['close_during_query_seconds']:.3f}→{after['close_during_query_seconds']:.3f}초**. 읽기 worker만 안전하게 취소한다.

## 결과

| 항목 | 결과 |
|---|---|
| 최종 전체 회귀 | {total}회: PASS {passed} / FAIL 0 / SKIP {len(skips)} |
| 별도 Windows QTest | PASS {native_pass} / FAIL 0 / SKIP {len(ns)} |
| ZIP/내부 파일/런타임/체크섬 | PASS |
| EXE 빈 실행·사진 추가·새 게임·경기 저장·재실행 | PASS |
| 읽기 제한 설치·기존 DB 가져오기 | PASS / 비관리자 / 기존 행 보존 |
| 800×700·1280×720·1920×1080 × Qt 1/1.25/1.5 | PASS / 5인 전원 표시 포함 |
| 깨끗한 Python 미설치 PC/VM | NOT TESTED |
| 전체 물리 GUI 플레이 / OS DPI 3종 | NOT TESTED (키보드 정상 종료만 확인) |
| P0 / P1 / P2 | 0 / 0 / 1 (통산 첫 집계 성능) |

통산 전체 조회는 첫 20명을 약 {after['first_rows_seconds']:.2f}초에 보여주고 전체 계산은 더 걸린다. 입력·다른 화면 사용·숨긴 화면 결과 폐기·종료 취소를 검증했으며 이를 잔여 성능 과제로 남겼다. 조회 결과를 삭제하거나 정확도를 낮추지 않았다.

프로젝트 원본 DB와 보호 파일 {preserved['protected_files']}개는 동일하다. **실제 AppData는 별도 실행/진행과 겹쳐 시작 0일→현재 {delta['day'] if delta else '알 수 없음'}일 변화가 관찰되어 전후 동일성은 보증하지 않는다.** QA는 별도 경로/복사본만 사용했고 현재 실제 DB 무결성은 ok다. 진행을 되돌리거나 초기화하지 않았다.

## 실행·파일

최종 ZIP: `{archive['archive']}`

SHA256: `{archive['sha256']}`

압축 내부 IDOL_Manager 폴더 전체를 유지해 EXE를 실행한다. 기존 사용자는 게임을 종료·백업한 뒤 EXE/_internal 등만 기존 설치 루트로 복사한다. AppData의 기존 저장 파일을 우선 사용하며 원본 data/assets를 덮어쓰지 않는다. **최종 실행본은 dist/release28/IDOL_Manager/IDOL_Manager.exe**이고, 기존 dist/IDOL_Manager는 보존된 27차다.

주요 변경: idol_manager/records_read.py(신규), records_service.py, ui/records_queries.py, ui/records_page.py, ui/battle_view.py, ui/portrait_layout.py, app.py 및 runtime_check.py(QA 진단), packaging/windows_version.txt, tests/test_release28.py(신규 4개), tests/test_battle_view.py(3개 추가), tools/release28_*.py, README 및 본 보고서. 게임 생성/경기/성장/부상/재정/계약 공식 변경 없음.

## 상세 문서

- [클린 설치](CLEAN_INSTALL_TEST.md)
- [GUI 및 5인 배치](WINDOWS_GUI_ACCEPTANCE.md)
- [성능](FINAL_PERFORMANCE.md)
- [패키지/데이터 보호](RELEASE_PACKAGE_AUDIT.md)
- [배포 판정](RELEASE_APPROVAL.md)
- [사용자 안내](USER_GUIDE.md)
''')
    guide=(ROOT/'dist/release28/IDOL_Manager/README_실행안내.txt').read_text(encoding='utf8')
    write('USER_GUIDE.md','# IDOL Manager 0.28.0 사용자 안내\n\n'+guide)
    print(status)
if __name__=='__main__':main()
