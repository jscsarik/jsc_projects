from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from dataclasses import replace
import json,random,sqlite3,tempfile,unittest,subprocess,sys

from idol_manager.database import Database
from idol_manager.finals_service import FinalsService,roster_change_reason
from idol_manager.finals_schema import convert_day
from idol_manager.game_clock import GameDate,DAYS_PER_SEASON
from idol_manager.calendar_service import CalendarService,CalendarError
from idol_manager.squads import SquadService,SquadError
from idol_manager.match_types import MatchError
from idol_manager.match_engine import calculate_match
from tools.verify_special_season import main as build_regular
from tools.verify_postseason_season import finish
from tests.test_match_ui import copy_db


class FinalsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.folder.cleanup)
        cls.template=Path(cls.folder.name)/'template.sqlite3';build_regular(cls.template)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'test.sqlite3'
        copy_db(self.template,self.path);self.db=Database(self.path);self.finals=FinalsService(self.db,seed_factory=lambda:82)
        self.calendar=CalendarService(self.db)

    def rows(self,sql,args=()):
        with closing(self.db.connect()) as c:return [tuple(r) for r in c.execute(sql,args)]

    def table(self,name):return self.rows(f'SELECT * FROM {name} ORDER BY 1')

    def setup_rank(self,tied=0,*,player_third=False):
        from idol_manager.league import standings
        with closing(self.db.connect()) as c,c:
            c.execute('DELETE FROM season_finals');c.execute('UPDATE game_clock SET absolute_day=168')
            c.execute('UPDATE player_conditions SET injured=0')
            original=list(standings(c,1))
            if player_third:
                own=next(r for r in original if r['agency_id']=='ador');original.remove(own);original.insert(2,own)
            table=[dict(r,points=100 if i<tied else 90-i) for i,r in enumerate(original)]
            with patch('idol_manager.finals_service.standings',return_value=table):FinalsService.ensure_started(c,1)
        return [r['agency_id'] for r in table]

    def day(self,day):
        with closing(self.db.connect()) as c,c:c.execute('UPDATE game_clock SET absolute_day=?',(day,))

    def play_current(self):
        return [self.finals.play(r['id']) for r in self.finals.rows() if r['status']!='completed']

    def test_217_days_phases_and_legacy_semantic_conversion(self):
        self.assertEqual(DAYS_PER_SEASON,217)
        for d,text in ((167,'정규 24'),(168,'포스트시즌 1'),(188,'포스트시즌 3'),(189,'비시즌 1'),(216,'비시즌 4'),(217,'시즌 2')):self.assertIn(text,str(GameDate(d)))
        self.assertEqual(convert_day(168),189);self.assertEqual(convert_day(196),217);self.assertEqual(convert_day(277),298)

    def test_two_team_tie_zero_fatigue_no_regular_or_condition_changes(self):
        self.setup_rank(2)
        with closing(self.db.connect()) as c,c:
            c.execute('UPDATE player_conditions SET last_appearance_day=167,consecutive_days=10')
            c.execute('UPDATE idols SET health=90')
        protected={t:self.table(t) for t in ('match_results','match_events','match_player_stats','player_conditions','appearance_days')}
        row=self.finals.rows()[0];result=self.finals.play(row['id'])
        self.assertEqual(len(result['summary']['order']),2)
        with closing(self.db.connect()) as c:
            data=json.loads(c.execute('SELECT input_json FROM final_contests WHERE id=?',(row['id'],)).fetchone()[0])
        for team in data['teams']:
            for p in team['players']:
                self.assertAlmostEqual(data['probabilities'][p['id']]['vocal'],p['skills'][0]/100)
        for t,rows in protected.items():
            actual=self.table(t)
            if t=='draft_estimates':
                old={r[0] for r in rows};actual=[r for r in actual if r[0] in old]
            self.assertEqual(rows,actual,t)
        self.assertEqual(result,FinalsService(Database(self.path)).play(row['id']))

    def test_three_team_tie_single_contest_every_rank_and_frozen_roster(self):
        agencies=self.setup_rank(3);row=self.finals.rows()[0]
        self.assertEqual(len(self.finals.rows()),1)
        with self.assertRaises(SquadError):
            squads=SquadService(self.db);s=squads.snapshot();squads.set_leader('first_team',next(p.id for p in s.members if p.squad=='first_team'),expected_revision=s.revision)
        result=self.finals.play(row['id']);self.assertEqual(set(result['summary']['order']),set(agencies[:3]))
        self.assertTrue(all(p['base_attempts']==60 for p in result['summary']['players']))
        self.assertEqual(len(json.loads(self.finals.season_state()['final_order_json'])),10)

    def test_no_tie_top_four_seeds_and_schedule_wednesday_thursday(self):
        order=self.setup_rank();state=self.finals.season_state()
        self.assertEqual(json.loads(state['final_order_json']),order)
        rows=self.finals.rows(today_only=False)
        self.assertEqual([r['absolute_day'] for r in rows],[170,171]);self.assertEqual(json.loads(rows[0]['agencies_json']),order[2:4])
        self.assertEqual(len(self.rows("SELECT * FROM season_honors WHERE kind='qualification'")),4)

    def desired_winner(self,identity,winner):
        def calculate(match,rng,**kwargs):
            # Controlled engine output for bracket/permission tests. Full-season
            # integration separately uses real frozen CA probabilities and RNG.
            chances={p.id:{s:float(t.agency_id==winner) for s in match.main_skills+tuple(s for s in ('vocal','dance','rap','entertainment','appearance','physique','intelligence','leadership') if s not in match.main_skills)} for t in match.teams for p in t.players}
            return calculate_match(replace(match,probabilities=chances),random.Random(1),**kwargs)
        with patch('idol_manager.finals_service.calculate_match',side_effect=calculate):return self.finals.play(identity)

    def split_series(self):
        order=self.setup_rank(player_third=True);self.day(170);row=self.finals.rows()[0];self.desired_winner(row['id'],order[2])
        self.day(171);row=self.finals.rows()[0];self.desired_winner(row['id'],order[3]);self.day(172)
        return order,self.finals.rows()[0]

    def test_two_zero_no_friday_and_next_round_link(self):
        order=self.setup_rank()
        with closing(self.db.connect()) as c,c:c.execute('UPDATE idols SET health=90')
        self.day(170);self.desired_winner(self.finals.rows()[0]['id'],order[2])
        self.day(171);self.desired_winner(self.finals.rows()[0]['id'],order[2])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM final_contests WHERE round_number=1 AND game_number=3"),[(0,)])
        self.assertEqual(self.rows('SELECT agency_a,agency_b FROM final_series WHERE round_number=2'),[(order[1],order[2])])
        for day in (177,178,184,185):
            self.day(day);self.desired_winner(self.finals.rows()[0]['id'],order[2])
        self.assertEqual(self.rows("SELECT agency_id FROM season_honors WHERE kind='regular_first'"),[(order[0],)])
        self.assertEqual(self.rows("SELECT agency_id FROM season_honors WHERE kind='champion'"),[(order[2],)])

    def test_one_one_friday_roster_swap_leader_and_prepared_lock(self):
        order,row=self.split_series()
        squads=SquadService(self.db);state=squads.snapshot()
        first=next(p.id for p in state.members if p.squad=='first_team');second=next(p.id for p in state.members if p.squad=='second_team')
        squads.swap(first,second,expected_revision=state.revision)
        state=squads.snapshot();squads.set_leader('first_team',second,expected_revision=state.revision)
        self.assertEqual(dict(squads.snapshot().leaders)['first_team'],second)
        with patch('idol_manager.finals_service.calculate_match',side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError):self.finals.play(row['id'])
        state=squads.snapshot()
        with self.assertRaises(SquadError):squads.set_leader('first_team',second,expected_revision=state.revision)
        result=FinalsService(Database(self.path)).play(row['id']);self.assertIsNotNone(result)

    def test_ordinary_tuesday_wednesday_thursday_blocked(self):
        self.setup_rank();squads=SquadService(self.db)
        for day in (169,170,171):
            self.day(day);s=squads.snapshot()
            with self.assertRaises(SquadError):squads.set_leader('first_team',next(p.id for p in s.members if p.squad=='first_team'),expected_revision=s.revision)

    def test_friday_third_day_fatigue_and_ai_no_pa(self):
        order,row=self.split_series();original=self.db.connect
        with closing(original()) as c,c:
            c.execute('UPDATE player_conditions SET last_appearance_day=171,consecutive_days=2,injured=0')
        reads=[]
        def connect():
            c=original()
            def authorize(action,table,column,*_):
                reads.append((table,column))
                return sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_READ and (table,column) in (('abilities','potential'),('idols','archetype')) else sqlite3.SQLITE_OK
            c.set_authorizer(authorize);return c
        with patch.object(self.db,'connect',side_effect=connect):self.finals.play(row['id'])
        context=json.loads(self.rows('SELECT condition_json FROM final_contests WHERE id=?',(row['id'],))[0][0])
        self.assertTrue(all(v['penalty']==.1 for v in context['public'].values()))
        self.assertNotIn(('abilities','potential'),reads)

    def test_unprocessed_tie_or_post_blocks_date(self):
        self.setup_rank(2)
        with self.assertRaises(CalendarError):self.calendar.advance_day(expected_absolute_day=168)
        self.play_current();self.day(170)
        with self.assertRaises(CalendarError):self.calendar.advance_day(expected_absolute_day=170)

    def test_concurrent_completion_once_and_result_transaction_rollback(self):
        self.setup_rank();self.day(170);row=self.finals.rows()[0]
        with patch.object(FinalsService,'_advance_series',side_effect=RuntimeError('save failure')):
            before=self.table('appearance_days')
            with self.assertRaises(RuntimeError):self.finals.play(row['id'])
            self.assertEqual(before,self.table('appearance_days'));self.assertIsNone(self.finals.result(row['id']))
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:FinalsService(Database(self.path)).play(row['id']),range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(self.rows("SELECT COUNT(*) FROM final_contests WHERE status='completed'"),[(1,)])

    def test_full_real_season_postseason_offseason_rollover_trophy_idempotent(self):
        protected={t:self.table(t) for t in ('match_results','match_events','draft_picks','draft_estimates')}
        potentials=self.rows('SELECT person_id,skill,potential FROM abilities ORDER BY person_id,skill')
        opening=dict(self.rows('SELECT id,funds_krw FROM agencies'))
        prior_journal=dict(self.rows('SELECT agency_id,SUM(cash_delta) FROM finance_ledger GROUP BY agency_id'))
        report=finish(self.db)
        for agency,balance in self.rows('SELECT id,funds_krw FROM agencies'):
            total=self.rows('SELECT COALESCE(SUM(cash_delta),0) FROM finance_ledger WHERE agency_id=?',(agency,))[0][0]
            self.assertEqual(balance,opening[agency]+total-prior_journal.get(agency,0))
        self.assertEqual(report['date'],'시즌 2 · 정규 1주차 · 월요일')
        champion=self.rows("SELECT agency_id FROM season_honors WHERE kind='champion'")
        self.assertEqual(len(champion),1)
        for r in self.rows("SELECT id FROM final_contests WHERE status='completed'"):self.finals.play(r[0])
        self.assertEqual(champion,self.rows("SELECT agency_id FROM season_honors WHERE kind='champion'"))
        self.assertTrue(self.finals.rows(today_only=False,season=1))
        self.assertEqual(self.finals.rows(today_only=False,season=2),())
        for t,rows in protected.items():
            actual=self.table(t)
            if t=='draft_estimates':
                old={r[0] for r in rows};actual=[r for r in actual if r[0] in old]
            self.assertEqual(rows,actual,t)
        old_ids={p[0] for p in potentials}
        self.assertEqual(potentials,[r for r in self.rows('SELECT person_id,skill,potential FROM abilities ORDER BY person_id,skill') if r[0] in old_ids])

    def test_tie_multiple_forfeits_uniform_lottery_persisted_and_active_always_above(self):
        from idol_manager.finals_service import forfeit_lottery
        self.assertEqual(len({tuple(forfeit_lottery(('a','b','c'),s)) for s in range(100)}),6)
        self.assertEqual(forfeit_lottery(('a','b','c'),8),forfeit_lottery(('c','b','a'),8))
        order=self.setup_rank(3)
        with closing(self.db.connect()) as c,c:
            frozen=json.loads(c.execute('SELECT frozen_json FROM season_finals').fetchone()[0])
            for a in order[1:3]:frozen[a]['injured']=[p['id'] for p in frozen[a]['players']]
            c.execute('UPDATE season_finals SET frozen_json=?',(json.dumps(frozen),))
        identity=self.finals.rows()[0]['id'];result=self.finals.play(identity)
        self.assertEqual(result['summary']['order'][0],order[0]);self.assertEqual(len(result['summary']['lottery_order']),2)
        self.assertEqual(result,FinalsService(Database(self.path)).play(identity))
        self.assertEqual([t['rank'] for t in result['summary']['teams']],[1,2,3])

    def test_all_tie_forfeit_lottery_no_trials_and_post_double_forfeit_high_seed_two_zero(self):
        order=self.setup_rank(3)
        with closing(self.db.connect()) as c,c:
            frozen=json.loads(c.execute('SELECT frozen_json FROM season_finals').fetchone()[0])
            for a in order[:3]:frozen[a]['injured']=[p['id'] for p in frozen[a]['players']]
            c.execute('UPDATE season_finals SET frozen_json=?',(json.dumps(frozen),))
        result=self.finals.play(self.finals.rows()[0]['id']);self.assertEqual(len(result['events']),0)
        self.assertEqual(set(result['summary']['lottery_order']),set(order[:3]))
        order=self.setup_rank()
        with closing(self.db.connect()) as c,c:c.execute('UPDATE player_conditions SET injured=1')
        for day in (170,171):
            self.day(day);row=self.finals.rows()[0];r=self.finals.play(row['id'])
            self.assertEqual(r['summary']['order'][0],order[2]);self.assertEqual(r['summary']['forfeit_policy'],'higher_frozen_regular_seed')
            self.assertEqual(r,self.finals.play(row['id']))
        self.assertEqual(self.rows('SELECT winner_id FROM final_series WHERE round_number=1'),[(order[2],)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM final_contests WHERE round_number=1 AND game_number=3'),[(0,)])

    def test_tie_injury_applied_without_fatigue_or_appearance_writes(self):
        self.setup_rank(2);before=self.rows('SELECT person_id,last_appearance_day,consecutive_days FROM player_conditions ORDER BY person_id');appearances=self.table('appearance_days')
        with patch('idol_manager.finals_service.injury_probability',return_value=1):result=self.finals.play(self.finals.rows()[0]['id'])
        self.assertEqual(before,self.rows('SELECT person_id,last_appearance_day,consecutive_days FROM player_conditions ORDER BY person_id'))
        self.assertEqual(appearances,self.table('appearance_days'))
        for p in result['summary']['players']:
            self.assertEqual(self.rows('SELECT injured FROM player_conditions WHERE person_id=?',(p['person_id'],)),[(1,)])

    def test_empty_player_selection_is_not_a_forfeit(self):
        order=self.setup_rank(player_third=True);self.day(170)
        with self.assertRaises(MatchError):self.finals.play(self.finals.rows()[0]['id'],lineups={'ador':()})
        self.assertEqual(self.rows("SELECT COUNT(*) FROM final_contests WHERE status='completed'"),[(0,)])

    def test_process_exit_after_prepare_resumes_same_seed_events(self):
        from idol_manager.config import ROOT
        self.setup_rank();self.day(170);identity=self.finals.rows()[0]['id']
        source='''import sys,os
from pathlib import Path
from unittest.mock import patch
from idol_manager.database import Database
from idol_manager.finals_service import FinalsService
with patch('idol_manager.finals_service.calculate_match',side_effect=lambda *a,**k:os._exit(17)):
    FinalsService(Database(Path(sys.argv[1]))).play(sys.argv[2])
'''
        process=subprocess.run([sys.executable,'-c',source,str(self.path),identity],cwd=ROOT,timeout=30)
        self.assertEqual(process.returncode,17)
        self.assertEqual(self.rows('SELECT status FROM final_contests WHERE id=?',(identity,)),[('prepared',)])
        first=FinalsService(Database(self.path)).play(identity)
        self.assertEqual(first,FinalsService(Database(self.path)).play(identity))

    def test_ai_friday_promotes_publicly_stronger_second_team_without_bonuses(self):
        order,row=self.split_series();agency=order[3]
        with closing(self.db.connect()) as c,c:
            first={r[0] for r in c.execute("SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='first_team'",(agency,))}
            second={r[0] for r in c.execute("SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='second_team'",(agency,))}
            for person in first|second:
                c.execute('UPDATE abilities SET value=?,potential=100 WHERE person_id=?',(0 if person in first else 100,person))
                c.execute('UPDATE idols SET health=90 WHERE person_id=?',(person,))
                c.execute('UPDATE player_conditions SET injured=0,return_not_before=NULL WHERE person_id=?',(person,))
        self.finals.play(row['id'])
        after={r[0] for r in self.rows("SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='first_team'",(agency,))}
        self.assertEqual(len(after),5);self.assertTrue(after<=second)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM roster_memberships WHERE agency_id=? AND career_status='second_team'",(agency,)),[(11,)])
