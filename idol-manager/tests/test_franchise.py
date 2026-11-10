"""Focused ledger, scoring and presentation checks on disposable databases."""
from collections import Counter
from contextlib import closing
from dataclasses import replace
import json,random,sqlite3,unittest
from unittest.mock import patch
from idol_manager.franchise import settle,eligible,display_name
from idol_manager.teamwork import trial
from idol_manager.match_engine import calculate_match
from idol_manager.match_types import MatchInput,MatchPlayer,MatchTeam,MatchResult
from idol_manager.match_replay import replay_frames
from idol_manager.database import Database
from tests.test_match_engine import match_input
from tests.test_special_engine import contest
from tests import test_season32 as fixture

def marked(data,n):
    return replace(data,teams=tuple(replace(t,players=tuple(replace(p,franchise=i<n) for i,p in enumerate(t.players))) for t in data.teams))

class FranchiseEngineTests(unittest.TestCase):
    def test_minimum_players_and_all_players_must_succeed(self):
        for count in (1,2,3,4,5,10):
            team=MatchTeam('a',tuple(MatchPlayer(str(i),'a',str(i),80,(100,)*8,True) for i in range(count)),None,None)
            rng=random.Random(7);before=rng.getstate()
            result=trial(team,[True]*count,1,count,rng)
            self.assertEqual(result is None,count<3)
            if count<3:self.assertEqual(before,rng.getstate())
            rng=random.Random(9);before=rng.getstate()
            self.assertIsNone(trial(team,[True]*(count-1)+[False],1,count,rng));self.assertEqual(before,rng.getstate())
        team=marked(match_input(count=5),0).teams[0]
        self.assertIsNone(trial(team,[True]*5,1,5,random.Random(1)))

    def test_probability_cap_and_single_point(self):
        for n,expected in ((1,.15),(2,.30),(3,.45),(4,.45),(5,.45)):
            data=marked(match_input(count=5),n)
            with patch('idol_manager.teamwork.random.Random') as unused:
                rng=unittest.mock.Mock();rng.random.return_value=0
                result=trial(data.teams[0],[True]*5,1,5,rng)
            self.assertEqual(result['probability'],expected);self.assertEqual(int(result['success']),1)
            rng.random.assert_called_once()

    def test_regular_score_independent_base_trials_and_persisted_replay(self):
        data=match_input(90,70,count=5)
        plain=calculate_match(data,random.Random(37));result=calculate_match(marked(data,5),random.Random(37))
        self.assertTrue(result.teamwork)
        self.assertEqual([e for e in plain.events if e.phase!='deathmatch'],[e for e in result.events if e.phase!='deathmatch'])
        for player in result.players:self.assertEqual(player['base_attempts'],60)
        self.assertEqual(len({(b['agency_id'],b['tick']) for b in result.teamwork}),len(result.teamwork))
        for t in result.teams:
            own=sum(e.success for e in result.events if e.agency_id==t['agency_id'])
            bonus=sum(b['success'] for b in result.teamwork if b['agency_id']==t['agency_id'])
            self.assertEqual(t['total_score'],own+bonus);self.assertLessEqual(bonus,60)
        restored=MatchResult.restore(json.loads(json.dumps(result.summary())),result.events)
        self.assertEqual(list(result.teamwork),list(restored.teamwork))
        frames=replay_frames(restored);score=Counter()
        for f in frames:
            for e in f.events:score[e.agency_id]+=e.success
            for b in restored.teamwork:
                if any(e.sequence==b['after_sequence'] for e in f.events):score[b['agency_id']]+=b['success']
        self.assertEqual(dict(score),{t['agency_id']:t['total_score'] for t in result.teams})

    def test_special_ten_person_events_and_postseason_common_engine(self):
        from idol_manager.special_engine import calculate_contest
        data=marked(contest(players=10),5)
        data=replace(data,probabilities={p.id:{s:.92 for s in data.probabilities[p.id]} for t in data.teams for p in t.players})
        result=calculate_contest(data,random.Random(17))
        self.assertTrue(result.teamwork)
        for b in result.teamwork:
            events=[e for e in result.events if e.agency_id==b['agency_id'] and e.tick==b['tick'] and e.phase in ('main','support')]
            self.assertEqual(len(events),10);self.assertTrue(all(e.success for e in events));self.assertEqual(b['probability'],.45)
        for t in result.teams:self.assertEqual(t['base_score'],sum(e.success for e in result.events if e.agency_id==t['agency_id'] and e.phase!='deathmatch')+t['teamwork_score'])
        post=calculate_match(marked(match_input(90,70,count=3),1),random.Random(3))
        self.assertTrue(all(b['probability']==.15 for b in post.teamwork))

    def test_legacy_prepared_input_round_trip_has_no_new_false_fields(self):
        data=match_input(count=3).to_dict()
        self.assertTrue(all('franchise' not in p for t in data['teams'] for p in t['players']))
        restored=MatchInput.from_dict(json.loads(json.dumps(data)))
        self.assertEqual(data,restored.to_dict())

class FranchiseStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.Season32Tests.setUpClass.__func__(cls)
    setUp=fixture.Season32Tests.setUp
    rows=fixture.Season32Tests.rows
    day=fixture.Season32Tests.day

    def person(self):return self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='first_team' ORDER BY person_id LIMIT 1")[0][0]
    def credit(self,person,units=2,seasons=3):
        with closing(self.db.connect()) as c,c:
            stint=c.execute('SELECT id FROM franchise_stints WHERE person_id=? AND ended_day IS NULL',(person,)).fetchone()[0]
            c.executemany('INSERT OR IGNORE INTO franchise_seasons VALUES (?,?,?,?,?)',[(stint,s,units,int(units==2),s*224-1) for s in range(1,seasons+1)])

    def test_half_full_seasons_threshold_idempotence_and_roles(self):
        p=self.person()
        with closing(self.db.connect()) as c,c:
            for season in range(1,6):settle(c,season)
            self.assertNotIn(p,eligible(c));settle(c,6);settle(c,6)
            self.assertIn(p,eligible(c))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM franchise_seasons y JOIN franchise_stints s ON s.id=y.stint_id WHERE person_id=?',(p,)).fetchone()[0],6)
            trainee=c.execute("SELECT person_id FROM initial_draft_undrafted LIMIT 1").fetchone()[0]
            c.execute("UPDATE roster_memberships SET agency_id='ador',career_status='trainee' WHERE person_id=?",(trainee,))
            c.execute('UPDATE franchise_stints SET started_day=0 WHERE person_id=?',(trainee,))
            settle(c,7)
            self.assertEqual(c.execute('SELECT units FROM franchise_seasons y JOIN franchise_stints s ON s.id=y.stint_id WHERE person_id=? AND season=7',(trainee,)).fetchone()[0],1)

    def test_actual_first_team_appearance_earns_one_and_repeat_is_safe(self):
        self.day(9);self.service.calendar.ensure_current_schedule()
        identity=self.rows("SELECT m.id FROM scheduled_matches m JOIN match_participants p ON p.match_id=m.id WHERE p.agency_id='ador' AND m.week=1 AND m.weekday=2 ORDER BY match_order LIMIT 1")[0][0]
        result=self.service.matches.play(identity)
        with closing(self.db.connect()) as c,c:
            settle(c,1);settle(c,1)
            for p in result.players:
                row=c.execute('SELECT units,first_appearance FROM franchise_seasons y JOIN franchise_stints s ON s.id=y.stint_id WHERE s.person_id=? AND season=1',(p['person_id'],)).fetchone()
                self.assertEqual(tuple(row),(2,1))

    def test_renew_same_team_preserves_but_release_return_resets_and_ui(self):
        p=self.person();self.credit(p)
        with closing(self.db.connect()) as c,c:
            before=c.execute('SELECT id FROM franchise_stints WHERE person_id=? AND ended_day IS NULL',(p,)).fetchone()[0]
            c.execute('UPDATE roster_memberships SET agency_id=agency_id WHERE person_id=?',(p,))
            self.assertIn(p,eligible(c))
        self.assertTrue(self.service.profiles.get(p)['identity']['display_name'].endswith('(프차)'))
        with closing(self.db.connect()) as c:self.assertTrue(next(x for x in self.service.matches._public_first_team(c,'ador') if x.id==p).franchise)
        with closing(self.db.connect()) as c,c:
            c.execute('DELETE FROM squad_leaders WHERE person_id=?',(p,))
            c.execute("UPDATE roster_memberships SET agency_id=NULL,career_status='fa' WHERE person_id=?",(p,))
            c.execute("UPDATE roster_memberships SET agency_id='ador',career_status='pro_pending' WHERE person_id=?",(p,))
            self.assertNotIn(p,eligible(c));self.assertEqual(c.execute('SELECT COUNT(*) FROM franchise_stints WHERE person_id=?',(p,)).fetchone()[0],2)
        self.assertNotIn('(프차)',self.service.profiles.get(p)['identity']['display_name'])

    def test_match_bonus_permanent_no_personal_ca_growth_contamination(self):
        from idol_manager.game_clock import regular_day
        identity,week,weekday=self.rows("SELECT id,week,weekday FROM scheduled_matches WHERE participants_min=5 AND participants_max=5 AND day_order=1 ORDER BY match_order LIMIT 1")[0]
        self.day(regular_day(1,week,weekday));self.service.calendar.ensure_current_schedule()
        agencies=[r[0] for r in self.rows('SELECT agency_id FROM match_participants WHERE match_id=?',(identity,))]
        for agency in agencies:
            for (p,) in self.rows("SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='first_team'",(agency,)):self.credit(p)
        # High public probabilities keep this short test reliably exercising bonuses.
        self.service.matches.effects.probability=lambda p,s: .97
        protected=self.rows('SELECT * FROM abilities ORDER BY person_id,skill')
        result=self.service.matches.play(identity)
        self.assertTrue(result.teamwork)
        again=self.service.matches.play(identity)
        self.assertEqual(result.summary(),again.summary())
        fresh=type(self.service)(self.root,database_path=self.path)
        self.assertEqual(result.summary(),fresh.matches.result(identity).summary())
        self.assertEqual(protected,self.rows('SELECT * FROM abilities ORDER BY person_id,skill'))
        self.assertEqual(sum(p['base_attempts'] for p in result.players),600)
        self.assertEqual(self.rows('SELECT SUM(attempts) FROM match_ability_stats WHERE match_id=?',(identity,)),[(600,)])
        self.assertEqual(self.rows('PRAGMA foreign_key_check'),[])

    def test_migration_backups_and_incomplete_history_never_grants_status(self):
        protected={t:self.rows('SELECT * FROM '+t+' ORDER BY 1') for t in ('abilities','agencies','draft_picks','idols')}
        with closing(self.db.connect()) as c,c:
            c.execute('DROP TRIGGER franchise_join');c.execute('DROP TRIGGER franchise_move')
            c.execute('DROP TABLE franchise_seasons');c.execute('DROP TABLE franchise_stints');c.execute('PRAGMA user_version=25')
            c.execute('DROP TABLE maintenance_condition_resets')
        db=Database(self.path);self.assertTrue(db.last_backup_path.exists())
        with closing(db.connect()) as c:self.assertFalse(eligible(c))
        for t,data in protected.items():self.assertEqual(data,self.rows('SELECT * FROM '+t+' ORDER BY 1'))
        self.assertIsNone(Database(self.path).last_backup_path)

    def test_battle_marker_and_bonus_final_display(self):
        from PySide6.QtWidgets import QApplication
        from idol_manager.ui.battle_view import BattleView
        from idol_manager.ui.thumbnails import ThumbnailCache
        from PySide6.QtCore import QSize
        app=QApplication.instance() or QApplication([])
        photos=ThumbnailCache(self.root,self.root/'test_franchise_cache',image_size=QSize(40,50))
        stage=BattleView(photos);self.addCleanup(stage.close)
        stage.configure('test',[('a','기획사')],[dict(id='p',agency_id='a',name=display_name('이름',True),leader=False,photo_path='')],
                        [dict(agency_id='a',after_sequence=3,success=True)])
        self.assertEqual(stage.cards['p'].name.text(),'이름 (프차)')
        stage.final_counts(Counter(p=10));self.assertEqual(stage.teams[0].total.text(),'11')
        photos.pool.waitForDone()

    def test_trade_changes_stint_without_erasing_credits(self):
        p=self.person();self.credit(p)
        with closing(self.db.connect()) as c,c:
            q=c.execute("SELECT person_id FROM roster_memberships WHERE agency_id='jyp' AND career_status='second_team' LIMIT 1").fetchone()[0]
            c.execute("UPDATE roster_memberships SET agency_id=NULL,career_status='fa' WHERE person_id=?",(q,))
            c.execute('DELETE FROM squad_leaders WHERE person_id=?',(p,))
            c.execute("UPDATE roster_memberships SET agency_id='jyp',career_status='pro_pending' WHERE person_id=?",(p,))
            self.assertNotIn(p,eligible(c));self.assertEqual(c.execute('SELECT SUM(units) FROM franchise_seasons y JOIN franchise_stints s ON s.id=y.stint_id WHERE person_id=?',(p,)).fetchone()[0],6)

    def test_special_result_bonus_saved_and_loaded_once(self):
        from idol_manager.game_clock import regular_day
        self.day(regular_day(1,4,6));self.service.calendar.ensure_current_schedule()
        for (p,) in self.rows("SELECT person_id FROM roster_memberships WHERE agency_id IS NOT NULL"):self.credit(p)
        with closing(self.db.connect()) as c,c:
            c.execute('UPDATE abilities SET potential=MAX(potential,90),value=90')
        event=self.rows('SELECT id FROM special_events WHERE week=4')[0][0]
        self.service.specials.seed_factory=lambda:3
        original=self.service.specials._event
        # Isolate round persistence without simulating 95 unrelated prior fixtures.
        with patch.object(self.service.specials,'_event',side_effect=lambda c,i,**kw:original(c,i)):
            self.service.specials.start(event)
            stage=self.service.specials.state(event)['rounds'][0]['id']
            result=self.service.specials.play(stage)
            self.assertTrue(result.teamwork)
            self.assertEqual(result.summary(),self.service.specials.play(stage).summary())
            self.assertEqual(result.summary(),self.service.specials.result(stage).summary())
        self.assertEqual(self.rows('PRAGMA foreign_key_check'),[])

    def test_proven_history_backfill_only_and_no_repeat(self):
        p=self.person();self.day(1344)
        with closing(self.db.connect()) as c,c:
            c.execute('DROP TRIGGER franchise_join');c.execute('DROP TRIGGER franchise_move')
            c.execute('DROP TABLE franchise_seasons');c.execute('DROP TABLE franchise_stints')
            c.execute('DROP TABLE maintenance_condition_resets')
            c.executemany("INSERT OR IGNORE INTO development_days VALUES (1,?,?,'ador','second_team',0)",[(d,p) for d in range(1344)])
            c.execute('PRAGMA user_version=25')
        Database(self.path)
        with closing(self.db.connect()) as c:self.assertIn(p,eligible(c))
        before=self.rows('SELECT * FROM franchise_seasons ORDER BY stint_id,season')
        Database(self.path);self.assertEqual(before,self.rows('SELECT * FROM franchise_seasons ORDER BY stint_id,season'))
