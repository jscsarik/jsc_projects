"""Recruitment identities and public-only decisions on disposable databases."""
from collections import Counter
from contextlib import closing
import sqlite3,unittest
from unittest.mock import patch
from idol_manager.database import Database
from idol_manager.migrations import SCHEMA_VERSION
from idol_manager.draft_session import DraftSession
from idol_manager.recruitment_philosophy import ensure
from idol_manager.recruitment_policy import decide,applications,public_view
from tests.test_draft_session import DraftSessionTests

class PhilosophyTests(unittest.TestCase):
    setUp=DraftSessionTests.setUp

    def test_432_selection_change_and_persisted_season_fields(self):
        self.session.select_agency('ador')
        with closing(self.database.connect()) as c,c:
            first=ensure(c,1)
            self.assertEqual(Counter(x['philosophy'] for x in first.values()),{'balanced':4,'specialist':3,'development':2})
            self.assertEqual(len({x['field'] for x in first.values() if x['field']}),3)
            second=ensure(c,2)
            self.assertEqual(len({x['field'] for x in second.values() if x['field']}),3)
            self.assertEqual({a:v['philosophy'] for a,v in first.items()},{a:v['philosophy'] for a,v in second.items()})
            self.assertEqual(first,ensure(c,1));self.assertEqual(second,ensure(c,2))
        loaded=Database(self.path)
        with closing(loaded.connect()) as c,c:self.assertEqual(first,ensure(c,1));self.assertEqual(second,ensure(c,2))
        self.session.select_agency('sm')
        with closing(self.database.connect()) as c,c:
            changed=ensure(c,1)
            self.assertNotIn('sm',changed);self.assertIn('ador',changed)
            self.assertEqual(Counter(x['philosophy'] for x in changed.values()),{'balanced':4,'specialist':3,'development':2})
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_v22_migration_backup_preserves_game_rows(self):
        self.session.select_agency('ador')
        tables=('abilities','idols','game_clock','agencies','roster_memberships','draft_estimates')
        with closing(self.database.connect()) as c,c:
            before={t:[tuple(r) for r in c.execute('SELECT * FROM '+t)] for t in tables}
            for table in ('recruitment_specialties','recruitment_philosophies','recruitment_identity'):c.execute('DROP TABLE '+table)
            c.execute('PRAGMA user_version=22')
        db=Database(self.path);self.assertTrue(db.last_backup_path.is_file())
        with closing(db.connect()) as c,c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],SCHEMA_VERSION)
            self.assertEqual(len(ensure(c)),9)
            for t in tables:self.assertEqual(before[t],[tuple(r) for r in c.execute('SELECT * FROM '+t)])
        self.assertIsNone(Database(self.path).last_backup_path)

    def test_default_founder_policy_uses_only_estimates_and_shared_pick(self):
        self.session=DraftSession(self.engine);self.session.select_agency('ador');self.session.start()
        if self.engine.state().next_turn.agency_id=='ador':
            self.engine.pick('ador',self.engine.available_candidates()[0].id,expected_pick_number=1)
        original=self.database.connect;queries=[]
        def connection():
            c=original()
            c.set_authorizer(lambda a,t,col,*_:sqlite3.SQLITE_DENY if a==sqlite3.SQLITE_READ and col in ('potential','archetype') else sqlite3.SQLITE_OK)
            c.set_trace_callback(queries.append);return c
        with patch.object(self.database,'connect',side_effect=connection):pick=self.session.pick_ai_turn()
        self.assertIsNotNone(pick)
        self.assertFalse(any('SELECT skill,value FROM abilities' in q for q in queries))
        self.assertEqual(self.session.snapshot().history[-1].person_id,pick.person_id)

class RecruitmentPolicyTests(unittest.TestCase):
    def setUp(self):
        self.candidates=[dict(id='balanced',age=23,skills=[70]*8),dict(id='music',age=23,skills=[92,92,92,50,50,50,50,50]),dict(id='young',age=14,skills=[66]*8),dict(id='weak',age=14,skills=[20]*8)]
    def identity(self,kind):return dict(philosophy=kind,field='music' if kind=='specialist' else None)
    def test_rounds_early_quality_middle_and_annual_philosophies(self):
        for kind in ('balanced','specialist','development'):
            self.assertEqual(decide(self.candidates,[],self.identity(kind),context='founding',round_number=1)[0]['id'],'music')
        for context,round_number in (('founding',5),('annual',1),('trainee',1)):
            for kind,expected in (('balanced','balanced'),('specialist','music'),('development','young')):
                self.assertEqual(decide(self.candidates,[],self.identity(kind),context=context,round_number=round_number)[0]['id'],expected)
    def test_late_strategy_depends_on_roster_not_fixed_rounds(self):
        for round_number in (7,9,16):
            full=[dict(id=str(i),age=25,skills=[75]*8) for i in range(3)]
            weak=[dict(id=str(i),age=25,skills=[90,90,90,30,30,30,30,30]) for i in range(3)]
            pick,mode=decide(self.candidates,full,self.identity('specialist'),context='founding',round_number=round_number)
            self.assertEqual((pick['id'],mode),('music','philosophy'))
            pick,mode=decide(self.candidates,weak,self.identity('specialist'),context='founding',round_number=round_number)
            self.assertEqual((pick['id'],mode),('balanced','coverage'))
    def test_trainee_two_unique_and_unknown_stats_not_used(self):
        for kind,expected in (('balanced','balanced'),('specialist','music'),('development','young')):
            selected=applications(self.candidates,[],self.identity(kind))
            self.assertEqual(selected[0],expected);self.assertEqual(len(set(selected)),2)
        view=public_view(dict(id='blind',age=15,exact=False,ranges=None,skills=[100]*8,potential=[100]*8))
        self.assertIsNone(view['skills']);self.assertNotIn('potential',view)
        self.assertEqual(applications([view],[],self.identity('development')),('blind',))
