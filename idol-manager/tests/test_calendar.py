from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import json
import random
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from idol_manager.agencies import AGENCY_SEEDS, INITIAL_FUNDS_KRW
from idol_manager.calendar_service import CalendarError, CalendarService
from idol_manager.config import ROOT, SKILLS, load_settings
from idol_manager.database import Database
from idol_manager.domain import Person
from idol_manager.game_clock import GameDate, is_monday
from idol_manager.migrations import V1_STATEMENTS,V2_STATEMENTS,V3_STATEMENTS,V3_PLAYER_STATEMENTS,V4_STATEMENTS,V5_STATEMENTS
from idol_manager.season_schedule import SPECIAL_TYPES, ScheduleError, create_season_plan, load_schedule_rules, validate_season_plan
from tests.game_fixtures import complete_initial_setup


class GameDateTests(unittest.TestCase):
    def test_shared_monday_rule_including_absolute_day_zero(self):
        from idol_manager import squads
        from idol_manager.ui import squad_page
        self.assertIs(squads.is_monday,is_monday)
        self.assertIs(squad_page.is_monday,is_monday)
        self.assertFalse(is_monday(None))
        for absolute in (0,1,6,7,168,196):
            self.assertEqual(is_monday(GameDate(absolute)),absolute in (0,7,168,196))

    def test_start_weekdays_week_changes_and_both_season_boundaries(self):
        cases={0:"시즌 1 · 정규 1주차 · 월요일",1:"시즌 1 · 정규 1주차 · 화요일",
               6:"시즌 1 · 정규 1주차 · 일요일",7:"시즌 1 · 정규 2주차 · 월요일",
               167:"시즌 1 · 정규 24주차 · 일요일",168:"시즌 1 · 포스트시즌 1주차 · 월요일",
               188:"시즌 1 · 포스트시즌 3주차 · 일요일",189:"시즌 1 · 비시즌 1주차 · 월요일",
               216:"시즌 1 · 비시즌 4주차 · 일요일",217:"시즌 2 · 정규 1주차 · 월요일",
               434:"시즌 3 · 정규 1주차 · 월요일",298:"시즌 2 · 정규 12주차 · 금요일",
               1062:"시즌 5 · 비시즌 1주차 · 토요일"}
        for number,expected in cases.items():
            self.assertEqual(str(GameDate(number)),expected)
            self.assertEqual(GameDate(number).after(),GameDate(number+1))
        self.assertEqual([GameDate(i).weekday() for i in range(7)],list(range(7)))
        for invalid in (-8,True,1.5):
            with self.assertRaises(ValueError):
                GameDate(invalid)


class SeasonPlanTests(unittest.TestCase):
    def test_exact_confirmed_catalog_matches_design_chapter_six(self):
        rules=load_schedule_rules()
        source=(ROOT/"docs/IDOL_Manager_기획서_2026-10-26.txt").read_text(encoding="utf-8-sig")
        section=source.split("6. 30종 정규 콘텐츠 [확정]",1)[1].split("7. 정규 경기 판정 시스템",1)[0]
        expected=[]
        for line in section.splitlines():
            match=re.match(r'^\s*(\d+)\s+(.+?)\s{2,}(.+?)\s{2,}(\d+)(?:~(\d+))?명\s*$',line)
            if match:
                number,name,abilities,low,high=match.groups()
                expected.append((name.strip(),tuple(abilities.strip().split('/')),int(low),int(high or low)))
        self.assertEqual(len(expected),30)
        self.assertEqual([(c.name,c.main_abilities,c.participants_min,c.participants_max) for c in rules.contents],expected)

    def test_585_matches_117_each_13_each_pair_three_doubleheaders_and_content_counts(self):
        agencies=[a[0] for a in AGENCY_SEEDS]
        for seed in (1,7,42):
            plan=create_season_plan(1,agencies,load_schedule_rules(),random.Random(seed))
            validate_season_plan(plan,agencies)
            self.assertEqual(len(plan.regular),585)
            self.assertEqual(Counter(a for m in plan.regular for a in m.agencies),{a:117 for a in agencies})
            self.assertEqual(Counter(Counter(tuple(sorted(m.agencies)) for m in plan.regular).values()),{13:45})
            day_counts=Counter((m.week,m.weekday) for m in plan.regular)
            self.assertEqual(Counter(day_counts.values()),{5:111,10:3})
            self.assertEqual(Counter(Counter(m.content.id for m in plan.regular).values()),{19:15,20:15})
            self.assertTrue(all(m.week>=21 for m in plan.regular if m.content.name=="연말시상식"))
            self.assertTrue(all(m.weekday>=2 and not(m.weekday==6 and m.week in (4,8,12,16,20,24)) for m in plan.regular))
            self.assertEqual([e.week for e in plan.special],[4,8,12,16,20,24])
            self.assertTrue(all(e.event_type in SPECIAL_TYPES for e in plan.special))

    def test_doubleheaders_can_cluster_and_special_types_repeat_independently(self):
        class ClusterRandom(random.Random):
            def sample(self,population,k,**kwargs):
                if k==3 and isinstance(population[0],tuple):
                    return list(population[:3])
                return super().sample(population,k,**kwargs)
            def choice(self,sequence):
                return sequence[0]
        plan=create_season_plan(2,[a[0] for a in AGENCY_SEEDS],load_schedule_rules(),ClusterRandom(1))
        counts=Counter((m.week,m.weekday) for m in plan.regular)
        self.assertEqual({day for day,count in counts.items() if count==10},{(1,2),(1,3),(1,4)})
        self.assertEqual({e.event_type for e in plan.special},{SPECIAL_TYPES[0]})

    def test_duplicate_participant_same_order_and_duplicate_ids_are_rejected(self):
        agencies=[a[0] for a in AGENCY_SEEDS]
        plan=create_season_plan(1,agencies,load_schedule_rules(),random.Random(8))
        rows=list(plan.regular)
        rows[1]=replace(rows[1],agencies=rows[0].agencies)
        with self.assertRaises(ScheduleError):
            validate_season_plan(replace(plan,regular=tuple(rows)),agencies)
        rows=list(plan.regular); rows[1]=replace(rows[1],id=rows[0].id)
        with self.assertRaises(ScheduleError):
            validate_season_plan(replace(plan,regular=tuple(rows)),agencies)


class CalendarServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="idol_calendar_")
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"한글 날짜.sqlite3"
        self.database=Database(self.path)
        people=tuple(Person(f"p{i}",f"인물{i}",f"인물{i}",f"assets/idols/{i}.png") for i in range(200))
        self.database.create_game(people,load_settings(),random.Random(2))
        complete_initial_setup(self.database)
        self.calendar=CalendarService(self.database,rng=random.Random(123))

    def dump(self):
        with closing(self.database.connect()) as connection:
            return list(connection.iterdump())

    def schedule_rows(self):
        with closing(self.database.connect()) as connection:
            return {table:sorted(tuple(r) for r in connection.execute(f"SELECT * FROM {table}")) for table in
                    ("season_schedules","scheduled_matches","match_participants","special_events")}

    def test_persisted_schedule_once_unchanged_after_reopen_or_config_change(self):
        self.calendar.ensure_current_schedule()
        before=self.schedule_rows()
        reopened=CalendarService(Database(self.path),rules_path=Path(self.temp.name)/"missing.json")
        reopened.ensure_current_schedule()
        self.assertEqual(before,self.schedule_rows())
        self.assertEqual(reopened.state().date,GameDate(0))
        code="""
from pathlib import Path
import sys
from idol_manager.database import Database
from idol_manager.calendar_service import CalendarService
c=CalendarService(Database(Path(sys.argv[1])))
c.ensure_current_schedule()
assert c.state().date.absolute_day==0
assert len(c.entries(1))==591
"""
        result=subprocess.run([sys.executable,"-c",code,str(self.path)],cwd=ROOT,capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(before,self.schedule_rows())

    def test_advance_to_wednesday_then_block_without_marking_matches_complete(self):
        self.calendar.ensure_current_schedule()
        self.assertEqual(self.calendar.advance_day(expected_absolute_day=0),GameDate(1))
        self.assertEqual(self.calendar.advance_day(expected_absolute_day=1),GameDate(2))
        state=self.calendar.state()
        self.assertIn(state.unprocessed_count,(5,10))
        before=self.dump()
        with self.assertRaisesRegex(CalendarError,"미처리"):
            self.calendar.advance_day(expected_absolute_day=2)
        self.assertEqual(before,self.dump())
        with closing(self.database.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM scheduled_matches WHERE status!='scheduled'").fetchone()[0],0)
        self.assertEqual(CalendarService(Database(self.path)).state().date,GameDate(2))

    def test_same_day_order_conflict_is_rejected_by_sqlite(self):
        self.calendar.ensure_current_schedule()
        with closing(self.database.connect()) as connection:
            row=connection.execute("SELECT id,season,week,weekday,day_order FROM scheduled_matches ORDER BY match_order LIMIT 1").fetchone()
            other=connection.execute("SELECT agency_id FROM match_participants WHERE match_id!=? AND season=? AND week=? AND weekday=? AND day_order=? LIMIT 1",tuple(row)).fetchone()[0]
            with self.assertRaises(sqlite3.IntegrityError),connection:
                connection.execute("INSERT INTO match_participants VALUES (?,?,?,?,?,?)",(row[0],other,*tuple(row)[1:]))
        self.assertEqual(len(self.calendar.entries(1)),591)

    def test_matchday_headcount_draw_once_shared_and_future_week_not_revealed(self):
        self.calendar.ensure_current_schedule()
        with closing(self.database.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM scheduled_matches WHERE required_participants IS NOT NULL").fetchone()[0],0)
        self.assertTrue(all(e.published for e in self.calendar.entries(1,week=1)))
        future=[e for e in self.calendar.entries(1,week=2) if e.match_type=="정규"]
        self.assertTrue(all(not e.published and e.content=="월요일 공개 예정" for e in future))
        self.calendar.advance_day(expected_absolute_day=0)
        self.calendar.advance_day(expected_absolute_day=1)
        with closing(self.database.connect()) as connection:
            drawn=connection.execute("SELECT id,required_participants,participants_min,participants_max FROM scheduled_matches WHERE required_participants IS NOT NULL").fetchall()
            self.assertTrue(all(r[2]<=r[1]<=r[3] for r in drawn))
            self.assertIn(len(drawn),(5,10))
            self.assertTrue(all(connection.execute("SELECT COUNT(*) FROM match_participants WHERE match_id=?",(r[0],)).fetchone()[0]==2 for r in drawn))
        before=self.schedule_rows()
        CalendarService(Database(self.path),rng=random.Random(999)).ensure_current_schedule()
        self.assertEqual(before,self.schedule_rows())
        with closing(self.database.connect()) as connection:
            with self.assertRaises(sqlite3.IntegrityError),connection:
                connection.execute("UPDATE scheduled_matches SET required_participants=NULL WHERE id=?",(drawn[0][0],))

    def test_unprocessed_special_event_blocks_day(self):
        self.calendar.ensure_current_schedule()
        with closing(self.database.connect()) as connection,connection:
            # Temporary test fixtures stand in for a future match engine; no production completion API exists.
            connection.execute("UPDATE scheduled_matches SET status='completed'")
            connection.execute("UPDATE game_clock SET absolute_day=27")
        before=self.dump()
        with self.assertRaisesRegex(CalendarError,"미처리"):
            self.calendar.advance_day(expected_absolute_day=27)
        self.assertEqual(before,self.dump())

    def test_217_persisted_day_transitions_preserve_people_and_reconcile_finance(self):
        # Reuse the actual-engine 26 QA run. The old fixture marked 585 games
        # complete without results and could no longer satisfy award/intake gates.
        source=ROOT/'diagnostics/26_seed_a/simulation.sqlite3'
        if not source.exists():self.skipTest('실제 엔진 217일 통합 실행 자료가 없음')
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as connection:
            self.assertEqual(connection.execute('SELECT absolute_day FROM game_clock').fetchone()[0],217)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM match_results').fetchone()[0],585)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM scheduled_matches WHERE season=2').fetchone()[0],585)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM annual_entries').fetchone()[0],70)
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertFalse(connection.execute('PRAGMA foreign_key_check').fetchall())
            for agency,balance in connection.execute('SELECT id,funds_krw FROM agencies'):
                delta=connection.execute('SELECT COALESCE(SUM(cash_delta),0) FROM finance_ledger WHERE agency_id=?',(agency,)).fetchone()[0]
                self.assertEqual(balance,1000000000+delta)

    def test_stale_day_request_and_schedule_rewriting_are_rejected(self):
        self.calendar.ensure_current_schedule()
        self.calendar.advance_day(expected_absolute_day=0)
        before=self.dump()
        with self.assertRaisesRegex(CalendarError,"다른 창"):
            self.calendar.advance_day(expected_absolute_day=0)
        self.assertEqual(before,self.dump())
        with closing(self.database.connect()) as connection:
            with self.assertRaises(sqlite3.IntegrityError),connection:
                connection.execute("UPDATE scheduled_matches SET week=24 WHERE match_order=1")
            with self.assertRaises(sqlite3.IntegrityError),connection:
                connection.execute("UPDATE special_events SET event_type='대학축제'")

    def test_schedule_generation_failure_rolls_back_every_schedule_table(self):
        with closing(self.database.connect()) as connection,connection:
            connection.execute("""CREATE TRIGGER fixture_failure BEFORE INSERT ON scheduled_matches
                WHEN NEW.match_order=300 BEGIN SELECT RAISE(ABORT,'failure'); END""")
        before=self.dump()
        with self.assertRaises(sqlite3.IntegrityError):
            self.calendar.ensure_current_schedule()
        self.assertEqual(before,self.dump())
        with closing(self.database.connect()) as connection:
            for table in ("season_schedules","scheduled_matches","match_participants","special_events"):
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],0)

    def test_failed_day_write_rolls_back_next_season_and_date(self):
        self.calendar.ensure_current_schedule()
        with closing(self.database.connect()) as connection,connection:
            connection.execute("UPDATE scheduled_matches SET status='completed'")
            connection.execute("UPDATE special_events SET status='completed'")
            connection.execute("UPDATE game_clock SET absolute_day=195")
            connection.execute("""CREATE TRIGGER fixture_day_failure BEFORE UPDATE ON game_clock
                BEGIN SELECT RAISE(ABORT,'failure'); END""")
        before=self.dump()
        with self.assertRaises(sqlite3.IntegrityError),patch.object(self.calendar,'_annual_issue',return_value=''):
            self.calendar.advance_day(expected_absolute_day=195)
        self.assertEqual(before,self.dump())
        self.assertEqual(self.calendar.state().date,GameDate(195))

    def test_concurrent_generation_and_same_day_requests_do_not_duplicate_or_skip(self):
        def initialize(_):
            CalendarService(Database(self.path)).ensure_current_schedule()
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(initialize,range(2)))
        self.assertEqual(len(self.calendar.entries(1)),591)
        def advance(_):
            try:
                CalendarService(Database(self.path)).advance_day(expected_absolute_day=0)
                return "advanced"
            except CalendarError:
                return "rejected"
        before=self.schedule_rows()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(advance,range(2)))
        self.assertEqual(sorted(results),["advanced","rejected"])
        self.assertEqual(self.calendar.state().date,GameDate(1))
        self.assertEqual(before,self.schedule_rows())

    def test_missing_rules_and_incomplete_persisted_season_fail_closed(self):
        missing=CalendarService(self.database,rules_path=Path(self.temp.name)/"missing.json")
        before=self.dump()
        missing.initialize()
        self.assertFalse(missing.state().schedule_ready)
        with self.assertRaises(CalendarError):
            missing.advance_day(expected_absolute_day=0)
        self.assertEqual(before,self.dump())
        self.calendar.ensure_current_schedule()
        with closing(self.database.connect()) as connection,connection:
            connection.execute("DELETE FROM scheduled_matches WHERE match_order=1")
        before=self.dump()
        with self.assertRaisesRegex(CalendarError,"불완전"):
            self.calendar.advance_day(expected_absolute_day=0)
        self.assertEqual(before,self.dump())


class CalendarMigrationTests(unittest.TestCase):
    def legacy(self,path,weekday_date="2026-10-26"):
        with closing(sqlite3.connect(path)) as connection,connection:
            connection.execute("PRAGMA foreign_keys=ON")
            for statement in V1_STATEMENTS+V2_STATEMENTS+V3_STATEMENTS+V3_PLAYER_STATEMENTS+V4_STATEMENTS:
                connection.execute(statement)
            connection.executemany("INSERT INTO agencies VALUES (?,?,?,?)",[(*a,INITIAL_FUNDS_KRW) for a in AGENCY_SEEDS])
            connection.execute("INSERT INTO game(id) VALUES (1)")
            connection.execute("INSERT INTO game_clock VALUES (1,'2026-10-26')")
            connection.execute("INSERT INTO player_settings(game_id,agency_id) VALUES (1,'ador')")
            for number in (1,2):
                person=f"legacy-{number}"
                connection.execute("INSERT INTO people VALUES (?,?,?,?)",(person,f"기존{number}",f"기존{number}",f"assets/idols/기존{number}.png"))
                connection.execute("INSERT INTO idols VALUES (?,22,83,'specialist',50,'candidate')",(person,))
                connection.executemany("INSERT INTO abilities VALUES (?,?,50,95)",[(person,s) for s in SKILLS])
                connection.execute("INSERT INTO initial_draft_candidates VALUES (?)",(person,))
                connection.execute("INSERT INTO roster_memberships VALUES (?,NULL,'unassigned')",(person,))
            connection.execute("INSERT INTO draft_state(id,status) VALUES (1,'in_progress')")
            for number,agency,squad in ((1,"ador","first_team"),(2,"sm","second_team")):
                person=f"legacy-{number}"
                connection.execute("INSERT INTO draft_turns(pick_number,round_number,position,agency_id) VALUES (?,1,?,?)",(number,number,agency))
                connection.execute("INSERT INTO draft_picks(pick_number,person_id) VALUES (?,?)",(number,person))
                connection.execute("UPDATE roster_memberships SET career_status=? WHERE person_id=?",(squad,person))
                connection.execute("INSERT INTO squad_formations(agency_id,revision) VALUES (?,7)",(agency,))
                connection.execute("INSERT INTO squad_leaders VALUES (?,?,?)",(agency,squad,person))
            connection.execute("UPDATE agencies SET funds_krw=123456789 WHERE id='ador'")
            connection.execute("UPDATE game_clock SET management_date=?",(weekday_date,))
            connection.execute("PRAGMA user_version=4")

    def test_legacy_clock_weekday_conversion_backup_and_all_other_rows_preserved(self):
        for old_date,expected in (("2026-10-26",0),("2026-10-27",1)):
            with self.subTest(old_date=old_date),tempfile.TemporaryDirectory() as temp:
                path=Path(temp)/"legacy.sqlite3"; self.legacy(path,old_date)
                def protected():
                    with closing(sqlite3.connect(path)) as connection:
                        tables=[r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'") if r[0] not in ("game_clock","legacy_game_clock","season_schedules","scheduled_matches","match_participants","special_events",
                            "match_runs","match_results","match_team_stats","match_player_stats","match_ability_stats","match_events",
                            "condition_events","appearance_days","player_conditions","condition_day_runs","condition_runtime",
                            "special_sessions","special_rounds","special_team_results","special_player_stats","special_ability_stats","special_judgments","special_points","draft_estimates",
                            "season_finals","final_contests","final_series","season_honors","calendar_v9_archive",
                            "development_runtime","development_days","development_settlements","development_results","development_trials",
                            "finance_runtime","finance_contracts","finance_settlements","finance_ledger","finance_payroll","finance_debts","finance_points",
                            "market_runtime","market_terms","market_careers","market_days","market_negotiations","market_offers","market_auctions","market_bids","market_trades","market_trade_versions","market_history","market_release_plans","market_installments","market_draft_rights","market_draft_outcomes")]
                        return {t:sorted(connection.execute(f"SELECT * FROM {t}").fetchall()) for t in tables}
                before=protected()
                database=Database(path)
                self.assertIsNotNone(database.last_backup_path)
                after=protected()
                self.assertEqual(before,{t:after[t] for t in before})
                with closing(database.connect()) as connection:
                    self.assertEqual(connection.execute("SELECT absolute_day FROM game_clock").fetchone()[0],expected)
                    self.assertEqual(tuple(connection.execute("SELECT * FROM legacy_game_clock").fetchone()),(1,old_date,expected))
                    self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(),[])
                with closing(sqlite3.connect(database.last_backup_path)) as backup:
                    self.assertEqual(backup.execute("SELECT management_date FROM game_clock").fetchone()[0],old_date)

    def test_migration_failure_preserves_original_clock_schema_leaders_and_version(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"legacy.sqlite3"; self.legacy(path)
            with closing(sqlite3.connect(path)) as connection:
                before=list(connection.iterdump())
            with patch("idol_manager.migrations.V5_STATEMENTS",V5_STATEMENTS+("INVALID SQL",)):
                with self.assertRaises(sqlite3.OperationalError):
                    Database(path)
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(list(connection.iterdump()),before)
                self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0],4)


if __name__=="__main__":
    unittest.main()
