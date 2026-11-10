"""Initial-game prerequisites and explicitly approved, date-only recovery."""
from contextlib import closing
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .agencies import INITIAL_FUNDS_KRW
from .game_clock import GameDate, current_game_date
from .migrations import backup_database


def initial_setup_reason(connection):
    from .founding import waiting,contract_reason
    if waiting(connection):
        reason=contract_reason(connection)
        if reason:return reason
    draft = connection.execute('SELECT status FROM draft_state WHERE id=1').fetchone()
    if not draft or draft[0] != 'completed':
        return '최초 드래프트를 완료한 뒤 날짜를 진행할 수 있습니다.'
    counts = connection.execute('''SELECT a.id,COUNT(p.person_id) FROM agencies a
        LEFT JOIN draft_turns t ON t.agency_id=a.id LEFT JOIN draft_picks p ON p.pick_number=t.pick_number
        GROUP BY a.id''').fetchall()
    if len(counts) != 10 or any(r[1] != 16 for r in counts):
        return '드래프트 160명 지명 기록을 확인해야 합니다. 날짜를 진행하지 않습니다.'
    player = connection.execute('SELECT agency_id FROM player_settings WHERE game_id=1').fetchone()
    if player is None:
        return '플레이어 기획사를 먼저 선택해 주세요.'
    if not connection.execute('SELECT 1 FROM squad_formations WHERE agency_id=?',(player[0],)).fetchone():
        return '플레이어 최초 선수단 편성이 완료되지 않았습니다. 월요일에 1군 5명·2군 11명을 편성하고 1군·2군 리더를 지정해 주세요.'
    if connection.execute('SELECT COUNT(*) FROM squad_formations').fetchone()[0] != 10 or connection.execute(
            "SELECT 1 FROM roster_memberships WHERE career_status='pro_pending' LIMIT 1").fetchone():
        return 'AI 기획사를 포함한 최초 선수단 편성을 모두 완료해야 합니다.'
    day=current_game_date(connection)
    if day and not day.is_regular and not day.is_postseason:
        # Expiring contracts can empty squads before the FA week. Do not turn
        # the first-game leader gate into an offseason market deadlock.
        return ''
    leaders = {r[0] for r in connection.execute('''SELECT l.squad FROM squad_leaders l
        JOIN roster_memberships r ON r.person_id=l.person_id AND r.agency_id=l.agency_id AND r.career_status=l.squad
        WHERE l.agency_id=?''',(player[0],))}
    missing = [label for squad,label in (('first_team','1군'),('second_team','2군')) if squad not in leaders]
    if missing:
        return '플레이어 ' + '·'.join(missing) + ' 리더를 지정한 뒤 날짜를 진행해 주세요.'
    return ''


class InitialRecoveryError(ValueError):
    pass


@dataclass(frozen=True)
class InitialRecoveryStatus:
    allowed: bool
    reason: str
    absolute_day: int | None
    revision: int
    token: str = ''


@dataclass(frozen=True)
class InitialRecoveryResult:
    backup_path: Path
    previous_absolute_day: int
    date: GameDate


# Fail closed if future financial/settlement/progression tables are introduced.
KNOWN_TABLES = frozenset(('ai_trade_checks','ai_trade_windows','ai_trade_messages','trainee_rounds','founding_setup','founding_contracts','trainee_rng','trainee_weeks','trainee_sheets','trainee_applications','trainee_results','trainee_submission_keys','annual_assets','annual_runtime','annual_intakes','annual_entries','annual_secrets','annual_sessions','annual_turns','annual_pool',
    'award_regular_rosters','award_match_selections','season_awards','individual_awards','award_outcomes',
    'people','game','idols','abilities','agencies','initial_draft_candidates',
    'roster_memberships','draft_state','draft_turns','draft_picks','draft_age_corrections','player_settings',
    'squad_formations','professional_history','squad_leaders','legacy_game_clock','game_clock',
    'season_schedules','scheduled_matches','match_participants','special_events','match_runs','match_results',
    'match_team_stats','match_player_stats','match_ability_stats','match_events',
    'condition_runtime','player_conditions','appearance_days','condition_events','condition_day_runs',
    'special_sessions','special_rounds','special_team_results','special_player_stats','special_ability_stats','special_judgments','special_points','draft_estimates',
    'season_finals','final_series','final_contests','season_honors','calendar_v9_archive',
    'development_runtime','development_days','development_settlements','development_results','development_trials',
    'finance_runtime','finance_contracts','finance_settlements','finance_ledger','finance_payroll','finance_debts','finance_points',
    'market_runtime','market_terms','market_careers','market_days','market_negotiations','market_offers','market_auctions','market_bids','market_trades','market_trade_versions','market_history','market_release_plans','market_installments','market_draft_rights','market_draft_outcomes'))
RESULT_TABLES = ('match_runs','match_results','match_team_stats','match_player_stats','match_ability_stats','match_events',
                 'special_sessions','special_rounds','special_team_results','special_player_stats','special_ability_stats','special_judgments','special_points',
                 'development_settlements','development_results','development_trials')


def _fingerprint(connection,*,original_clock=None):
    digest = hashlib.sha256()
    for table in sorted(KNOWN_TABLES):
        rows = ([original_clock] if table=='game_clock' and original_clock is not None else
                sorted(tuple(r) for r in connection.execute(f'SELECT * FROM "{table}"')))
        digest.update(json.dumps([table,rows],ensure_ascii=False,sort_keys=True).encode('utf-8'))
    return digest.hexdigest()


class InitialDateRecovery:
    def __init__(self,database):
        self.database = database

    @staticmethod
    def _inspect(connection):
        day = current_game_date(connection)
        clock = connection.execute('SELECT revision FROM game_clock WHERE game_id=1').fetchone()
        absolute,revision = (day.absolute_day if day is not None else None), (clock[0] if clock else 0)

        def reject(reason):
            return InitialRecoveryStatus(False,reason,absolute,revision)

        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        from .migrations import SCHEMA_VERSION
        if connection.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION or tables != KNOWN_TABLES:
            return reject('지원하지 않는 저장 구조·추가 진행 기록이 있어 안전한 초기 날짜 복구를 판단할 수 없습니다.')
        if connection.execute("SELECT 1 FROM finance_settlements WHERE kind!='opening' LIMIT 1").fetchone():
            return reject('재정 정산 기록이 있어 초기 날짜를 강제로 되돌리지 않습니다.')
        from .founding import waiting
        if waiting(connection) or connection.execute("SELECT 1 FROM trainee_weeks WHERE status='finalized'").fetchone():
            return reject('창단 준비 또는 연습생 추첨 기록이 있어 초기 날짜를 되돌리지 않습니다.')
        if day is None or absolute <= 7:
            return reject('이미 최초 월요일이거나 저장된 게임 날짜가 없습니다.')
        if day.season != 1:
            return reject('다음 시즌 진행 기록이 있어 초기 날짜로 자동 복구할 수 없습니다.')
        draft = connection.execute('SELECT status FROM draft_state WHERE id=1').fetchone()
        if not draft or draft[0] != 'completed' or connection.execute('SELECT COUNT(*) FROM draft_picks').fetchone()[0] != 160:
            return reject('최초 드래프트 160명 지명이 완료된 저장에서만 초기 날짜를 복구할 수 있습니다.')
        if not connection.execute('SELECT 1 FROM player_settings WHERE game_id=1').fetchone():
            return reject('플레이어 기획사 정보가 없습니다.')
        if connection.execute('SELECT 1 FROM squad_formations LIMIT 1').fetchone() or connection.execute('SELECT 1 FROM squad_leaders LIMIT 1').fetchone():
            return reject('이미 선수단 편성 또는 리더 지정 기록이 있어 날짜를 강제로 되돌리지 않습니다.')
        if any(connection.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone() for table in RESULT_TABLES):
            return reject('경기 준비·진행·결과 기록이 있어 초기 날짜 복구를 차단했습니다.')
        if connection.execute("SELECT 1 FROM scheduled_matches WHERE status!='scheduled' LIMIT 1").fetchone() or connection.execute(
                "SELECT 1 FROM special_events WHERE status!='scheduled' LIMIT 1").fetchone():
            return reject('정규 경기 또는 특별전 진행 기록이 있어 초기 날짜 복구를 차단했습니다.')
        if connection.execute('SELECT COUNT(*) FROM agencies').fetchone()[0] != 10 or connection.execute(
                'SELECT 1 FROM agencies WHERE funds_krw!=? LIMIT 1',(INITIAL_FUNDS_KRW,)).fetchone():
            return reject('기획사 자금 변동이 확인되어 초기 날짜 복구를 차단했습니다.')
        seasons = connection.execute('SELECT season,regular_count,special_count FROM season_schedules').fetchall()
        if [tuple(r) for r in seasons] != [(1,585,6)] or connection.execute('SELECT COUNT(*) FROM scheduled_matches WHERE season=1').fetchone()[0] != 585 or connection.execute(
                'SELECT COUNT(*) FROM special_events WHERE season=1').fetchone()[0] != 6:
            return reject('초기 585경기·특별전 6회 일정이 온전하지 않아 자동 복구할 수 없습니다.')
        counts = connection.execute('''SELECT a.id,COUNT(p.person_id) FROM agencies a
            LEFT JOIN draft_turns t ON t.agency_id=a.id LEFT JOIN draft_picks p ON p.pick_number=t.pick_number
            GROUP BY a.id''').fetchall()
        if any(r[1] != 16 for r in counts) or connection.execute('''SELECT 1 FROM draft_picks p
            JOIN draft_turns t ON t.pick_number=p.pick_number LEFT JOIN roster_memberships r ON r.person_id=p.person_id
            WHERE r.person_id IS NULL OR r.agency_id IS NOT t.agency_id OR r.career_status!='pro_pending' LIMIT 1''').fetchone():
            return reject('드래프트 지명과 편성 대기 선수의 소속 정보가 일치하지 않습니다.')
        if connection.execute('''SELECT 1 FROM roster_memberships r WHERE r.career_status NOT IN('pro_pending','unassigned')
            OR (r.career_status='pro_pending' AND NOT EXISTS(SELECT 1 FROM draft_picks p WHERE p.person_id=r.person_id)) LIMIT 1''').fetchone():
            return reject('선수 상태에 초기 편성 대기 이외의 진행 기록이 있습니다.')
        if connection.execute('PRAGMA foreign_key_check').fetchone():
            return reject('저장 데이터 참조 무결성을 먼저 확인해야 합니다.')
        # The approval covers exactly the inspected save, not a later edit/new game.
        return InitialRecoveryStatus(True,'초기 편성 전 날짜만 진행된 상태로 확인되었습니다.',absolute,revision,_fingerprint(connection))

    def status(self):
        with closing(self.database.connect()) as connection,connection:
            connection.execute('BEGIN')
            return self._inspect(connection)

    def recover(self,*,approved=False,expected_absolute_day,expected_revision,expected_token):
        if approved is not True:
            raise InitialRecoveryError('명시적으로 승인해야 백업 후 초기 날짜를 복구할 수 있습니다.')
        with closing(self.database.connect()) as connection,connection:
            connection.execute('BEGIN IMMEDIATE')
            status = self._inspect(connection)
            if not status.allowed:
                raise InitialRecoveryError(status.reason)
            if type(expected_absolute_day) is not int or type(expected_revision) is not int or (
                    status.absolute_day,status.revision,status.token) != (expected_absolute_day,expected_revision,expected_token):
                raise InitialRecoveryError('승인 화면 이후 저장 내용이 변경되었습니다. 최신 상태를 다시 확인하고 승인해 주세요.')
            # No writes precede the backup. The reserved writer lock prevents
            # concurrent mutations while a separate read-only connection backs up.
            backup = backup_database(self.database.path,label='initial_date_recovery')
            connection.execute('UPDATE game_clock SET absolute_day=7,revision=revision+1 WHERE game_id=1')
            clock = tuple(connection.execute('SELECT game_id,absolute_day,revision FROM game_clock WHERE game_id=1').fetchone())
            if clock != (1,0,status.revision+1) or _fingerprint(connection,original_clock=(1,status.absolute_day,status.revision)) != status.token:
                raise InitialRecoveryError('날짜 이외의 데이터 변경이 감지되어 복구 트랜잭션 전체를 취소했습니다. 백업은 보존했습니다.')
            return InitialRecoveryResult(backup,status.absolute_day,GameDate(7))
