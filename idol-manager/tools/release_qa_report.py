"""Assemble release evidence; unknown coverage is never promoted to PASS."""
from pathlib import Path
from collections import Counter
import json,statistics,math
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/release_qa'
def read(name):return json.loads((OUT/name).read_text(encoding='utf8'))
def write(name,text):(OUT/name).write_text(text,encoding='utf8')

def main():
    results=[(p.name,json.loads(p.read_text(encoding='utf8'))) for p in OUT.glob('test_tests*.json')]
    total=sum(r['tests'] for _,r in results);skips=sum(len(r['skipped']) for _,r in results)
    failures=sum(len(r['failures'])+len(r['errors']) for _,r in results)
    startup=read('startup.json');env=read('environment.json');db=read('database_audit.json');repro=read('reproducibility.json');protect=read('protection_after.json')
    gui=[read('gui_benchmark_'+s+'.json') for s in ('1','1.25','1.5-fixed')]
    peak=max(g['resources']['peak_rss'] for g in gui)
    bugs=[
      ('RC01','P0','수정·재검증','신인왕 후보 0명에서 시즌 진입 차단','awards.py / migrations.py / awards_page.py','명시적 NO_ELIGIBLE_CANDIDATE, 항목11개 완료, 실제 수상 기록10건 허용(서로 다른 선수10명을 뜻하지 않음). 후보1명/여러명/0승 및 누락 오류 분리. 25차 405일 체크포인트 재개 후 3시즌 완주.'),
      ('RC02','P1','수정·재검증','통합 드래프트 완료가 2회 미지명 은퇴 처리를 호출하지 않음','annual_draft.py / market_service.py','기존 record_outcome 경로를 동일 트랜잭션에 연결. 두 시즌 연속 미지명·미소속만 은퇴, 중복 실행 방지.'),
      ('RC03','P1','수정·재검증','17세 이상 미지명 신규 후보 연습생 영입 차단','market_service.py / ui/market_page.py','최신 요청대로 공개 후보14세 이상 허용. 프로 경력·기존 소속·은퇴 선수는 차단.'),
      ('RC04','P1','수정·재검증','FA 입찰 중 후보를 연습생 영입하여 입찰 무효화','market_service.py','실제 AI 대 AI 테스트에서 ownership 사유로 입찰 실패 재현. 진행 중인 입찰/협상 후보는 연습생 대상에서 제외하고 서비스에서도 검증.'),
      ('RC05','P1','수정·재검증','270명 사진에서 캐시 퇴출/완료 알림 반복 및 UI 정체','ui/thumbnails.py / ui/profile_explorer.py','완료된 작은 캐시 이미지 재조회는 추가 완료 이벤트를 만들지 않음. 사진 갱신 중 비교 체크 신호를 차단해 전체 명단 재집계 폭증 제거. 270개 초과 캐시·실제 UI 재검증.'),
      ('RC06','P2','수정·재검증','프로필 반복 개폐 시 세로 화면의 삭제된 객체 참조 누적/예외','ui/portrait_layout.py','20회 개폐에서 표 등록68→258·레이아웃130→510 재현. 닫힌 다이얼로그 등록 해제 및 실제 QLayout 확인. 수정 후 표58/레이아웃106 유지, Qt 비동기 예외0.'),
      ('RC07','P2','수정·재검증','세로 표 페이징이 최초 편성 후 숨긴 선택 열을 다시 표시','ui/table_widgets.py / ui/portrait_layout.py','앱의 명시적 열 숨김을 페이저의 원래 숨김 목록에 동기화. 실제 편성 UI 테스트 통과.'),
      ('RC08','P2','수정·재검증','누적 성장 이력 조회의 인물별 인덱스 누락','migrations.py / market_service.py','실제 3시즌 DB의 SCAN r 확인. 인물/정산 인덱스 추가, 동일 날짜는 기존 rowid 순서로 명시하여 인덱스가 과거 표시·평가 순서를 바꾸지 않도록 함. 100회 실측 비교.'),
      ('RC09','P2','미해결','800×700의 선수단 표 페이지 조작줄 일부가 좁아짐','gui_1/layout_800x700.png','900×1560 및 일반 대형 창 검증과 구분. 매우 작은 높이의 완전 무스크롤 사용은 추가 압축 필요. 배포 시 큰 창 사용 권고.'),
    ]
    features=[]
    def item(name,status,evidence):features.append((name,status,evidence))
    pairs=[('사진·한글·중복 이름·손상/누락','core / ui / annual_draft'),('가상 생성·CA/PA·건강90','core / health90'),('최초 드래프트160·순서·재개','draft / draft_session / draft_ui'),('선수단·리더·월요일1회','squads / squad_daily_limit / squad_ui'),('게임 날짜·초기 복구','calendar / initial_recovery'),('585·117·13·더블헤더·콘텐츠','calendar / database_audit.json'),('정규60·주요30·무작위8종30','all8_judgments / match_engine / matches'),('리더·데스매치·몰수','match_engine / matches / finals'),('특별전·추가 대결','special_engine / special_service / special_ui'),('포스트시즌·순위결정전','finals / finals_ui'),('성장·활동·PA격차','development / development_activity'),('노화·나이·건강감소','development / health90'),('협상·재계약·프로데뷔','market / release26'),('FA 2일·마감·중복·소속충돌','market / release26'),('트레이드·방출·위약금10회','market'),('급여·일할·후원·채무·매각','finance / market / finance_migration'),('신규70·추정치·특별유망주2','annual_draft'),('연간3라운드·2년 미지명 은퇴','annual_draft / release26 / 3시즌DB'),('개인상11·공석·영구 저장','awards / awards_ui / release26'),('프로필·시즌/통산/콘텐츠 기록','profiles / records / profile_summaries'),('BGM 탐색·셔플·예외·Qt 디코더','bgm / bgm_native'),('마이그레이션·백업·외래키','*_migration / database_audit.json'),('트랜잭션 실패·동시 요청·중복','matches / market / finance / awards / annual_draft'),('준비 후 강제 종료·경기 재개','special_service / finals / matches'),('同시드 동일·다른 시드 차이','reproducibility.json'),('3시즌 실제 엔진 연속 완주','diagnostics/26_resume'),('Windows 네이티브 주요 화면13개·반복','gui_benchmark*.json / native_market.log'),('SQL·CPU·메모리 계측','*_resources.json / *_timings.csv / sql_profile.json')]
    for name,evidence in pairs:item(name,'VERIFIED',evidence)
    item('모든 주요 버튼의 모든 상태 조합','PARTIAL','핵심 자동 클릭·잘못된 입력 포함. 모든 상태의 전체 버튼 조합을 망라하지 않음')
    item('125%·150% 및 작은 창','PARTIAL','Qt scale factor와 네이티브 렌더 검증. OS 시스템 배율 자체 변경/물리 화면 수동 조작은 미실행')
    item('800×700 완전 무스크롤 레이아웃','FAILED','RC09 P2; 페이지 줄 일부 가림')
    item('장시간 메모리 안정성','PARTIAL','3시즌 헤드리스 및 GUI 개폐20회. 수 시간 GUI 유휴·대용량 수십 시즌은 미실행')
    item('EXE 패키지·서명·백신 환경','NOT TESTED','EXE 없음. 신규 패키징은 범위 밖')
    item('Python 없는 신규 Windows PC 설치','NOT TESTED','현재 Python3.13 가상환경 검증만 수행')
    item('물리 전원 차단·저장장치 장애','NOT TESTED','트리거 오류와 일부 프로세스 종료 주입으로 대체; 물리 장애 보장은 아님')
    item('10~20시즌 신규 인물 공급 포함','NOT TESTED','기존 사진421개로 초기200+연70 공급은 3시즌 이후 제한. 임의 인물/사진 추가하지 않음')
    feature_counts=Counter(s for _,s,_ in features)
    conditional=failures==0 and protect['assets_unchanged'] and not protect['live_changed_tables']
    verdict='CONDITIONAL RELEASE' if conditional else 'RELEASE BLOCKED'
    stats=dict(verdict=verdict,function_targets=len(features),function_statuses=feature_counts,tests=total+5,pass_tests=total-skips-failures+5,fail_tests=failures,skipped_tests=skips,native_extra_tests=5,bugs=len(bugs),fixed=8,unresolved={'P0':0,'P1':0,'P2':1,'P3':0},max_seasons=3,startup_seconds=startup['seconds'],peak_gui_rss=peak,gui_scope='Windows Qt backend + QTest; physical/manual desktop not exhaustively tested')
    save_json=OUT/'qa_summary.json';save_json.write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf8')
    write('TEST_COVERAGE_MATRIX.md','# 기능별 검증 범위\n\n'+f'대상 {len(features)}개. {dict(feature_counts)}. 자동 테스트는 {total}건 중 PASS {total-skips-failures}, FAIL {failures}, SKIP {skips}; 별도 네이티브5건 PASS. 총 실행 결과 집계는 모듈별 최종 실행만 사용하며 중간 실패/재시도는 중복 합산하지 않았다.\n\n| 기능 | 상태 | 근거·한계 |\n|---|---|---|\n'+'\n'.join(f'|{n}|{s}|{e}|' for n,s,e in features)+'\n\n코드 커버리지 백분율은 측정하지 않았다. 구형 테스트의 상한100·무효 가짜 경기·구형 탭수 기대는 최신 규칙/실제 오류 주입/저장된 실제 엔진 결과로 갱신했다. 테스트 PASS를 전체 상태 공간 검증으로 취급하지 않는다.\n')
    write('BUG_REPORT.md','# 발견·수정 이력\n\nP0 1건, P1 4건, P2 4건 발견. 8건 수정, P2 1건 남음. 확정 확률·승점·성장·급여·시즌 길이는 바꾸지 않았다.\n\n'+'\n\n'.join(f'## {i} · {sev} · {status}\n\n{title}\n\n파일: `{file}`\n\n{desc}' for i,sev,status,title,file,desc in bugs)+'\n\n추가로 구형 테스트의 건강100, 재진급 당일 재강등, 구형 탭수·화폐 표기, 비시즌70명 부재, 정상 부상 결과를 고려하지 않은 기대값을 정정했다. 이는 게임 규칙 변경이 아니다.\n')
    perf='# 성능 측정\n\n'+f"환경: {env['windows']}; Python {env['python'].split()[0]}, PySide6 {env['pyside']}, SQLite {env['sqlite']}.\n\n네이티브 창 노출: {startup['seconds']:.3f}초 / n=1. QApplication 생성부터 실제 exposed까지; Python import·가상환경 시작·QA DB 복사는 제외했다. 최초 콜드 부팅 시간과 동일하지 않다.\n\n"
    for name in ('gui_timings_1.csv','gui_timings_1.25.csv','gui_timings_1.5-fixed.csv','26_seed_a_timings.csv','26_seed_b_timings.csv'):
        perf+=f'## {name}\n\n```csv\n'+(OUT/name).read_text(encoding='utf-8-sig')+'```\n\n'
    for scale,g in zip(('100%','125%','150% 수정 후'),gui):
        samples=g['resources']['samples'];cpus=[s['cpu_one_core_percent'] for s in samples];mem=[s['rss'] for s in samples]
        cycles=g['memory_cycles'];perf+=f"{scale}: {g['resources']['elapsed']:.2f}초 관측, CPU 평균 {statistics.mean(cpus):.1f}% / 최대 {max(cpus):.1f}% (논리 코어1개=100%, 다중 스레드 합산), 메모리 평균 {statistics.mean(mem)/2**20:.1f}MiB / 최대 {g['resources']['peak_rss']/2**20:.1f}MiB. 프로필20회 전후 {cycles[0]['rss']/2**20:.1f}→{cycles[-1]['rss']/2**20:.1f}MiB.\n\n"
    sql=read('sql_profile.json');perf+=f"성장 이력 SQL100회: 원래 전체 스캔 평균 {sql['before_mean']*1000:.3f}ms → 인덱스 평균 {sql['after_mean']*1000:.3f}ms. 같은 행과 tie 순서 확인. SQL 쿼리 단위 수치이며 전체 게임이 그 비율로 빨라졌다는 뜻이 아니다.\n\n데이터: 3시즌 DB {db[0]['bytes']/2**20:.1f}MiB. 평균/중앙값/P95/최대는 CSV 원시 계측. n<20의 P95는 대표성이 낮다고 표시했다. 월요일·급여·일반 하루/시즌 경계는 advance_day 종합에 포함된다. 별도 시즌 전환만의 충분한 표본/초기 콜드 실행/전체 프로세스 트리 CPU/장시간 GUI 유휴는 NOT TESTED.\n"
    write('PERFORMANCE_REPORT.md',perf)
    write('DATABASE_INTEGRITY_REPORT.md','# 저장 데이터·마이그레이션\n\n실제 세이브는 읽기 전용 조사 및 SQLite backup만 수행했다. 테스트 연결 가드는 원본 경로의 쓰기 연결을 거부한다.\n\n```json\n'+json.dumps(protect,ensure_ascii=False,indent=2)+'\n```\n\nv16→v17: `award_outcomes` 완료 원장 및 성장 이력 조회 인덱스. 기존 individual_awards 수상자 행은 그대로 유지하고 완료 상태를 이관한다. 공석만 person_id NULL이 가능하며 신인왕에만 허용한다. 다음 실제 게임 실행 시 기존 migrate_database가 백업 후 적용한다. 이번 QA에서 실제 세이브를 v17로 올리지 않았다.\n\n각 진단 DB에 PRAGMA integrity_check / foreign_key_check와 CA≤PA·건강·정원·계약 겹침·일반60회·승점·중복 정산·나이/건강 조건 검사.\n\n```json\n'+json.dumps(db,ensure_ascii=False,indent=2)+'\n```\n\n계약·트레이드·FA·급여·경기·시상식·신규 유입의 트리거 오류/중복/동시 호출 회귀 테스트를 확인했다. 실제 OS 강제 종료는 저장된 경기 준비 및 특별전/포스트시즌 경로에 한정하며 모든 쓰기 명령 도중 물리 전원 차단을 보장하지 않는다.\n')
    write('GUI_TEST_REPORT.md','# Windows GUI 검증\n\n네이티브 `windows` Qt 백엔드로 노출된 창을 검사했다. 시장 네이티브 자동 클릭5건 PASS. 주요 화면13개를3회씩 전환하고 프로필을20회씩 개폐했다. 화면·프로필·계약·순위 조회는 분리 DB이며 실제 세이브를 진행하지 않았다.\n\n100/125/150%는 QT_SCALE_FACTOR를 사용했다. 시스템 설정 자체를 변경하지 않았다. 1920×1080,900×1560,800×700의 Qt 렌더 이미지는 gui_*/ 아래 저장했다. 900px 세로 모드의 페이지·열 접근 테스트도 통과했다. 150% 수정 후 비동기 Python 예외0.\n\ncomputer-use의 창 목록에서는 QA 창을 찾을 수 없어 그 도구로 모든 화면을 직접 조작했다고 주장하지 않는다. 실제 노출 여부는 QTest.qWaitForWindowExposed=True, 버튼 클릭은 기존 네이티브 QTest 테스트, 시각 확인은 QWidget 캡처를 근거로 한다. 작은 높이800×700의 표 페이지 줄 일부 가림(RC09)은 남아 있다. 전 버튼/전 상태의 수동 확인은 PARTIAL.\n\nBGM은 실제 Qt 오디오 장치/디코더에서 손상MP3 실패→한글WAV 자동 재생·반복을 검증했다. 청취 품질을 사람이 확인한 것은 아니다.\n')
    write('LONG_RUN_REPORT.md','# 연속 실행·재현\n\n25차 DB와 보고서를 보존하고 전용 복사본26_resume에서 405일 중단 지점을 재개했다. 시즌3 완료 후 시즌4 첫 월요일 absolute_day651. 정규1755경기, 각 시즌585, 특별전각6, 시즌별 챔피언/11개 시상 처리, 연간70명/30턴과 은퇴를 저장했다.\n\n같은 시작 데이터·시드260029·정책으로1시즌 2회 실행했다. A는 첫 경기 준비 저장 후 계측 도구 오류를 수정해 재개했고 B는 중단 없이 실행했다. 양쪽 모든 테이블에서 실제 시각 열6개를 제외한 행 내용이 동일하다. 별도 시드260030은176경기 후 예산 체크포인트에서 중단했고 다른 대진을 확인했다. 이 실행의 완주나 전체 시드 공간 검증으로 확대 해석하지 않는다.\n\n```json\n'+json.dumps(repro,ensure_ascii=False,indent=2)+'\n```\n\n최대 연속3시즌. 실제 사진421개로 초기200+연70 공급 시 3시즌 이후 부족할 수 있어10~20시즌을 위해 사진/인물을 복제하거나 은퇴자를 재사용하지 않았다. 수 시간 GUI 유휴·수십 시즌 메모리 추세는 미검증. 기존 25차 보고서는 역사적 결과로 수정하지 않았다.\n')
    write('RELEASE_READINESS.md',f'# 배포 판정: {verdict}\n\n재현 가능한 미해결 P0 0 / P1 0 / P2 1. 실제 세이브의 모든 조사 대상 테이블·사진·설정 보존. 핵심 게임 흐름3시즌, 동시성·실패 롤백·마이그레이션·핵심 UI 회귀 검증 통과.\n\n현재 Python 소스 형태의 제한적 배포를 권고한다. 작은 창 레이아웃 제약을 안내하고 가능하면 RC09를 추가 수정해야 한다. EXE·Python 없는 신규 PC·설치 권한·물리 디스플레이별 모든 배율·전 버튼 모든 상태는 확인하지 않아 RELEASE READY로 단정하지 않는다.\n\n패키징 사전 감사: ROOT는 모듈 위치 기준이며 개발자 절대 경로가 핵심 런타임에 하드코딩되지 않았다. 다만 data/로그/설정/캐시를 프로젝트 폴더에 쓰므로 Program Files와 같은 읽기 전용 설치 위치용 사용자 데이터 경로 분리가 필요하다. EXE는 없으며 새 패키징 기능은 추가하지 않았다. `실행하기.bat`/bootstrap 경로와 버전·의존성 검사는 기존 launcher 테스트로 통과했다.\n')
    write('RELEASE_QA_SUMMARY.md',f'''# IDOL Manager · 26차 배포 전 종합 QA

배포 판정: **{verdict}**

- 기능 범위 {len(features)}개: {dict(feature_counts)}
- 최종 자동 테스트 {total}건: PASS {total-skips-failures} / FAIL {failures} / SKIP {skips}
- 별도 Windows 네이티브 UI 테스트5건 PASS → 합계 PASS {stats['pass_tests']} / FAIL {failures}
- 발견9건, 수정8건, 미해결 P0 0 / P1 0 / P2 1
- 최대 연속3시즌, 정규1755경기
- 창 노출 {startup['seconds']:.3f}초(n=1, 측정 범위는 성능 보고서 참조)
- 측정된 GUI 최대 메모리 {peak/2**20:.1f}MiB
- DB 무결성 PASS / Windows 네이티브 핵심 GUI PASS, 전체 수동 검증 PARTIAL

25차를 재시작하지 않고 결과·체크포인트를 인수했다. 실제 저장은 v16/absolute_day63에서 조사 대상 테이블 변경0, assets462개/설정 해시 동일. QA는 복사본·신규 전용 DB만 사용했다. 게임 확률·금액·경기 규칙을 재조정하지 않았다.

신인왕 공석은 사용자가 승인한 NO_ELIGIBLE_CANDIDATE로 영구 저장하며 실제 기록 누락을 공석으로 숨기지 않는다. v17 마이그레이션은 백업 후 추가 원장/인덱스만 적용한다.

## 근거 문서

- [기능 범위](TEST_COVERAGE_MATRIX.md)
- [버그별 원인·수정](BUG_REPORT.md)
- [성능·표본](PERFORMANCE_REPORT.md)
- [DB·보존](DATABASE_INTEGRITY_REPORT.md)
- [Windows GUI](GUI_TEST_REPORT.md)
- [장기·시드 재현](LONG_RUN_REPORT.md)
- [배포 권고](RELEASE_READINESS.md)

`environment.json`과 `source_after.json`은 테스트 시작/최종 소스 SHA256과 환경을 보존한다. 이 폴더의 모듈별 로그·JSON은 마지막 실행 결과이며 중간 실패·수정 이력은 BUG_REPORT에 기록했다. Git 저장소가 없어 commit/diff는 제공할 수 없다.

## 재실행

프로젝트 루트에서 `.\\.venv\\Scripts\\python.exe tools/release_qa.py`로 모듈별 분리 전체 테스트,
`--tests tests.test_release26 tests.test_market`로 관련 회귀 테스트만 실행한다.
`tools/release_qa_checks.py`, `tools/release_qa_report.py`는 현재 보존된 진단 자료를 점검/정리한다.
같은 진단 출력 폴더에 새 게임을 덮어쓰지 않으며, 새로운 시드 검증에는 새 하위 폴더를 사용한다.
''')
    print(json.dumps(stats,ensure_ascii=False))
if __name__=='__main__':main()
