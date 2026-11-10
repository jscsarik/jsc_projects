from .game_clock import regular_day
"""Persist seasons once, prepare matchday headcounts, and advance safely."""
from contextlib import closing
from dataclasses import dataclass
import json
import random

from .game_clock import GameDate, current_game_date
from .season_schedule import ScheduleError, create_season_plan, load_schedule_rules
from .initial_setup import initial_setup_reason, InitialDateRecovery, InitialRecoveryError
from .conditions import finish_day,enter_day,repair_ai_leaders


class CalendarError(ValueError):
    pass


@dataclass(frozen=True)
class CalendarState:
    date: GameDate | None
    revision: int
    schedule_ready: bool
    reason: str
    unprocessed_count: int
    advance_block_reason: str = ''


@dataclass(frozen=True)
class ScheduleEntry:
    id: str
    season: int
    week: int
    weekday: int
    day_order: int | None
    match_order: int | None
    agencies: str
    content: str
    main_abilities: str
    participants: str
    match_type: str
    status: str
    published: bool


class CalendarService:
    def __init__(self,database,*,rules_path=None,rng=None,root=None,user_asset_dir=None):
        self.database=database
        self.root=root or (database.path.parent.parent if database.path.parent.name=='data' else database.path.parent)
        self.user_asset_dir=user_asset_dir
        self.rules_path=rules_path
        self.rng=rng or random.SystemRandom()
        self.schedule_issue=""

    @staticmethod
    def _pending(connection,day):
        # Also protect overdue matches (e.g. a migrated legacy weekday).
        regular=connection.execute("""SELECT COUNT(*) FROM scheduled_matches WHERE season=?
            AND regular_day(season,week,weekday)<=? AND status!='completed'""",(day.season,day.absolute_day)).fetchone()[0]
        special=connection.execute("""SELECT COUNT(*) FROM special_events WHERE season=?
            AND regular_day(season,week,weekday)<=? AND status!='completed'""",(day.season,day.absolute_day)).fetchone()[0]
        finals=connection.execute("SELECT COUNT(*) FROM final_contests WHERE season=? AND absolute_day<=? AND status!='completed'",(day.season,day.absolute_day)).fetchone()[0]
        return regular+special+finals

    def state(self):
        with closing(self.database.connect()) as connection,connection:
            connection.execute("BEGIN")
            day=current_game_date(connection)
            if day is None:
                return CalendarState(None,0,False,"새 게임을 먼저 생성해 주세요.",0)
            revision=connection.execute("SELECT revision FROM game_clock WHERE game_id=1").fetchone()[0]
            if day.is_founding:
                from .founding import ready_reason,advance_reason,staged
                return CalendarState(day,revision,True,'',0,(advance_reason if staged(connection) else ready_reason)(connection))
            marker=connection.execute("SELECT 1 FROM season_schedules WHERE season=?",(day.season,)).fetchone()
            return CalendarState(day,revision,marker is not None,
                                 "" if marker else (self.schedule_issue or "시즌 일정 생성이 필요합니다."),
                                 self._pending(connection,day),initial_setup_reason(connection) or self._annual_issue(connection,day))

    @staticmethod
    def _annual_issue(c,day):
        if day.day_in_season==209:
            from .annual_recruitment import intake_issue
            return intake_issue(c,day.season)
        if day.day_in_season==216:
            from .annual_draft import draft_issue
            return draft_issue(c,day.season)
        return ''

    def initial_recovery_status(self):
        return InitialDateRecovery(self.database).status()

    def recover_initial_date(self,**approval):
        try:
            return InitialDateRecovery(self.database).recover(**approval)
        except InitialRecoveryError as error:
            raise CalendarError(str(error)) from error

    def _ensure_season(self,connection,season):
        from .recruitment_philosophy import ensure
        ensure(connection,season)
        row=connection.execute("SELECT regular_count,special_count FROM season_schedules WHERE season=?",(season,)).fetchone()
        if row:
            regular=connection.execute("SELECT COUNT(*) FROM scheduled_matches WHERE season=?",(season,)).fetchone()[0]
            special=connection.execute("SELECT COUNT(*) FROM special_events WHERE season=?",(season,)).fetchone()[0]
            if (regular,special)!=(row[0],row[1]):
                raise CalendarError("저장된 시즌 일정이 불완전합니다. 일정을 덮어쓰지 않고 날짜 진행을 중단합니다.")
            return
        rules=load_schedule_rules(self.rules_path)
        agencies=[r[0] for r in connection.execute("SELECT id FROM agencies ORDER BY id")]
        plan=create_season_plan(season,agencies,rules,self.rng)
        connection.execute("INSERT INTO season_schedules(season,rules_digest,rules_json,regular_count,special_count) VALUES (?,?,?,585,6)",
                           (season,rules.digest,rules.serialized))
        connection.executemany("""INSERT INTO scheduled_matches
            (id,season,week,weekday,day_order,match_order,content_id,content_name,main_abilities_json,participants_min,participants_max)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",[
                (m.id,m.season,m.week,m.weekday,m.day_order,m.match_order,m.content.id,m.content.name,
                 json.dumps(m.content.main_abilities,ensure_ascii=False),m.content.participants_min,m.content.participants_max)
                for m in plan.regular])
        connection.executemany("INSERT INTO match_participants VALUES (?,?,?,?,?,?)",[
            (m.id,agency,m.season,m.week,m.weekday,m.day_order) for m in plan.regular for agency in m.agencies])
        connection.executemany("INSERT INTO special_events(id,season,week,event_type) VALUES (?,?,?,?)",
                               [(e.id,e.season,e.week,e.event_type) for e in plan.special])

    def _prepare_day(self,connection,day):
        if not day.is_regular:
            return
        rows=connection.execute("""SELECT id,participants_min,participants_max FROM scheduled_matches
            WHERE season=? AND week=? AND weekday=? AND required_participants IS NULL ORDER BY match_order""",
                                (day.season,day.week,day.weekday())).fetchall()
        for row in rows:
            connection.execute("UPDATE scheduled_matches SET required_participants=? WHERE id=? AND required_participants IS NULL",
                               (self.rng.randint(row[1],row[2]),row[0]))

    def ensure_current_schedule(self):
        with closing(self.database.connect()) as connection,connection:
            connection.execute("BEGIN IMMEDIATE")
            day=current_game_date(connection)
            if day is None:
                return
            from .founding import waiting
            if waiting(connection):return
            self._ensure_season(connection,day.season)
            self._prepare_day(connection,day)
        self.schedule_issue=""

    def initialize(self):
        try:
            self.ensure_current_schedule()
            with closing(self.database.connect()) as c,c:
                c.execute('BEGIN IMMEDIATE')
                from .annual_recruitment import intake
                from .founding import waiting
                if not waiting(c):intake(c,self.root)
        except (ScheduleError,CalendarError) as error:
            self.schedule_issue=str(error)

    def advance_day(self,*,expected_absolute_day:int,expected_trainee_revision=None):
        if type(expected_absolute_day) is not int:
            raise CalendarError("현재 게임 날짜를 다시 확인해 주세요.")
        try:
            with closing(self.database.connect()) as connection,connection:
                connection.execute("BEGIN IMMEDIATE")
                day=current_game_date(connection)
                if day is None:
                    raise CalendarError("진행할 게임이 없습니다.")
                if day.absolute_day!=expected_absolute_day:
                    raise CalendarError("다른 창에서 날짜가 변경되었습니다. 최신 날짜를 확인한 뒤 다시 진행해 주세요.")
                if day.is_founding:
                    from .founding import ready_reason,advance_reason,staged,start_contracts
                    modern=staged(connection)
                    reason=(advance_reason if modern else ready_reason)(connection)
                    if reason:raise CalendarError(reason)
                    if modern and day.weekday() in (2,4):
                        from .trainee_recruitment import submit,round_info
                        submit(connection,round_info(connection)['key'],expected_player_revision=expected_trainee_revision)
                    elif not modern and day.weekday()==0:
                        from .trainee_recruitment import finalize
                        finalize(connection,day.absolute_day,expected_player_revision=expected_trainee_revision)
                    if day.absolute_day==6:
                        from .squad_calendar import ready_for_play
                        ready_for_play(connection)
                        connection.execute("UPDATE founding_setup SET status='completed' WHERE game_id=1")
                        connection.execute('UPDATE game_clock SET absolute_day=7 WHERE game_id=1')
                        self._ensure_season(connection,1)
                        from .conditions import sync_rosters
                        sync_rosters(connection,7,'founding_complete')
                        enter_day(connection,7);self._prepare_day(connection,day.after())
                    else:connection.execute('UPDATE founding_setup SET prep_day=prep_day+1 WHERE game_id=1')
                    if modern:
                        tomorrow=current_game_date(connection)
                        if tomorrow.absolute_day==1:start_contracts(connection)
                        if tomorrow.absolute_day in (3,5):
                            from .trainee_recruitment import finalize,round_info
                            finalize(connection,round_info(connection)['key'])
                        from .market_service import process_market
                        process_market(connection,tomorrow.absolute_day,run_ai=tomorrow.absolute_day in (3,5,7))
                    connection.execute('UPDATE game_clock SET absolute_day=?,revision=revision+1 WHERE game_id=1',(day.after().absolute_day,))
                    return day.after()
                reason = initial_setup_reason(connection) if day.is_regular or day.is_postseason else ''
                if reason:
                    raise CalendarError(reason)
                self._ensure_season(connection,day.season)
                pending=self._pending(connection,day)
                if pending:
                    raise CalendarError(f"현재 날짜 또는 이전 날짜에 미처리 경기·특별전 {pending}건이 있습니다. "
                                        "정규 경기·특별전·동률 결정전·포스트시즌의 모든 단계를 완료해 주세요. 자동으로 완료하거나 건너뛰지 않습니다.")
                tomorrow=day.after()
                if (day.is_preparation or day.is_maintenance) and day.weekday()==6:
                    from .squad_calendar import ready_for_play
                    ready_for_play(connection)
                annual_issue=self._annual_issue(connection,day)
                if annual_issue:raise CalendarError(annual_issue)
                if day.weekday()==0:
                    from .ai_trades import close_due
                    close_due(connection)
                    repair_ai_leaders(connection,day.absolute_day)
                    reason=initial_setup_reason(connection)
                    if reason:raise CalendarError('트레이드 마감 전에 이적 대상 이외의 선수로 리더를 지정해 주세요. '+reason)
                    from .trainee_recruitment import finalize
                    finalize(connection,day.absolute_day,expected_player_revision=expected_trainee_revision)
                if day.day_in_season==202:
                    from .awards import finalize
                    # Gate before offseason growth/finance/market transactions.
                    finalize(connection,day.season)
                from .training_service import close_tuesday
                close_tuesday(connection,day.absolute_day)
                from .ai_training import plan as plan_ai_training
                plan_ai_training(connection,self.root)
                finish_day(connection,day.absolute_day)
                from .development_service import advance_development
                advance_development(connection,day.absolute_day,tomorrow.absolute_day)
                from .finance_service import advance_finance
                advance_finance(connection,day.absolute_day,tomorrow.absolute_day)
                if day.day_in_season==181:
                    from .awards import capture_regular_rosters
                    capture_regular_rosters(connection,day.season)
                    from .finals_service import FinalsService
                    FinalsService.ensure_started(connection,day.season)
                if day.day_in_season==202:
                    final=connection.execute('SELECT status FROM season_finals WHERE season=?',(day.season,)).fetchone()
                    if not final or final[0]!='completed':raise CalendarError('챔피언 결정전을 완료한 뒤 비시즌으로 진행할 수 있습니다.')
                enter_day(connection,tomorrow.absolute_day)
                if tomorrow.season!=day.season:
                    from .franchise import settle
                    settle(connection,day.season)
                    self._ensure_season(connection,tomorrow.season)
                self._prepare_day(connection,tomorrow)
                connection.execute("UPDATE game_clock SET absolute_day=?,revision=revision+1 WHERE game_id=1",(tomorrow.absolute_day,))
                if tomorrow.day_in_season==203:
                    from .annual_recruitment import intake
                    intake(connection,self.root,user_asset_dir=self.user_asset_dir)
                repair_ai_leaders(connection,tomorrow.absolute_day)
                from .market_service import process_market
                process_market(connection,tomorrow.absolute_day)
                from .ai_training import plan as plan_ai_training
                plan_ai_training(connection,self.root)
                repair_ai_leaders(connection,tomorrow.absolute_day)
                return tomorrow
        except (ScheduleError,ValueError) as error:
            raise CalendarError(str(error)) from error

    def seasons(self):
        state=self.state()
        with closing(self.database.connect()) as connection:
            values={r[0] for r in connection.execute("SELECT season FROM season_schedules")}
        if state.date:
            values.add(state.date.season)
        return sorted(values) or [1]

    def entries(self,season,*,week=None,agency_id=None,current_week=False):
        if type(season) is not int or season<1 or (week is not None and (type(week) is not int or not 1<=week<=24)):
            raise CalendarError("조회할 시즌과 정규 주차를 확인해 주세요.")
        with closing(self.database.connect()) as connection,connection:
            connection.execute("BEGIN")
            day=current_game_date(connection)
            if current_week:
                if day is None or not day.is_regular or season!=day.season:
                    return ()
                week=day.week
            if agency_id and not connection.execute("SELECT 1 FROM agencies WHERE id=?",(agency_id,)).fetchone():
                raise CalendarError("존재하지 않는 기획사입니다.")
            parameters=[season]
            where="m.season=?"
            if week is not None:
                where+=" AND m.week=?"; parameters.append(week)
            if agency_id:
                where+=" AND EXISTS(SELECT 1 FROM match_participants p WHERE p.match_id=m.id AND p.agency_id=?)"
                parameters.append(agency_id)
            rows=connection.execute(f"SELECT m.* FROM scheduled_matches m WHERE {where} ORDER BY m.match_order",parameters).fetchall()
            names={}
            for row in connection.execute("""SELECT p.match_id,a.name FROM match_participants p JOIN agencies a ON a.id=p.agency_id
                WHERE p.season=? ORDER BY p.match_id,a.name""",(season,)):
                names.setdefault(row[0],[]).append(row[1])
            entries=[]
            for row in rows:
                published=bool(day and not day.is_founding and (day.season>season or (day.season==season and day.absolute_day>=regular_day(season,row['week']))))
                needed=row['required_participants']
                span=str(row['participants_min']) if row['participants_min']==row['participants_max'] else f"{row['participants_min']}~{row['participants_max']}"
                entries.append(ScheduleEntry(row['id'],season,row['week'],row['weekday'],row['day_order'],row['match_order'],
                    " vs ".join(names.get(row['id'],())) if published else "월요일 공개 예정",
                    row['content_name'] if published else "월요일 공개 예정",
                    " / ".join(json.loads(row['main_abilities_json'])) if published else "",
                    (f"{needed}명 (양측 동일)" if needed is not None else f"{span}명"+" · 당일 확정"*(row['participants_min']!=row['participants_max'])) if published else "공개 예정",
                    "정규",row['status'],published))
            special_parameters=[season]
            special_where="season=?"
            if week is not None:
                special_where+=" AND week=?"; special_parameters.append(week)
            for row in connection.execute(f"SELECT * FROM special_events WHERE {special_where} ORDER BY week",special_parameters):
                published=bool(day and not day.is_founding and (day.season>season or (day.season==season and day.absolute_day>=regular_day(season,row['week']))))
                entries.append(ScheduleEntry(row['id'],season,row['week'],6,None,None,
                    "10개 기획사 · 상위/하위 5자 및 후속 4자",row['event_type'] if published else "월요일 공개 예정","",
                    "기획사별 10명 · 후속 콘텐츠 인원 적용","특별전",row['status'],published))
            return tuple(sorted(entries,key=lambda e:(e.week,e.weekday,e.day_order or 1,e.match_order or 9999)))
