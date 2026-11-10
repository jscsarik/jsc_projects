from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
import json
import random
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from idol_manager.calendar_service import CalendarService, CalendarError
from idol_manager.config import ROOT, load_settings
from idol_manager.database import Database
from idol_manager.domain import Person
from idol_manager.draft import DraftEngine
from idol_manager.draft_session import DraftSession
from idol_manager.game_clock import GameDate
from idol_manager.match_engine import calculate_match
from idol_manager.match_schema import V6_STATEMENTS
from idol_manager.match_service import MatchService
from idol_manager.match_types import MatchError, MatchInput, UnresolvedMatch
from idol_manager.migrations import SCHEMA_VERSION
from idol_manager.squads import SquadService

MATCH_TABLES = ('match_runs','match_results','match_team_stats','match_player_stats','match_ability_stats','match_events')
MATCH_VIEWS = ('regular_standings','idol_regular_career_stats','idol_content_stats','idol_ability_stats')
PROTECTED = ('people','idols','abilities','agencies','draft_state','draft_turns','draft_picks',
             'initial_draft_candidates','player_settings','roster_memberships','squad_formations','squad_leaders')


def copy_db(source, target):
    with closing(sqlite3.connect(source)) as a, closing(sqlite3.connect(target)) as b:
        a.backup(b)


class MatchServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix='idol_match_fixture_')
        cls.addClassCleanup(cls.folder.cleanup)
        cls.template = Path(cls.folder.name)/'template.sqlite3'
        db = Database(cls.template)
        people = tuple(Person(f'p-{i}', f'가상 선수{i:03}', f'가상 선수{i:03}', f'assets/idols/{i}.png') for i in range(310))
        db.create_game(people,load_settings(),random.Random(55))
        with closing(db.connect()) as c,c:
            c.execute('UPDATE idols SET health=90') # Current persisted health ceiling.
        from tests.game_fixtures import legacy_save
        legacy_save(db)
        draft = DraftEngine(db)
        DraftSession(draft).select_agency('ador')
        draft.start(rng=random.Random(6))
        identities = [p.id for p in draft.available_candidates()[:160]]
        for number, identity in enumerate(identities,1):
            draft.pick(draft.state().next_turn.agency_id,identity,expected_pick_number=number)
        squads = SquadService(db)
        squads.confirm_initial(tuple(p.id for p in squads.snapshot().members[:5]))
        with closing(db.connect()) as connection,connection:
            # Each agency gets a valid first-team leader on the initial Monday.
            for agency in db.agencies():
                for squad in ('first_team','second_team'):
                    identity = connection.execute("SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status=? ORDER BY person_id LIMIT 1",(agency.id,squad)).fetchone()[0]
                    connection.execute("INSERT OR IGNORE INTO squad_leaders VALUES (?,?,?)",(agency.id,squad,identity))
        calendar = CalendarService(db,rng=random.Random(88))
        calendar.ensure_current_schedule()
        with patch('idol_manager.conditions.injury_probability',return_value=0):
            calendar.advance_day(expected_absolute_day=0)
            calendar.advance_day(expected_absolute_day=1)

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='idol_match_테스트_')
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)/'세이브.sqlite3'
        copy_db(self.template,self.path)
        self.db = Database(self.path)
        self.calendar = CalendarService(self.db,rng=random.Random(8))
        self.service = MatchService(self.db,seed_factory=lambda:91)
        self.match = self.rows("SELECT * FROM scheduled_matches ORDER BY match_order LIMIT 1")[0]
        self.identity = self.match['id']

    def rows(self, sql, parameters=()):
        with closing(self.db.connect()) as connection:
            return [dict(row) for row in connection.execute(sql,parameters)]

    def protected(self):
        return {t:self.rows(f'SELECT * FROM {t} ORDER BY 1') for t in PROTECTED}

    def fixture_fields(self):
        # Only status may change during match play; fixed headcounts are included.
        return [{k:v for k,v in row.items() if k!='status'} for row in self.rows('SELECT * FROM scheduled_matches ORDER BY match_order')]

    def assert_no_results(self):
        for table in MATCH_TABLES[1:]:
            self.assertEqual(self.rows(f'SELECT COUNT(*) AS n FROM {table}')[0]['n'],0)

    def test_normal_result_records_abilities_events_points_and_585_fixtures_preserved(self):
        protected, fixtures = self.protected(),self.fixture_fields()
        result = self.service.play(self.identity)
        self.assertIn(result.resolution,('normal','deathmatch'))
        self.assertEqual(sum(t['points'] for t in result.teams),1)
        self.assertEqual(sum(r['points'] for r in self.service.standings(1)),1)
        self.assertEqual(sum(r['played'] for r in self.service.standings(1)),2)
        self.assertEqual(len(result.players),self.match['required_participants']*2)
        for player in result.players:
            skills = self.rows('SELECT * FROM match_ability_stats WHERE match_id=? AND person_id=?',(self.identity,player['person_id']))
            self.assertEqual(sum(r['attempts'] for r in skills),60)
            self.assertEqual(sum(r['successes'] for r in skills),player['base_successes'])
            self.assertEqual(sum(r['failures'] for r in skills),player['base_failures'])
            self.assertEqual(sum(r['attempts'] for r in skills if r['phase']=='main'),30)
            self.assertEqual(sum(r['attempts'] for r in skills if r['phase']=='support'),30)
            self.assertEqual(player['success_rate'],(player['base_successes']+player['leader_successes'])/(60+player['leader_attempts']))
            self.assertEqual(self.service.player_records(player['person_id'],season=1,content_id=player['content_id'])[0]['base_attempts'],60)
        self.assertEqual(len(self.rows('SELECT * FROM match_events')),len(result.events))
        self.assertEqual(self.rows('SELECT status FROM scheduled_matches WHERE id=?',(self.identity,))[0]['status'],'completed')
        self.assertEqual(self.protected(),protected)
        self.assertEqual(self.fixture_fields(),fixtures)
        self.assertEqual(len(fixtures),585)
        self.assertEqual(self.rows('PRAGMA foreign_key_check'),[])

    def test_player_lineup_and_ai_share_engine_no_second_team_no_duplicates(self):
        agency = self.rows('SELECT agency_id FROM match_participants WHERE match_id=? ORDER BY agency_id',(self.identity,))[0]['agency_id']
        first = [r['person_id'] for r in self.rows("SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='first_team' ORDER BY person_id",(agency,))]
        second = self.rows("SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='second_team' LIMIT 1",(agency,))[0]['person_id']
        count = self.match['required_participants']
        for identities in ([second]+first[:count-1], [first[0]]*count if count>1 else [], first[:max(0,count-1)]):
            with self.assertRaises(MatchError):
                self.service.play(self.identity,lineups={agency:identities})
        self.assertEqual(self.rows('SELECT * FROM match_runs'),[])
        result = self.service.play(self.identity,lineups={agency:first[:count]},representatives={agency:first[0]})
        self.assertEqual({p['person_id'] for p in result.players if p['agency_id']==agency},set(first[:count]))
        self.assertTrue(all(self.rows('SELECT career_status FROM roster_memberships WHERE person_id=?',(p['person_id'],))[0]['career_status']=='first_team' for p in result.players))

    def test_ai_cannot_read_potential_archetype_or_hidden_columns(self):
        original = self.db.connect
        reads = []
        def connect():
            connection = original()
            def authorizer(action,table,column,*rest):
                if action == sqlite3.SQLITE_READ:
                    reads.append((table,column))
                    if (table,column) in (('abilities','potential'),('idols','archetype')):
                        return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            connection.set_authorizer(authorizer)
            return connection
        with patch.object(self.db,'connect',side_effect=connect):
            result = self.service.play(self.identity)
        self.assertTrue(result.players)
        self.assertNotIn(('abilities','potential'),reads)
        snapshot = self.rows('SELECT input_json FROM match_runs')[0]['input_json']
        self.assertNotIn('potential',snapshot)
        self.assertNotIn('archetype',snapshot)

    def test_deathmatch_saved_separately_from_general_ability_and_success_rate(self):
        class HalfChance:
            def probability(inner, player, skill): return .5
        class Script:
            def __init__(inner, rolls): inner.rolls=iter(rolls)
            def random(inner): return next(inner.rolls)
            def choice(inner, values): return values[0]
        def tie_then_win(match, rng):
            basic = sum(len(t.players)*60 for t in match.teams)
            bonus = sum(2 for t in match.teams for p in t.players if p.id==t.leader_id)
            return calculate_match(match,Script([.9]*(basic+bonus)+[0,.9]*10))
        with patch('idol_manager.match_service.calculate_match',side_effect=tie_then_win):
            result = MatchService(self.db,effects=HalfChance()).play(self.identity)
        self.assertEqual(result.resolution,'deathmatch')
        self.assertEqual(len(self.rows("SELECT * FROM match_events WHERE phase='deathmatch'")),20)
        self.assertEqual(sum(r['deathmatch_attempts'] for r in self.rows('SELECT * FROM match_player_stats')),20)
        self.assertEqual(sum(r['attempts'] for r in self.rows('SELECT * FROM match_ability_stats')),len(result.players)*60)
        self.assertEqual(sum(r['successes'] for r in self.rows('SELECT * FROM match_ability_stats')),0)
        self.assertTrue(all(r['success_rate']==0 for r in self.rows('SELECT * FROM idol_content_stats')))
        self.assertEqual(result,self.service.result(self.identity))

    def test_insufficient_eligible_first_team_never_replaced_by_second_team(self):
        agencies = [r['agency_id'] for r in self.rows('SELECT agency_id FROM match_participants WHERE match_id=?',(self.identity,))]
        allowed = self.rows("SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='first_team' LIMIT 1",(agencies[0],))[0]['person_id']
        class OneAllowed:
            def available(inner,p):
                return p.agency_id!=agencies[0] or p.id==allowed
        result = MatchService(self.db,availability=OneAllowed()).play(self.identity)
        own = [p for p in result.players if p['agency_id']==agencies[0]]
        self.assertEqual([p['person_id'] for p in own],[allowed])
        self.assertEqual(own[0]['base_attempts'],60)

    def test_forfeit_persisted_and_double_forfeit_both_zero_points(self):
        agencies = [r['agency_id'] for r in self.rows('SELECT agency_id FROM match_participants WHERE match_id=?',(self.identity,))]
        class NoneFromOne:
            def available(inner,p): return p.agency_id!=agencies[0]
        result = MatchService(self.db,availability=NoneFromOne()).play(self.identity)
        self.assertEqual(result.resolution,'forfeit')
        self.assertEqual(result.loser_id,agencies[0])
        self.assertEqual(sum(t['points'] for t in result.teams),1)
        another = self.rows('SELECT id FROM scheduled_matches WHERE week=1 AND weekday=2 AND day_order=1 AND id!=? LIMIT 1',(self.identity,))[0]['id']
        class Nobody:
            def available(inner,p): return False
        both = MatchService(self.db,availability=Nobody()).play(another)
        self.assertEqual(both.resolution,'double_forfeit')
        self.assertIsNone(both.winner_id)
        self.assertEqual([t['outcome'] for t in both.teams],['loss','loss'])
        self.assertEqual([t['points'] for t in both.teams],[0,0])
        self.assertEqual(self.rows('SELECT * FROM match_player_stats'),[])

    def test_complete_twice_and_new_process_return_identical_events_without_calculation(self):
        first = self.service.play(self.identity)
        with patch('idol_manager.match_service.calculate_match',side_effect=AssertionError('must not reroll')):
            self.assertEqual(first,self.service.play(self.identity))
        code = '''import json,sys
from pathlib import Path
from idol_manager.database import Database
from idol_manager.match_service import MatchService
r=MatchService(Database(Path(sys.argv[1]))).play(sys.argv[2])
print(json.dumps(r.summary(),sort_keys=True))
print(len(r.events))
'''
        child = subprocess.run([sys.executable,'-c',code,str(self.path),self.identity],cwd=ROOT,capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(child.stdout.splitlines()[0]),json.loads(json.dumps(first.summary())))
        self.assertEqual(int(child.stdout.splitlines()[1]),len(first.events))
        self.assertEqual(sum(r['points'] for r in self.service.standings(1)),1)
        self.assertEqual(self.rows('SELECT COUNT(*) n FROM match_results')[0]['n'],1)

    def test_concurrent_same_match_commits_exactly_once(self):
        barrier = threading.Barrier(2)
        def play(_):
            barrier.wait(timeout=15)
            return self.service.play(self.identity)
        with patch('idol_manager.match_service.calculate_match',wraps=calculate_match) as calculation:
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(play,range(2)))
            self.assertEqual(calculation.call_count,1)
        self.assertEqual(results[0],results[1])
        self.assertEqual(self.rows('SELECT COUNT(*) n FROM match_results')[0]['n'],1)
        self.assertEqual(self.rows('SELECT COUNT(*) n FROM match_events')[0]['n'],len(results[0].events))
        self.assertEqual(sum(r['points'] for r in self.service.standings(1)),1)

    def test_storage_failure_rolls_back_every_final_record_retry_same_seed(self):
        with closing(self.db.connect()) as connection,connection:
            connection.execute("CREATE TRIGGER fail_event BEFORE INSERT ON match_events BEGIN SELECT RAISE(ABORT,'simulated disk failure'); END")
        with self.assertRaises(MatchError):
            self.service.play(self.identity)
        self.assert_no_results()
        self.assertEqual(self.rows('SELECT status FROM scheduled_matches WHERE id=?',(self.identity,))[0]['status'],'in_progress')
        run = self.rows('SELECT * FROM match_runs')[0]
        self.assertEqual(run['status'],'prepared')
        expected = calculate_match(MatchInput.from_dict(json.loads(run['input_json'])),random.Random(int(run['seed'])))
        with closing(self.db.connect()) as connection,connection:
            connection.execute('DROP TRIGGER fail_event')
        actual = MatchService(Database(self.path),seed_factory=lambda:999).play(self.identity)
        self.assertEqual(expected,actual)

    def test_two_processes_share_one_calculation_and_one_saved_result(self):
        marker = Path(self.folder.name)/'calculation_calls.txt'
        code = '''import json,sys,time
from pathlib import Path
from unittest.mock import patch
from idol_manager.database import Database
from idol_manager.match_service import MatchService
from idol_manager.match_engine import calculate_match
def counted(*args):
    with open(sys.argv[3],'a') as file: file.write('calculated\\n')
    time.sleep(.2)
    return calculate_match(*args)
with patch('idol_manager.match_service.calculate_match',side_effect=counted):
    r=MatchService(Database(Path(sys.argv[1]))).play(sys.argv[2])
print(json.dumps(r.summary(),sort_keys=True))
'''
        children = [subprocess.Popen([sys.executable,'-c',code,str(self.path),self.identity,str(marker)],cwd=ROOT,
                                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
        self.addCleanup(lambda: [c.kill() for c in children if c.poll() is None])
        outputs = [c.communicate(timeout=20) for c in children]
        for child,output in zip(children,outputs):
            self.assertEqual(child.returncode,0,output[1])
        self.assertEqual(outputs[0][0],outputs[1][0])
        self.assertEqual(marker.read_text().splitlines(),['calculated'])
        self.assertEqual(self.rows('SELECT COUNT(*) n FROM match_results')[0]['n'],1)

    def test_last_status_write_failure_also_rolls_back_all_saved_events(self):
        with closing(self.db.connect()) as connection,connection:
            connection.execute("""CREATE TRIGGER fail_completion BEFORE UPDATE OF status ON scheduled_matches
                WHEN NEW.status='completed' BEGIN SELECT RAISE(ABORT,'last write failed'); END""")
        with self.assertRaises(MatchError):
            self.service.play(self.identity)
        self.assert_no_results()
        self.assertEqual(self.rows('SELECT status FROM match_runs')[0]['status'],'prepared')
        self.assertEqual(sum(r['points'] for r in self.service.standings(1)),0)

    def test_process_termination_after_preparation_then_resumes_same_inputs(self):
        code = '''import os,sys
from pathlib import Path
from unittest.mock import patch
from idol_manager.database import Database
from idol_manager.match_service import MatchService
with patch('idol_manager.match_service.calculate_match',side_effect=lambda *args:os._exit(23)):
    MatchService(Database(Path(sys.argv[1])),seed_factory=lambda:77).play(sys.argv[2])
'''
        child = subprocess.run([sys.executable,'-c',code,str(self.path),self.identity],cwd=ROOT,capture_output=True)
        self.assertEqual(child.returncode,23)
        self.assert_no_results()
        run = self.rows('SELECT * FROM match_runs')[0]
        source = MatchInput.from_dict(json.loads(run['input_json']))
        expected = calculate_match(source,random.Random(77))
        # Changing a future effect or lineup policy cannot change a prepared game.
        actual = self.service.play(self.identity)
        self.assertEqual(actual,expected)

    def test_prepared_lineup_is_frozen_and_bad_representative_rejected(self):
        agency = self.rows('SELECT agency_id FROM match_participants WHERE match_id=? LIMIT 1',(self.identity,))[0]['agency_id']
        with self.assertRaises(MatchError):
            self.service.play(self.identity,representatives={agency:'absent'})
        with patch('idol_manager.match_service.calculate_match',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.service.play(self.identity)
        with self.assertRaises(MatchError):
            self.service.play(self.identity,lineups={agency:[]})
        self.assert_no_results()

    def test_process_termination_after_all_result_inserts_rolls_back_and_resumes(self):
        code = '''import os,sys
from pathlib import Path
from unittest.mock import patch
from idol_manager.database import Database
from idol_manager.match_service import MatchService
original=MatchService._store_result
def terminate(connection,result):
    original(connection,result)
    os._exit(24)
with patch.object(MatchService,'_store_result',staticmethod(terminate)):
    MatchService(Database(Path(sys.argv[1])),seed_factory=lambda:77).play(sys.argv[2])
'''
        child = subprocess.run([sys.executable,'-c',code,str(self.path),self.identity],cwd=ROOT,capture_output=True)
        self.assertEqual(child.returncode,24)
        self.assert_no_results()
        self.assertEqual(self.rows('SELECT status FROM match_runs')[0]['status'],'prepared')
        self.assertEqual(self.rows('PRAGMA integrity_check')[0]['integrity_check'],'ok')
        result = self.service.play(self.identity)
        self.assertEqual(result,self.service.result(self.identity))
        self.assertEqual(sum(r['points'] for r in self.service.standings(1)),1)

    def test_unresolvable_tie_blocks_without_arbitrary_winner_or_partial_stats(self):
        with closing(self.db.connect()) as connection,connection:
            connection.execute('UPDATE abilities SET value=0')
        with self.assertRaises(UnresolvedMatch):
            self.service.play(self.identity)
        self.assert_no_results()
        self.assertEqual(self.rows('SELECT status FROM match_runs')[0]['status'],'blocked')
        with patch('idol_manager.match_service.calculate_match',side_effect=AssertionError('no reroll')):
            with self.assertRaises(UnresolvedMatch):
                self.service.play(self.identity)
        with self.assertRaises(CalendarError):
            self.calendar.advance_day(expected_absolute_day=2)

    def test_only_current_day_regular_matches_can_start(self):
        future = self.rows('SELECT id FROM scheduled_matches WHERE week=2 LIMIT 1')[0]['id']
        special = self.rows('SELECT id FROM special_events LIMIT 1')[0]['id']
        for identity in (future,special,'unknown'):
            with self.assertRaises(MatchError):
                self.service.play(identity)
        self.assert_no_results()
        self.assertEqual(self.rows('SELECT * FROM match_runs'),[])

    def test_doubleheader_second_order_requires_all_first_order_completed(self):
        second = self.rows('SELECT * FROM scheduled_matches WHERE day_order=2 ORDER BY match_order LIMIT 1')[0]
        absolute = (second['season']-1)*196+(second['week']-1)*7+second['weekday']
        with closing(self.db.connect()) as connection,connection:
            connection.execute('UPDATE game_clock SET absolute_day=?',(absolute,))
        self.calendar.ensure_current_schedule()
        with self.assertRaisesRegex(MatchError,'1차'):
            self.service.play(second['id'])
        first = self.rows('SELECT id FROM scheduled_matches WHERE week=? AND weekday=? AND day_order=1 ORDER BY match_order',(second['week'],second['weekday']))
        for row in first:
            self.service.play(row['id'])
        result = self.service.play(second['id'])
        self.assertEqual(result.match_id,second['id'])

    def test_day_advances_only_after_all_regular_matches_completed_special_still_blocks(self):
        today = self.rows('SELECT id FROM scheduled_matches WHERE week=1 AND weekday=2 ORDER BY match_order')
        with self.assertRaises(CalendarError):
            self.calendar.advance_day(expected_absolute_day=2)
        for i,row in enumerate(today):
            self.service.play(row['id'])
            if i<len(today)-1:
                with self.assertRaises(CalendarError):
                    self.calendar.advance_day(expected_absolute_day=2)
        self.assertEqual(self.calendar.advance_day(expected_absolute_day=2),GameDate(3))
        # Finished matches remain readable after their date has passed.
        self.assertEqual(self.service.play(today[0]['id']),self.service.result(today[0]['id']))
        with closing(self.db.connect()) as connection,connection:
            # Special-date barrier in an isolated save, without inventing results.
            connection.execute('UPDATE game_clock SET absolute_day=27')
        with self.assertRaises(CalendarError):
            self.calendar.advance_day(expected_absolute_day=27)
        self.assertTrue(all(r['status']=='scheduled' for r in self.rows('SELECT status FROM special_events')))

    def test_multiple_days_accumulate_real_appearances_and_content_records_no_hidden_stats_change(self):
        before = self.protected()
        for absolute in (2,3,4):
            day = self.calendar.state().date
            self.assertEqual(day.absolute_day,absolute)
            today = self.rows('SELECT id FROM scheduled_matches WHERE week=1 AND weekday=? ORDER BY match_order',(day.weekday(),))
            for row in today:
                self.service.play(row['id'])
            self.calendar.advance_day(expected_absolute_day=absolute)
        results = self.rows('SELECT COUNT(*) n FROM match_results')[0]['n']
        self.assertGreaterEqual(results,15)
        self.assertEqual(sum(r['played'] for r in self.service.standings(1)),results*2)
        self.assertEqual(sum(r['points'] for r in self.service.standings(1)),results)
        for record in self.rows('SELECT * FROM idol_regular_career_stats'):
            self.assertEqual(record['base_attempts'],record['appearances']*60)
            self.assertEqual(record['wins']+record['losses'],record['appearances'])
        self.assertEqual(before,self.protected())

    def test_explicit_new_game_clears_results_atomically_and_failed_reset_preserves_them(self):
        result = self.service.play(self.identity)
        people = tuple(Person(r['id'],r['name'],r['name_key'],r['photo_path']) for r in self.rows('SELECT * FROM people'))
        from tests.migration_fixtures import fail_new_game
        with self.assertRaises(sqlite3.IntegrityError),fail_new_game(self.db):
            self.db.create_game(people,load_settings(),random.Random(3))
        self.assertEqual(self.service.result(self.identity),result)
        self.db.create_game(people,load_settings(),random.Random(3))
        self.assert_no_results()
        self.assertEqual(self.rows('SELECT * FROM match_runs'),[])
        self.assertEqual(self.rows('PRAGMA foreign_key_check'),[])

    def test_v5_migration_backed_up_preserves_every_old_row_and_rolls_back_failure(self):
        # Reconstruct exactly the v5 table set, without touching any real save.
        with closing(self.db.connect()) as connection,connection:
            from idol_manager.special_schema import SPECIAL_TABLES
            from tests.migration_fixtures import drop_finals
            drop_finals(connection)
            connection.execute('DROP TABLE draft_estimates')
            for view in ('special_standings','idol_special_career_stats'):connection.execute(f'DROP VIEW {view}')
            for table in SPECIAL_TABLES:connection.execute(f'DROP TABLE {table}')
            for view in MATCH_VIEWS:
                connection.execute(f'DROP VIEW {view}')
            from idol_manager.condition_schema import CONDITION_TABLES
            for table in CONDITION_TABLES:
                connection.execute(f'DROP TABLE {table}')
            for table in reversed(MATCH_TABLES):
                connection.execute(f'DROP TABLE {table}')
            connection.execute('PRAGMA user_version=5')
        before = self.protected(),self.fixture_fields(),self.rows('SELECT * FROM game_clock')
        with patch('idol_manager.migrations.V6_STATEMENTS',V6_STATEMENTS+('INVALID SQL',)):
            with self.assertRaises(sqlite3.OperationalError):
                Database(self.path)
        self.assertEqual(self.rows('PRAGMA user_version')[0]['user_version'],5)
        self.assertEqual(self.rows("SELECT name FROM sqlite_master WHERE name='match_results'"),[])
        upgraded = Database(self.path)
        self.assertTrue(upgraded.last_backup_path.is_file())
        self.assertEqual((self.protected(),self.fixture_fields(),self.rows('SELECT * FROM game_clock')),before)
        self.assert_no_results()
        self.assertEqual(self.rows('PRAGMA user_version')[0]['user_version'],SCHEMA_VERSION)
        with closing(sqlite3.connect(upgraded.last_backup_path)) as connection:
            self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0],5)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM scheduled_matches').fetchone()[0],585)

    def test_special_types_are_revealed_only_from_their_week_monday(self):
        entries = [r for r in self.calendar.entries(1) if r.match_type=='특별전']
        self.assertTrue(all(not r.published and r.content=='월요일 공개 예정' for r in entries))
        for absolute, published_weeks in ((21,{4}),(49,{4,8}),(168,{4,8,12,16,20,24})):
            with closing(self.db.connect()) as connection,connection:
                connection.execute('UPDATE game_clock SET absolute_day=?',(absolute,))
            entries = [r for r in self.calendar.entries(1) if r.match_type=='특별전']
            self.assertEqual({r.week for r in entries if r.published},published_weeks)
            self.assertTrue(all(r.content in ('대학축제','K-POP 페스티벌','아이돌 체육대회') for r in entries if r.published))


if __name__ == '__main__':
    unittest.main()
