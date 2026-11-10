"""Read-only analysis of a v25 diagnostic save; never opens a game save."""
from pathlib import Path
import argparse,json,sqlite3,sys,statistics,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parent))
from simulate_game import ROOT,csvfile,dump,schedule_audit,quick_audit

def analyze(folder):
    folder=folder.resolve()
    if not folder.is_relative_to(ROOT/'diagnostics') or not (folder/'run_manifest.json').exists():raise ValueError('진단 전용 폴더만 허용합니다.')
    c=sqlite3.connect((folder/'simulation.sqlite3').as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    summary=json.loads((folder/'simulation_summary.json').read_text(encoding='utf8'))
    def rows(sql):return [dict(r) for r in c.execute(sql)]
    exports={
      'content_agency_statistics':'''SELECT m.season,m.content_id,t.agency_id,COUNT(*) matches,SUM(t.outcome='win') wins,AVG(t.points) win_rate FROM match_team_stats t JOIN scheduled_matches m ON m.id=t.match_id GROUP BY m.season,m.content_id,t.agency_id''',
      'ability_development':'''SELECT (s.absolute_day/217)+1 season,r.person_id,r.age_before,s.kind,j.key skill,SUM(MAX(0,j.value)) increase,SUM(MAX(0,-j.value)) decrease FROM development_results r JOIN development_settlements s ON s.id=r.settlement_id,json_each(r.deltas_json) j GROUP BY season,r.person_id,r.age_before,s.kind,j.key''',
      'condition_events_summary':'''SELECT (absolute_day/217)+1 season,kind,json_extract(details_json,'$.reason') reason,COUNT(*) opportunities,SUM(occurred) occurred,AVG(probability) expected_probability FROM condition_events GROUP BY season,kind,reason''',
      'season_agency_records':'''SELECT m.season,t.agency_id,COUNT(*) matches,SUM(t.outcome='win') wins,SUM(t.outcome='loss') losses,SUM(t.points) regular_points FROM match_team_stats t JOIN scheduled_matches m ON m.id=t.match_id GROUP BY m.season,t.agency_id''',
      'annual_population':'''SELECT intake_season,COUNT(*) newcomers,SUM(initial_age BETWEEN 14 AND 16) minors FROM annual_entries GROUP BY intake_season''',
    }
    export_errors=[]
    for name,sql in exports.items():
        try:csvfile(folder/(name+'.csv'),rows(sql))
        except sqlite3.Error as e:export_errors.append(name+': '+str(e))
    # Exact pre-match health comes from frozen inputs; no present-day health is
    # substituted for a historical observation. Daily rest risks remain separate.
    health={}
    for row in c.execute('SELECT match_id,input_json FROM match_runs'):
        for team in json.loads(row['input_json'])['teams']:
            for p in team['players']:health[row['match_id'],p['id']]=p['health']
    bands={}
    for r in c.execute("SELECT * FROM condition_events WHERE kind='match'"):
        detail=json.loads(r['details_json']);v=health.get((detail.get('match_id'),r['person_id']))
        band='not_captured_special_or_postseason' if v is None else f'{int(v)//10*10}~{min(90,int(v)//10*10+9)}'
        b=bands.setdefault(band,dict(health_band=band,opportunities=0,injuries=0));b['opportunities']+=1;b['injuries']+=r['occurred']
    for b in bands.values():b['observed_rate']=b['injuries']/b['opportunities']
    csvfile(folder/'injury_health_bands.csv',list(bands.values()))
    seasons=rows('SELECT season,status,champion_id FROM season_finals ORDER BY season')
    checks=[schedule_audit(c,s['season']) for s in seasons]
    faults=quick_audit(c)
    finances=list(__import__('csv').DictReader((folder/'financial_statistics.csv').open(encoding='utf-8-sig')))
    complete_cash=[int(r['end_cash']) for r in finances if r['season']=='1' and r['end_cash']]
    rookie=rows('SELECT debut_season,COUNT(*) players FROM market_careers GROUP BY debut_season')
    unmature=rows('''SELECT COUNT(*) players FROM market_draft_outcomes o JOIN roster_memberships r ON r.person_id=o.person_id WHERE o.season=1 AND o.picked=0 AND r.agency_id IS NULL''')
    marker=json.loads((folder/'run_manifest.json').read_text(encoding='utf8'))
    photos=sorted(p for p in (ROOT/'assets/idols').rglob('*') if p.is_file())
    digest=hashlib.sha256(''.join(str(p.relative_to(ROOT))+':'+hashlib.sha256(p.read_bytes()).hexdigest() for p in photos).encode()).hexdigest()
    protection=dict(original_save_opened_writable=False,diagnostic_database=str(folder/'simulation.sqlite3'),photos_unchanged=digest==marker['photo_manifest_digest'],photo_files=len(photos))
    dump(folder/'data_protection.json',protection)
    dump(folder/'analysis_details.json',dict(schedule=checks,integrity=faults,finals=seasons,rookie_debuts=rookie,unassigned_unpicked=unmature,export_errors=export_errors))
    report=f'''# 25차 실제 엔진 시뮬레이션 결과

## 실행 범위와 결론
시드 {summary['seed']}. 신규 테스트 게임으로 최초 드래프트 160명과 편성을 수행했다.
**1시즌 완주 PASS**, 시즌 2 정규 585경기와 특별전·포스트시즌까지 처리했으나 **absolute_day=405에서 FAIL / 안전 중단**했다.
정규 총 {summary['actual_matches']}경기. 3시즌 목표는 미완료이며 5·10·20시즌은 NOT TESTED.
첫 실행 약 72초, 확장 실행 약 72초. 전체 테스트를 다시 시작하지 않았다.

## 시스템별 판정
추가 핵심 자동 테스트 7개 PASS: 실제 저장 경로 차단, 시드/RNG 체크포인트 복원,
PA 조회 차단, 시간 예산 중단 체크포인트, 2개 시즌 일정 및 무결성,
완료 경기 재호출/이벤트 동일성, 신인상 후보 없음의 중단 재현.
`python -m unittest tests.test_simulation25 -v` 실행 결과 7/7 통과(약 0.31초).
이는 전체 기존 테스트 스위트나 GUI 관전/스킵 버튼 검증을 대신하지 않는다.
- PASS: 최초 드래프트·선수단, 시즌 1 정규 585·특별전 6·개인상 11·신규 70·연간 지명 30·시즌 2 월요일 도달.
- PASS: 시즌 1/2 대진 각각 585, 기획사 117, 쌍별 13, 콘텐츠 19/20, 더블헤더 3, 특별전 6, 동시 참가 충돌 없음. 상세 schedule 검사 참조.
- PASS: 실제 저장 데이터 CA/PA 범위, 건강 0~90, 자금 비음수, 프로/1군/2군 정원, 계약 겹침, 선수당 주요30+무작위30=60, 승점, 생일 나이+1/건강-1, 중복 성장·외래키 검사. 위반 집계 {faults}.
- PASS: 시즌 1 챔피언 yg. 시즌별 확정 상태 {seasons}.
- FAIL(P0): 시즌 2 신인왕의 유효 후보가 0명일 때 awards.decide()가 예외를 발생시켜 CalendarService.advance_day()가 비시즌 진입을 막는다. 405일 트랜잭션은 롤백되어 경기 기록은 보존된다.
- NOT TESTED: 3~5시즌 완주, 10~20시즌, 전체 회귀 스위트, GUI 관전 대 스킵 직접 비교, 전체 시즌 동일 시드 재실행 비교, 만료·강제매각·33세 은퇴의 실제 발생 경로.

## 경기 밸런스
정규 일반 판정 성공률 {summary['regular_success_rate']:.2%}, 데스매치 {summary['deathmatches']}회,
출전자 평균 CA가 상대보다 10 이상 낮은 팀의 승리 {summary['large_ca_upsets']}회.
이는 피로·결원·콘텐츠를 통제한 실험이 아니다. CA 차이만으로 인과관계를 주장하지 않는다.
콘텐츠별 팀 승률은 content_agency_statistics.csv, 실제 인원·점수 차·전력은 regular_matches.csv에 저장했다.

## 재정·성장·부상·AI
시즌 1 평균 종료 현금 {statistics.mean(complete_cash):,.0f}원(최저 {min(complete_cash):,}, 최고 {max(complete_cash):,}).
후원금 2억4천만원·시즌 보너스 10억원을 기존 서비스로 지급했다. 급여·훈련·채무는 financial_statistics.csv 원장 집계를 참조한다.
짧은 관측에서 현금이 증가했으나 장기 인플레이션은 미확정이며 재정 수치는 변경하지 않았다.
선수 CA 시작/종료·나이·건강, 능력별 증가/감소·성장 유형, 일별 신분과 판정 종류별 성장 횟수 CSV를 제공한다.
시즌 2 종료값은 미완료이므로 checkpoint 값과 확정 종료값을 구분했다. 시즌 1 종료 스냅샷은 재개 시 보존했다.
부상률 분모는 선수 수가 아닌 실제 condition_events 위험 판정 기회 수이다.
시즌1 경기 위험 3,511회 중 부상78회(2.22%), 시즌2 경기 위험3,502회 중99회(2.83%).
경기 위험에는 정규·특별전·포스트시즌의 실제 판정이 포함되며 연속 등록 주차별 기대확률도 CSV에 제공한다.
등록 주차·건강 구간·경기/1군 휴식/2군 위험을 구분했다. 일반 경기의 저장된 사전 건강을 사용하고 특별전·포스트시즌 건강 미수집 행은 명시적으로 분리했다.
연령별 부상률과 피로의 승률 인과 효과는 NOT TESTED. 현재 건강으로 과거 건강을 추정하지 않았다.
관측 코호트에서 실제 28세 이상 노화 적용 여부는 별도 확인하지 못했으므로 27세 이하 감소 0건만으로 전체 노화를 PASS로 간주하지 않는다.
테스트 플레이어 ADOR는 공개 CA·건강·등록주차 기반 주간 교체, 나머지 9곳은 기존 AI를 그대로 사용했다.
AI에는 정기 위험 회피 로테이션이 없고 결원 보충 중심이므로 장기 고정 등록 위험이 있다(P2). 기본 AI는 변경하지 않았다.
공개 정책 구간은 SQLite authorizer로 PA·성장유형·annual_secrets 조회를 거부한다.

## 문제와 다음 개발 권고
1. P0 미수정: 신인상 후보 부재 시 시즌 진행 중단. season2 데뷔 집계 {rookie}. 최초 프로 160명의 계약이 미정으로 유지되고 신규 드래프트가 연습생 중심이어서 실제 새 프로 데뷔가 없을 수 있다. 후보 없음에 대한 수상 공석 정책이 확정되지 않아 임의 수상자를 만들거나 기존 선수 자격을 바꾸지 않았다. 다음 수정에서 공석 저장/UI/11종 무결성의 일관된 규칙 확정이 필요하다.
2. P1 연결 점검 필요: annual_draft.sync_session()는 결과 원장만 기록하며 market_service.record_draft_outcome()의 2회 미지명 은퇴 처리를 호출하지 않는다. 이번 실행은 시즌2 드래프트 전에 중단되어 2년 은퇴 발생 검증은 NOT TESTED. 존재하지 않는 은퇴를 통계에 넣지 않았다.
3. P2: 9개 AI 정기 휴식 로테이션 부재, 자금 증가 추세. 확률·후원금·승률을 보정하지 않았다.
4. P3: 일부 위험 기록의 역사적 건강/나이가 없어 교차분석 제한. 향후 위험 판정 시 공개 입력 스냅샷 저장 권고.
현재 사진 {len(photos)}개로 신규 등장 중복 없이 70명씩 공급하면 3시즌 이후 공급이 부족할 수 있다. 임의 인물을 생성하지 않는다.

## 재현·재개·데이터 보호
tools/simulate_game.py --output diagnostics/25_seed250029 --seed 250029 --seasons 3 --budget-seconds 280 --resume
현재 버그가 해결되기 전 재개하면 같은 위치에서 중단된다. DB·체크포인트를 삭제하지 말 것.
체크포인트는 공식 트랜잭션 경계의 DB와 entropy/UUID/달력 RNG 상태를 보존한다. 강제 프로세스 종료 직후의 RNG 원자성까지 보장하는 복구 도구는 아니다.
동일 코드·설정·사진·정책이 재현 조건이다. wall-clock 생성 시간은 동일성 비교 대상에서 제외한다.
실제 세이브는 쓰기 연결하지 않았고 테스트 DB만 진행했다. 아이돌 사진 해시 동일: {protection['photos_unchanged']}.
UI·DB 스키마·확률·실제 게임 서비스의 변경은 없다. 리포트의 PASS는 실제 검사한 범위에 한정한다.
'''
    (folder/'분석_보고서.md').write_text(report,encoding='utf8');c.close()
    return export_errors

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);a=p.parse_args();print(analyze(a.folder))
