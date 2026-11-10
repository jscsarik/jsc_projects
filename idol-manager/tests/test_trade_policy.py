"""Small deterministic policy/ledger checks; no real saves or season simulation."""
from contextlib import closing
import json,random,sqlite3,unittest
from unittest.mock import patch
from idol_manager.trade_policy import (acceptance_probability,coverage,quality,exchange,useful,
    evaluate,decision,season_slots)
from idol_manager.market_rules import market_salary
from idol_manager.market_service import public_people,process_market,MarketError
from idol_manager.ai_trades import generate,generate_ai_pairs,close_due
from tests import test_ai_pair_trades as pair_fixture
from tests import test_market as fixture

def person(identity,skills,role='second_team'):
    return dict(id=identity,skills=skills,age=20,annual=10**9,career_status=role)

class FormulaTests(unittest.TestCase):
    def test_acceptance_curve_and_bounds(self):
        for ratio,expected in ((.8,.14),(.9,.42),(1,.7),(1.1,.805),(1.2,.91),(0,0),(2,1)):
            self.assertAlmostEqual(acceptance_probability(ratio),expected)
    def test_unique_specialist_loss_and_team_specific_fit(self):
        special=person('s',[95,40,40,40,40,40,40,40],'first_team')
        incoming=person('i',[40,95,40,40,40,40,40,40])
        base=[person(str(i),[40,80,55,55,55,55,55,55],'first_team' if i<4 else 'second_team') for i in range(10)]
        unique=base+[special]
        redundant=base+[special,person('copy',special['skills'],'first_team')]
        self.assertGreater(exchange(unique,special,incoming)[0],exchange(redundant,special,incoming)[0])
        self.assertLess(exchange(unique,special,incoming)[2],exchange(redundant,special,incoming)[2])
        stable=[person(str(i),[80]*8,'first_team' if i<5 else 'second_team') for i in range(16)]
        self.assertFalse(useful(stable,stable[0],person('super',[100]*8)))

class TradePolicyTests(unittest.TestCase):
    setUpClass=classmethod(fixture.MarketTests.setUpClass.__func__)
    setUp=fixture.MarketTests.setUp
    rows=fixture.MarketTests.rows;day=fixture.MarketTests.day;dump=fixture.MarketTests.dump
    prepare=pair_fixture.AIPairTests.prepare
    def seed(self,seed):
        with closing(self.db.connect()) as c,c:c.execute('INSERT OR REPLACE INTO trade_rng VALUES (1,?)',(json.dumps(random.Random(seed).getstate()),))
    def proposal(self,n):
        ids=[self.rows("SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='second_team' ORDER BY person_id",(a,))[n][0] for a in ('ador','sm')]
        return self.market.propose_trade('ador','sm',dict(pro_a=ids[0],pro_b=ids[1],cash=0,trainees_a=[],trainees_b=[]),request_id='limit:'+str(n))
    def accept(self,identity):
        with patch('idol_manager.market_service._evaluate_trade',return_value=dict(action='accept')):
            return self.market.trade_reply(identity,'sm','accept',expected_version=1)

    def test_two_season_slots_reservations_release_and_next_season(self):
        self.day(7)
        ids=[self.proposal(n) for n in range(3)]
        self.accept(ids[0]);self.accept(ids[1])
        with self.assertRaisesRegex(MarketError,'최대 2회'):self.accept(ids[2])
        with closing(self.db.connect()) as c,c:
            self.assertEqual(season_slots(c,'ador'),2)
            c.execute("UPDATE market_trades SET status='expired' WHERE id=?",(ids[1],))
        self.accept(ids[2]);self.day(14)
        with closing(self.db.connect()) as c,c:process_market(c,14,run_ai=False)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM market_trades WHERE status='completed'"),[(2,)])
        before=self.dump()
        with closing(self.db.connect()) as c,c:process_market(c,14,run_ai=False)
        self.assertEqual(before,self.dump())
        with self.assertRaisesRegex(MarketError,'최대 2회'):self.proposal(5)
        # Reload uses only stored trade rows; the next season gets a fresh budget.
        from idol_manager.database import Database
        self.day(217)
        with closing(Database(self.path).connect()) as c:self.assertEqual(season_slots(c,'ador'),0)
        self.proposal(5)

    def test_half_cash_and_trainee_value_no_real_salary_and_persistent_roll(self):
        with closing(self.db.connect()) as c,c:
            c.execute('UPDATE abilities SET value=50,potential=100');c.execute('UPDATE idols SET age=20')
        identity=self.proposal(0)
        with closing(self.db.connect()) as c,c:
            t=c.execute('SELECT * FROM market_trades WHERE id=?',(identity,)).fetchone()
            terms=json.loads(c.execute('SELECT terms_json FROM market_trade_versions WHERE trade_id=?',(identity,)).fetchone()[0])
            people=list(public_people(c));extra=person('test-trainee',[50]*8,'trainee');extra['agency_id']='sm';people.append(extra)
            base=evaluate(c,t,'ador',terms,people)
            cash=evaluate(c,t,'ador',dict(terms,cash=-8000000),people)
            trainee=evaluate(c,t,'ador',dict(terms,trainees_b=['test-trainee']),people)
            self.assertAlmostEqual(base['probability'],.7)
            self.assertEqual(cash['receive']-base['receive'],4000000)
            self.assertEqual(trainee['receive']-base['receive'],market_salary([50]*8,20)*.5)
            before=c.execute('SELECT COUNT(*) FROM trade_decisions').fetchone()[0]
        with closing(self.db.connect()) as c,c:
            self.assertEqual(base,evaluate(c,t,'ador',terms,people))
            self.assertEqual(before,c.execute('SELECT COUNT(*) FROM trade_decisions').fetchone()[0])

    def test_one_weekly_search_per_ai_and_single_recipient_roll(self):
        self.prepare()
        with closing(self.db.connect()) as c,c:
            c.set_authorizer(lambda a,t,col,*_:sqlite3.SQLITE_DENY if a==sqlite3.SQLITE_READ and (col in ('potential','archetype') or t=='annual_secrets') else sqlite3.SQLITE_OK)
            generate_ai_pairs(c);generate(c)
        pairs=self.rows("SELECT agency_a,agency_b,status FROM market_trades WHERE id LIKE 'ai-pair:%'")
        self.assertIn(('jyp','sm','accepted_pending'),pairs)
        self.assertTrue(all(n<=1 for n, in self.rows('SELECT COUNT(*) FROM market_trades GROUP BY agency_a,created_day')))
        rolls=self.rows("SELECT decision_key,probability FROM trade_decisions WHERE decision_key LIKE 'search:%'")
        self.assertTrue(rolls);self.assertTrue(all(p==.15 for _,p in rolls))
        accepts=self.rows("SELECT decision_key FROM trade_decisions WHERE decision_key LIKE 'accept:ai-pair:%'")
        self.assertEqual(len(accepts),1);self.assertIn(':sm:',accepts[0][0])
        before=self.dump()
        with closing(self.db.connect()) as c,c:generate_ai_pairs(c);generate(c)
        self.assertEqual(before,self.dump())

    def test_failed_search_does_not_reroll_or_force_deal(self):
        self.prepare();self.seed(0) # Neither JYP nor SM passes its one search roll.
        with closing(self.db.connect()) as c,c:generate_ai_pairs(c)
        self.assertEqual(self.rows("SELECT id FROM market_trades WHERE id LIKE 'ai-pair:%'"),[])
        before=self.dump()
        with closing(self.db.connect()) as c,c:generate_ai_pairs(c)
        self.assertEqual(before,self.dump())

    def test_v20_upgrade_backup_preserves_existing_trade_and_game_rows(self):
        from idol_manager.database import Database
        identity=self.proposal(0)
        tables=('game_clock','agencies','abilities','draft_picks','roster_memberships','market_trades','market_trade_versions','finance_contracts')
        with closing(self.db.connect()) as c,c:
            before={t:[tuple(r) for r in c.execute('SELECT * FROM '+t)] for t in tables}
            c.execute('DROP TABLE training_choices');c.execute('DROP TABLE training_sheets')
            c.execute('DROP TABLE trade_decisions');c.execute('DROP TABLE trade_rng')
            c.execute('DROP INDEX trade_season_lookup');c.execute('PRAGMA user_version=20')
        db=Database(self.path);self.assertTrue(db.last_backup_path.is_file())
        with closing(db.connect()) as c:
            from idol_manager.migrations import SCHEMA_VERSION
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],SCHEMA_VERSION)
            for t in tables:self.assertEqual(before[t],[tuple(r) for r in c.execute('SELECT * FROM '+t)])
            self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())

    def test_invalid_roster_rejected_before_any_acceptance_roll(self):
        identity=self.proposal(0)
        with closing(self.db.connect()) as c,c:
            p=c.execute("SELECT person_id FROM roster_memberships WHERE agency_id='sm' AND career_status='first_team' LIMIT 1").fetchone()[0]
            c.execute('DELETE FROM squad_leaders WHERE person_id=?',(p,))
            c.execute("UPDATE roster_memberships SET career_status='fa',agency_id=NULL WHERE person_id=?",(p,))
        before=self.rows('SELECT COUNT(*) FROM trade_decisions')
        with self.assertRaises(MarketError):self.market.ai_trade_reply(identity,'sm')
        self.assertEqual(before,self.rows('SELECT COUNT(*) FROM trade_decisions'))
