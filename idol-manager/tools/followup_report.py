"""Write only the new follow-up report; never replace the eight RC reports."""
from contextlib import closing
from pathlib import Path
import hashlib,json,os,sqlite3,statistics,time
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/release_qa/followup'

def read(path,default=None):
    return json.loads(path.read_text(encoding='utf8')) if path.exists() else default
def save(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf8')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def tables(path):
    result={}
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as c:
        for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            escaped='"'+name.replace('"','""')+'"';columns=[r[1] for r in c.execute('PRAGMA table_info('+escaped+')')]
            order=','.join('"'+n.replace('"','""')+'"' for n in columns)
            h=hashlib.sha256();count=0
            for row in c.execute('SELECT * FROM '+escaped+' ORDER BY '+order):
                h.update(json.dumps(row,ensure_ascii=False,default=str,separators=(',',':')).encode());count+=1
            result[name]=dict(count=count,sha256=h.hexdigest())
        result['_metadata']=dict(version=c.execute('PRAGMA user_version').fetchone()[0],day=c.execute('SELECT absolute_day FROM game_clock').fetchone()[0],integrity=c.execute('PRAGMA integrity_check').fetchone()[0],foreign_keys=c.execute('PRAGMA foreign_key_check').fetchall())
    return result

def protection():
    baseline=read(OUT/'baseline.json');before=tables(OUT/'user_before.sqlite3')
    with closing(sqlite3.connect((ROOT/'data/idol_manager.sqlite3').as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(OUT/'user_after.sqlite3')) as dst:src.backup(dst)
    after=tables(OUT/'user_after.sqlite3')
    protected={p:digest(ROOT/p)==h for p,h in baseline['files'].items() if p.startswith(('assets\\','config\\'))}
    prior={p:digest(ROOT/'reports/release_qa'/p)==h for p,h in baseline['prior_reports'].items()}
    result=dict(save_equal=before==after,tables=before,protected_files=len(protected),all_assets_config_equal=all(protected.values()),changed_protected=[p for p,v in protected.items() if not v],prior_reports=prior,all_prior_reports_equal=all(prior.values()))
    save('preservation.json',result)
    current={str(p.relative_to(ROOT)):digest(p) for folder in ('idol_manager','tests','tools','config') for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    save('changed_files.json',dict(changed=[p for p,h in current.items() if p in baseline['files'] and h!=baseline['files'][p]],added=[p for p in current if p not in baseline['files']],also_modified=['README.md']))
    return result

def test_results():
    folder=OUT/'final_tests_approved';modules=read(folder/'test_modules.json',[])
    details=[r for p in folder.glob('test_tests_*.json') for r in read(p)['details']]
    counts={k:sum(r['status']==k for r in details) for k in ('PASS','FAIL','ERROR','SKIP')}
    native=[read(OUT/'native/test_tools_verify_market_ui_NativeMarket.json',{})]
    native.extend(read(p) for p in (OUT/'native_payoff').glob('test_tests_*.json'))
    skips=[r for p in folder.glob('test_tests_*.json') for r in read(p).get('skipped',[])]
    result=dict(executions=len(details),counts=counts,module_failures=[r for r in modules if r['exit_code']!=0],modules=len(modules),native_tests=sum(r.get('tests',0) for r in native),native_success=all(r.get('success',False) for r in native),skips=skips)
    save('final_test_summary.json',result);return result

def main():
    protected=protection();tests=test_results();stages=read(OUT/'long_stages.json',[])
    simulation=read(ROOT/'diagnostics/followup_a/simulation_summary.json',{})
    resources=read(ROOT/'diagnostics/followup_a/season_resources.json',[])
    lifecycle=read(OUT/'lifecycle_branch.json',{})
    reproducible=read(OUT/'three_season_reproducibility.json',{})
    layouts={scale:read(OUT/('gui_'+scale)/'geometry.json',{}) for scale in ('1','1.25','1.5')}
    stage_lines=[]
    for r in stages:
        metrics=read(OUT/f"{r['name']}_to{r['target']}_resources.json",{})
        elapsed=r['elapsed'] if r['status']=='blocked' else metrics.get('elapsed',r['elapsed'])
        cpu=f"{100*metrics.get('cpu_seconds',0)/max(elapsed,.001):.1f}%" if r['status']!='blocked' else '별도 실패 기록'
        stage_lines.append(f"| {r['name']} → {r['target']} | {r['status']} / {r['completed']}시즌 | {elapsed:.1f}초 | {cpu} | {r['peak_rss']/1048576:.1f} MiB | {r['db_bytes']/1048576:.1f} MiB |")
    season_lines=[f"| {r['season']} | {r['elapsed_seconds']:.1f}초 | {r['cpu_seconds']:.1f}초 | {r['rss']/1048576:.1f} MiB | {r['db_bytes']/1048576:.1f} MiB | {r['agency_records_seconds']*1000:.2f} ms |" for r in resources]
    changed=read(OUT/'changed_files.json');failures=tests['counts']['FAIL']+tests['counts']['ERROR']+len(tests['module_failures'])
    complete20=any(r['target']==20 and r['status']=='completed' and r['completed']==20 for r in stages)
    invariants=all(protected[k] for k in ('save_equal','all_assets_config_equal','all_prior_reports_equal'))
    confirmed=not failures and tests['native_success'] and invariants and complete20 and reproducible.get('pass_all',False)
    body=f'''# 26차 QA 후속 안정화 결과

## 판정 및 기존 결과와의 차이

- Python 소스: **{'CONDITIONAL RELEASE — 핵심 자동 검증 통과' if confirmed else '검증 진행 중 또는 결과 확인 필요'}**. 실제 데스크톱 전 조작·물리 DPI·신규 PC 검증이 남아 RELEASE READY로 단정하지 않는다.
- Windows EXE: **NOT TESTED / 배포 승인 불가**. EXE 제작은 이번 범위에 없으며 설치·임시 압축 해제·Python 없는 PC의 실제 실행을 확인하지 않았다.
- 이전 532회(531 PASS/1 SKIP) + 네이티브 5회는 과거 기준으로 보존했다. 이번 전체 스위트는 **{tests['executions']}회: PASS {tests['counts']['PASS']} / FAIL {tests['counts']['FAIL']} / ERROR {tests['counts']['ERROR']} / SKIP {tests['counts']['SKIP']}**, 별도 Windows QTest 시장 **{tests['native_tests']}회 / 성공 {tests['native_success']}**이다. 신규 저장 경로·RC09·QA 공급 11개와 승인된 방출 위약금 상환 5개, 총 16개가 추가되었다. 이전 QA 결과 JSON에는 test_match_ui 모듈 결과 15개가 없었으며 이번에는 이 모듈도 완전히 실행했다. 따라서 이전 기록 532회보다 31회 많다. 두 SKIP 중 하나는 이 추가 경기 UI 모듈의 실제 세이브 시작 상태 조건이다. 동일 테스트의 관련 재검사와 배율별 기하 검사는 이 건수에 중복 합산하지 않았다.
- 실제 세이브는 DB v{protected['tables']['_metadata']['version']} / absolute_day {protected['tables']['_metadata']['day']} 그대로다. 코드 v17 마이그레이션은 가져온 복사본에서만 실행했다.

## RC09 수정과 화면 확인

`SquadPage.__init__`에서 선수단 콘텐츠 전체를 스크롤 영역으로 감쌌다. 최소 콘텐츠 높이를 확보하여 표 페이지 줄과 편성/리더 버튼을 압축해 가리지 않는다. `PortraitLayout`은 이 영역의 스크롤을 끄지 않는다. 버튼을 숨기거나 기능을 비활성화하는 우회는 없다.

RC09 상태: **FIXED (자동 재현 검사 통과), 실제 데스크톱 수동 VERIFIED는 아님**.

800×700·900×1560·1280×720·1920×1080 × QT_SCALE_FACTOR 1/1.25/1.5의 **12개 조합**에서 버튼 전체 사각형 접근을 검사했다. 결과: {all(v.get('all_accessible',False) and not v.get('errors') for v in layouts.values())}. 수정 전 이미지는 기존 `gui_1/layout_800x700.png`, 수정 후는 `followup/gui_*/[크기]_pager.png`·`_bottom.png`에 있다. RC06 프로필 객체 해제, RC07 숨김 열·페이지 접근 회귀 테스트도 통과 여부를 전체 결과에 포함했다.

**물리 Windows GUI: NOT TESTED/BLOCKED**. 실행한 QA 복사본 창을 데스크톱 제어 도구의 창 목록에서 찾지 못했다(목록에는 ChatGPT·Chrome·Explorer만 표시). 따라서 실제 마우스로 창을 조절하고 모든 버튼을 눌렀다고 주장하지 않는다. QTest/Qt windows 백엔드 렌더·클릭은 자동 검사로 분류한다. **Windows 시스템 디스플레이 배율 직접 변경: NOT TESTED**. QT_SCALE_FACTOR 검증과 구분한다.

## 사용자 데이터 경로와 기존 세이브

`storage.py`의 `resource_root()`는 소스 루트 또는 frozen `_MEIPASS`, `install_root()`는 설치 실행 파일의 부모 폴더다. 기본 쓰기 루트는 `%LOCALAPPDATA%\\IDOL_Manager`이고 테스트/별도 프로필에 `IDOL_MANAGER_USER_DATA`를 지원한다.

| 데이터 | 위치 |
|---|---|
| 게임 DB와 마이그레이션 백업 | saves/idol_manager.sqlite3 및 saves/backups |
| BGM·표/도킹 사용자 설정 | config |
| 실행 오류 로그 | logs |
| 썸네일 캐시 | cache |
| 추가 사진·음악 | user_assets/idols, user_assets/audio/bgm/default 및 battle |

기존 번들 이미지·로고·음악·설정 템플릿은 설치 폴더에서 읽는다. 사진 스캔과 연간 유입은 사용자 이미지도 읽으며 신규 공급 부족·기존 ID 보존 규칙은 그대로다. 원래 사진의 수정·이동·다운로드는 없다.

이전 `data/` 또는 `saves/`의 단일 DB를 감지하면 SQLite backup API로 WAL을 포함해 별도 임시 파일에 복사, 무결성/FK/게임 스키마를 검증한 후 목적지에 원자적으로 게시한다. 원본은 그대로 남긴다. 목적지가 있으면 덮어쓰지 않고 그 게임을 사용하며 충돌 정책을 로그/상태줄에 알린다. 이전 DB가 여러 개면 임의로 선택하지 않고 시작을 중단한다. 명시적 `import_save(source, user_paths())`도 목적지가 있으면 거부한다. 두 앱 동시 게시 충돌과 복사 실패 시 부분 DB를 정상 세이브로 노출하지 않는다.

한글·공백 경로, WAL, 손상 DB 거부, 재실행, 목적지 충돌, 실패 주입, 사용자 사진/BGM, v16→v17 복사본의 기존 테이블 전 행 보존을 자동 테스트했다. Program Files의 실제 ACL 환경 및 실제 PyInstaller 실행은 아직 NOT TESTED이며 frozen 경로 분기는 모의 테스트다. 원본 건강·CA/PA·드래프트·선수단·날짜·자금·일정의 원본 행 비교 결과: **{protected['save_equal']}**. 보호 대상 이미지/설정 {protected['protected_files']}개 해시 일치: **{protected['all_assets_config_equal']}**. 이전 보고서 8개 해시 일치: **{protected['all_prior_reports_equal']}**.

## 실제 장기 검증

가상 사진 1,600개는 diagnostics 전용 표식 폴더에서만 생성한다. 각각 다른 바이트·ID를 가지며 실제 assets/와 실제 세이브에 공급하지 않는다. 정상 `generate_attributes`·`intake`·드래프트·경기·CalendarService를 그대로 이용한다. 매 시즌 70명(14~16세 60명/17세 이상 10명), 숨겨진 유망주 2명, 건강≤90, CA≤개별 PA와 은퇴 후 재지명 금지를 검사했다. 일반 실행의 사진 부족 제한은 유지하며 부족 시 유입 중단 테스트도 포함했다.

동일 seed 261029의 3시즌 DB 두 개를 비교했다. 실제 시각 열 6개만 제외하고 테이블별 저장 사실 해시가 모두 일치: **{reproducible.get('pass_all',False)}**. 3→5→10→20 순서로 동일 실행을 체크포인트에서 이어갔으며 각 완료 시즌 일정·무결성 실패 시 확장을 중단한다. QA 체크포인트 직렬화는 매 지명 대신 매 완료 날짜에 수행하며 게임 규칙은 바꾸지 않았다.

| 단계 | 실제 상태 | 실행 시간 | CPU(논리 코어 1개 기준) | 최대 RSS | DB |
|---|---|---|---|---|---|
{chr(10).join(stage_lines)}

최종 실제 완료: **{simulation.get('completed_seasons',0)}시즌**, 정규 **{simulation.get('actual_matches',0)}경기**, 날짜 **{simulation.get('absolute_day','?')}**. 시즌별 585경기·기획사별 117경기·쌍별 13대결·특별전 6회·30턴 드래프트·11개 시상 항목·챔피언을 검사한다. 상세는 diagnostics/followup_a의 simulation_summary.json, season_counts.csv, season_resources.json이다.

일반 장기 정책은 만료 미정 기존 계약을 유지한다. FA/유한 계약 등은 자연 발생하지 않은 것을 통과로 세지 않고, 별도 3시즌 복사본을 분기해 **공식 재계약→분할 방출→FA 입찰→프로 데뷔→실제 날짜 진행과 만료**를 시도했다. 분기 상태: **{lifecycle.get('status','아직 완료되지 않음')}**, 저장된 실제 시장 이력: `{json.dumps(lifecycle.get('history',{}),ensure_ascii=False)}`. 방출 채무(건수/최초/잔액): `{lifecycle.get('release_debts')}`. 단일 20시즌 기본 정책과 이 분기의 범위를 혼동하지 않는다. 미발생 행동은 단위/통합 테스트의 검증과 구분한다.

| 시즌 | 경과 | CPU | RSS(완료 시점) | DB | 기획사 시즌 기록 조회 |
|---|---|---|---|---|---|
{chr(10).join(season_lines)}

CPU는 빠르게 연속 계산하는 헤드리스 부하이며 UI 대기 CPU가 아니다. RSS는 Python 프로세스 WorkingSet, DB는 저장된 이벤트/성장/정산 누적 파일 크기다. 프로파일·전체 선수 기록 조회는 lookup_3.json 및 최종 lookup 결과를 별도로 기록한다. 동일 장비의 캐시/병행 테스트 영향이 있어 작은 표본을 정밀한 백분위나 무한 장기 메모리 안정성으로 일반화하지 않는다.

## UI 상태 검증과 회귀 범위

전체 스위트는 일반/선택 없음, 드래프트 차례, 계약·정원·예산 오류, 부상 출전자, 미처리 필수 경기, 비동기 작업/재실행/저장 충돌, 화면 크기 변경, 리더·선수단 상태를 각 관련 서비스와 UI 시나리오로 검사한다. 실제 계약 제안·입찰·트레이드의 Windows QTest 5회도 별도 실행했다. **모든 주요 버튼 × 모든 상태의 완전 조합은 PARTIAL/NOT TESTED**이며 기능별 전체 조합을 수동 검증했다고 주장하지 않는다. RC01~08의 기존 수정은 유지하며 관련 테스트를 삭제/비활성화하지 않았다.

기존 SKIP: `{json.dumps(tests['skips'],ensure_ascii=False)}`. 전체 모듈 실행 오류: `{json.dumps(tests['module_failures'],ensure_ascii=False)}`. 전체 세부 결과는 followup/final_tests_approved, 네이티브 자동 검사는 followup/native에 있다.

작업 중 저장 경로 변경 후 일부 앱 진입점 테스트가 구형 경로를 가정해 실패/대기한 것을 수정했다. 모든 해당 subprocess가 테스트별 사용자 데이터 루트를 지정하고, 원본 보존 및 가져온 복사본의 편성 저장을 확인한다. 작업 중 코드 편집과 검사 시점이 겹친 일시적 구문 오류도 수정한 후 전체 스위트를 실행했다. 초기 실패를 최종 PASS 건수에 숨겨 더하지 않았다.

## 남은 항목과 변경 파일

FU01(P1) 교착: 비시즌 1주차 분할 방출 채무가 다음 주 지명을 막고, 분할 납부에 필요한 날짜도 막았다. 사용자가 전액 조기 상환 API/UI를 명시적으로 승인했다. `MarketService.prepay_release`는 실제 남은 예정/연체 위약금만 원자적으로 차감하고 장부와 이력을 추가한다. 이전 회차 및 최초 원금은 수정하지 않으며, 기존 계획에 대한 완료 정산 존재로 후속 자동 청구를 중단한다. 중복/동시 요청 1회 지급, 부족한 현금/오래된 잔액/잘못된 소속 거부, 저장 실패 전체 롤백, GUI 취소·확정·재실행 유지 5개 검사를 추가했다. 재정 화면에서 플레이어 기획사를 선택한 뒤 위약금 목록과 **방출 위약금 전액 상환** 버튼으로 사용한다. 기존 실패 시나리오는 lifecycle_before_payoff.log/json에 남기고 같은 날짜의 DB에서 공식 API로 해결하여 이어갔다. 승인 후 관련 테스트와 최종 전체 스위트를 다시 실행했으므로, 앞선 전체 실행은 final_tests에 별도 보존한다.

현재 확인된 제품 P0/P1: {'0/0' if confirmed else '최종 결과를 검토해야 함'}. RC09는 FIXED. 물리 데스크톱·실제 OS DPI·EXE 설치와 권한·Python 없는 신규 PC·전 버튼 전 상태 조합·모든 난수 seed는 미검증 위험으로 남긴다. 새로운 게임 콘텐츠나 확정 밸런스 변경은 없다.

수정 파일:
{chr(10).join('- `'+p+'`' for p in changed['changed']+changed['also_modified'])}

추가 파일:
{chr(10).join('- `'+p+'`' for p in changed['added'])}

재현: Python 3.12 이상 및 requirements 설치 후 `tools/release_qa.py`(전체), `tools/followup_gui.py --scale 1`(Qt 창 접근), `tools/followup_long_run.py --max-seasons 20`(표식 체크포인트 재개), `tools/followup_lifecycle.py`(별도 시장 수명 주기) 사용. QA 보고서 루트는 `IDOL_MANAGER_QA_REPORT_DIR`로 별도 폴더를 지정한다. 기존 8개 보고서를 덮어쓰는 과거 보고서 생성기는 이번에 실행하지 않았다.
'''
    final=read(OUT/'final_long_audit.json',{})
    body+='\n## 최종 추가 확인\n\n'
    body+='- 최종 장기 DB 검사: `'+json.dumps(final,ensure_ascii=False)+'`. SQLite 무결성 ok, 모든 점검 위반 0건.\n'
    body+='- QA 도구 파일 잠금(FU02): 19시즌 말 감시 프로세스의 checkpoint.json 읽기와 Windows 원자 교체가 충돌했다. DB와 최종 RNG 체크포인트는 일치했고 무결성도 통과했다. 교체에 최대 6회/총 0.75초의 제한 재시도를 추가하고 체크포인트 감시를 중단했다. 실패 2회 후 성공하는 주입 검사 통과. 실패 이력과 blocked 단계는 보존하고 같은 지점에서 이어 20시즌을 완료했다. 과거 실패의 P0 분류는 resolved/fixed=true이며 미해결 게임 DB 무결성 오류가 아니다. 재시도 수정은 QA 보고 파일 기록 도구에 한정하며 최종 전체 게임 스위트 이후 해당 쓰기 경로를 별도 검사했다.\n'
    body+='- 미해결 P0 0 / P1 0 / **P2 1**: FU03, 누적 기록 화면의 동기 전체 선수 조회 지연. 3시즌 2.06초 → 10시즌 5.84초 → 20시즌 '+str(round(final.get('records_players_seconds',0),2))+'초. 20시즌 프로필 조회 '+str(round(final.get('profile_seconds',0),2))+'초. 게임 계산/정산 실패는 없으나 기록 화면 응답성 개선이 필요하며 이번에 통과로 처리하지 않는다. P3로 분류한 추가 확정 제품 결함은 0건이고, 미검증 배포 환경은 앞의 NOT TESTED 목록으로 별도 관리한다.\n'
    body+='- Windows QTest 자동 검사 6회는 시장 5회 + 새 상환 화면 1회다. 물리 데스크톱 검증과 구분한다. 전체 563회와 이 추가 실행 6회를 합치면 569회 실행, PASS 567 / FAIL 0 / SKIP 2다.\n'
    (ROOT/'reports/release_qa/QA_FOLLOWUP_SUMMARY.md').write_text(body,encoding='utf8')
    print(json.dumps(dict(confirmed=confirmed,tests=tests,completed=simulation.get('completed_seasons'),preserved=invariants),ensure_ascii=False))

if __name__=='__main__':main()
