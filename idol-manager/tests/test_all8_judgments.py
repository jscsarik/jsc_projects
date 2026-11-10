from collections import Counter
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import json,random,sqlite3,unittest
from unittest.mock import patch
from idol_manager.config import ROOT,SKILLS
from idol_manager.judgments import basic_trials
from idol_manager.match_engine import calculate_match,ENGINE_VERSION,LEGACY_ENGINE_VERSION
from idol_manager.match_service import MatchService
from idol_manager.match_types import MatchInput
from idol_manager.finals_service import FinalsService,dump
from idol_manager.profile_service import ProfileService
from idol_manager.development_service import activity
from tests import test_match_engine as pure
from tests import test_matches as fixture
from tests import test_special_engine as specials
from idol_manager.special_engine import calculate_contest


class AllEightEngineTests(unittest.TestCase):
    def test_uniform_independent_pool_and_one_main_expectation(self):
        source=pure.match_input(100,0,leaders=False);rng=random.Random(170117);counts=Counter();repeats=0
        for _ in range(2000):
            events=[];basic_trials(source.teams,('vocal',),source.probabilities,rng,events,60,support_pool=SKILLS)
            chosen=[e.skill for e in events if e.person_id=='a0' and e.phase=='support']
            repeats+=sum(a==b for a,b in zip(chosen,chosen[1:]))
            counts.update(e.skill for e in events if e.phase=='support')
        expected=sum(counts.values())/8
        self.assertEqual(set(counts),set(SKILLS));self.assertEqual(sum(counts.values()),120000)
        chi=sum((counts[s]-expected)**2/expected for s in SKILLS)
        self.assertLess(chi,30);self.assertGreater(repeats,5000)
        self.assertAlmostEqual(30+counts['vocal']/4000,33.75,delta=.15)
        (ROOT/'.test-artifacts').mkdir(exist_ok=True)
        (ROOT/'.test-artifacts/integrated17_distribution.json').write_text(json.dumps(dict(draws=sum(counts.values()),counts=dict(counts),chi_square=chi,
            degrees_of_freedom=7,mean_single_main_trials=30+counts['vocal']/4000,independent_repeated_choices=repeats),indent=2),encoding='utf-8')

    def test_repeated_main_in_random_group_is_only_one_score_each(self):
        result=calculate_match(pure.match_input(100,0,leaders=False),pure.ScriptedRandom([.5]*120))
        for p in result.players:
            own=[e for e in result.events if e.person_id==p['person_id']]
            self.assertEqual(Counter(e.phase for e in own),{'main':30,'support':30})
            self.assertEqual({e.skill for e in own if e.phase=='support'},{'vocal'})
        self.assertEqual([t['total_score'] for t in result.teams],[60,0]);self.assertEqual(len(result.events),120)

    def test_special_30_and_60_keep_excluded_pool_and_legacy_regular(self):
        for final in (False,True):
            data=specials.contest(final=final)
            result=calculate_contest(data,random.Random(1701))
            self.assertTrue(all(e.skill not in data.main_skills for e in result.events if e.phase=='support'))
            self.assertTrue(all(p['base_attempts']==(60 if final else 30) for p in result.players))
        source=pure.match_input(100,0,leaders=False)
        old=calculate_match(source,pure.ScriptedRandom([.5]*120),include_main_in_random=False)
        self.assertEqual({e.skill for e in old.events if e.phase=='support'},{'rap'})


class AllEightStorageTests(unittest.TestCase):
    setUpClass=classmethod(fixture.MatchServiceTests.setUpClass.__func__)
    setUp=fixture.MatchServiceTests.setUp
    rows=fixture.MatchServiceTests.rows

    def test_new_saved_groups_profile_totals_growth_actual_skill_and_cached_result(self):
        result=self.service.play(self.identity)
        self.assertEqual(self.rows('SELECT engine_version FROM match_runs')[0]['engine_version'],ENGINE_VERSION)
        with closing(self.db.connect()) as c:
            before=list(c.iterdump());facts=activity(c,0,6)
            for p in result.players:
                own=[e for e in result.events if e.person_id==p['person_id'] and e.phase in ('main','support')]
                self.assertEqual(len(own),60)
                expected=Counter(e.skill for e in own if e.success)
                self.assertEqual(facts[p['person_id']]['basic_successes'],[expected[s] for s in SKILLS])
                profile=ProfileService(self.db).get(p['person_id'])
                for total in profile['statistics']['skill_totals']:
                    self.assertEqual(total['attempts'],sum(e.skill==total['skill'] for e in own))
                    self.assertEqual(total['main_attempts']+total['random_attempts'],total['attempts'])
            main_skills={e.skill for e in result.events if e.phase=='main'}
            self.assertTrue(any(e.phase=='support' and e.skill in main_skills for e in result.events))
        with patch('idol_manager.match_service.calculate_match',side_effect=AssertionError('completed result reroll')):self.assertEqual(result,self.service.play(self.identity))
        with closing(self.db.connect()) as c:self.assertEqual(before,list(c.iterdump()))

    def test_prepared_legacy_regular_resumes_old_rules_and_keeps_seed_inputs(self):
        source,seed=self.service._prepare(self.identity,None,None)
        with closing(self.db.connect()) as c,c:
            c.execute('UPDATE match_runs SET engine_version=?',(LEGACY_ENGINE_VERSION,))
            frozen=c.execute('SELECT input_json,seed FROM match_runs').fetchone()
        expected=calculate_match(source,random.Random(seed),include_main_in_random=False)
        actual=MatchService(self.db).play(self.identity);self.assertEqual(actual,expected)
        with closing(self.db.connect()) as c:
            self.assertEqual(tuple(frozen),tuple(c.execute('SELECT input_json,seed FROM match_runs').fetchone()))
            self.assertEqual(c.execute('SELECT engine_version FROM match_runs').fetchone()[0],LEGACY_ENGINE_VERSION)

    def post(self,identity):
        with closing(self.db.connect()) as c,c:
            c.execute('UPDATE game_clock SET absolute_day=170')
            c.execute("INSERT INTO season_finals(season,status,frozen_json,standings_json,final_order_json) VALUES (1,'seeded','{}','[]','[\"ador\",\"jyp\"]')")
            c.execute("INSERT INTO final_series VALUES (1,1,'ador','jyp',NULL)")
            content=dict(id='profile-test',name='판정 테스트',main_abilities=['보컬','댄스'])
            c.execute("INSERT INTO final_contests(id,season,kind,round_number,game_number,absolute_day,agencies_json,content_json,required) VALUES (?,1,'post',1,1,170,'[\"ador\",\"jyp\"]',?,2)",(identity,json.dumps(content)))
        return FinalsService(self.db,seed_factory=lambda:913)

    def test_new_postseason_uses_all_eight_and_persists_rule_marker(self):
        finals=self.post('new-post');result=finals.play('new-post')
        self.assertTrue(any(e.phase=='support' and e.skill in ('vocal','dance') for e in result['events']))
        with closing(self.db.connect()) as c:self.assertEqual(json.loads(c.execute("SELECT input_json FROM final_contests WHERE id='new-post'").fetchone()[0])['regular_random_pool'],'all8-v2')
        self.assertTrue(all(p['base_attempts']==60 for p in result['summary']['players']))

    def test_prepared_old_postseason_keeps_excluded_pool_and_exact_events(self):
        finals=self.post('old-post')
        with closing(self.db.connect()) as c,c:
            row=c.execute("SELECT * FROM final_contests WHERE id='old-post'").fetchone();data,context=finals._prepare(c,row,None)
            data.pop('regular_random_pool');c.execute("UPDATE final_contests SET status='prepared',seed='913',input_json=?,condition_json=?",(dump(data),dump(context)))
        expected=calculate_match(MatchInput.from_dict(data),random.Random(913),include_main_in_random=False)
        result=finals.play('old-post');self.assertEqual(result['events'],expected.events)
        self.assertFalse(any(e.phase=='support' and e.skill in ('vocal','dance') for e in result['events']))
