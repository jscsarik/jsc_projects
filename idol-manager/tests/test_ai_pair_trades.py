"""Focused weekly AI-to-AI checks, synthetic disposable saves only."""
from contextlib import closing
import json,sqlite3,unittest,random
from unittest.mock import patch
from idol_manager.ai_trades import generate_ai_pairs,close_due,terms_of
from idol_manager.market_service import process_market,active_contract
from tests import test_market as fixture

class AIPairTests(unittest.TestCase):
    setUpClass=classmethod(fixture.MarketTests.setUpClass.__func__)
    setUp=fixture.MarketTests.setUp;day=fixture.MarketTests.day
    rows=fixture.MarketTests.rows;dump=fixture.MarketTests.dump
    def prepare(self):
        self.day(7)
        with closing(self.db.connect()) as c,c:
            c.execute('INSERT OR REPLACE INTO trade_rng VALUES (1,?)',(json.dumps(random.Random(4).getstate()),))
            c.execute('UPDATE abilities SET value=80,potential=100')
            # JYP needs vocal; SM needs dance. Their unused specialists are
            # useful to the other team. Contract/age/health terms are equal.
            for agency,weak,strong in (('jyp','vocal','dance'),('sm','dance','vocal')):
                c.execute("UPDATE abilities SET value=50 WHERE person_id IN (SELECT person_id FROM roster_memberships WHERE agency_id=?)",(agency,))
                c.execute("UPDATE abilities SET value=20 WHERE skill=? AND person_id IN (SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='first_team')",(weak,agency))
                c.execute("UPDATE abilities SET value=80 WHERE skill=? AND person_id IN (SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='first_team')",(strong,agency))
                c.execute("UPDATE abilities SET value=20 WHERE skill=? AND person_id IN (SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='second_team')",(weak,agency))
                c.execute("UPDATE abilities SET value=80 WHERE skill=? AND person_id IN (SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='second_team')",(strong,agency))
            c.execute("UPDATE idols SET age=20,health=90 WHERE person_id IN (SELECT person_id FROM roster_memberships WHERE agency_id IN ('jyp','sm'))")
    def generate(self):
        with closing(self.db.connect()) as c,c:generate_ai_pairs(c)
    def pair(self):return self.rows("SELECT id FROM market_trades WHERE id LIKE 'ai-pair:%'")[0][0]

    def test_monday_mutual_agreement_no_hidden_data_and_no_immediate_move(self):
        self.prepare();before=self.rows('SELECT * FROM roster_memberships ORDER BY person_id')
        with closing(self.db.connect()) as c,c:
            c.set_authorizer(lambda a,t,col,*_:sqlite3.SQLITE_DENY if a==sqlite3.SQLITE_READ and (col in ('potential','archetype') or t=='annual_secrets') else sqlite3.SQLITE_OK)
            generate_ai_pairs(c)
        self.assertEqual(self.rows("SELECT agency_a,agency_b,status FROM market_trades WHERE id LIKE 'ai-pair:%'"),[('jyp','sm','accepted_pending')])
        self.assertEqual(before,self.rows('SELECT * FROM roster_memberships ORDER BY person_id'))
        self.assertEqual(self.rows('SELECT deadline_day FROM ai_trade_windows WHERE trade_id=?',(self.pair(),)),[(14,)])
        before=self.dump();self.generate();self.assertEqual(before,self.dump())
        self.day(8);before=self.dump();self.generate();self.assertEqual(before,self.dump())

    def test_next_monday_settlement_contracts_counts_and_idempotency(self):
        self.prepare();self.generate();identity=self.pair()
        with closing(self.db.connect()) as c:
            t=c.execute('SELECT * FROM market_trades WHERE id=?',(identity,)).fetchone();terms=terms_of(c,t)
            contracts={p:dict(active_contract(c,p)) for p in (terms['pro_a'],terms['pro_b'])}
        self.day(7)
        with closing(self.db.connect()) as c,c:close_due(c)
        self.assertEqual(self.rows('SELECT status FROM market_trades WHERE id=?',(identity,)),[('accepted_pending',)])
        self.day(14)
        with closing(self.db.connect()) as c,c:process_market(c,14,run_ai=False)
        self.assertEqual(self.rows('SELECT status FROM market_trades WHERE id=?',(identity,)),[('accepted_pending',)])
        with closing(self.db.connect()) as c,c:close_due(c)
        self.assertEqual(self.rows('SELECT status FROM market_trades WHERE id=?',(identity,)),[('completed',)])
        for person,owner in ((terms['pro_a'],'sm'),(terms['pro_b'],'jyp')):
            self.assertEqual(self.rows('SELECT agency_id FROM roster_memberships WHERE person_id=?',(person,)),[(owner,)])
            with closing(self.db.connect()) as c:
                contract=active_contract(c,person)
                for k in ('annual_krw','end_day','end_season','root_id'):self.assertEqual(contract[k],contracts[person][k])
        self.assertTrue(all(n==5 for n, in self.rows("SELECT COUNT(*) FROM roster_memberships WHERE agency_id IN ('jyp','sm') AND career_status='first_team' GROUP BY agency_id")))
        self.assertEqual(len(self.rows("SELECT * FROM market_history WHERE kind='trade' AND related_id=?",(identity,))),2)
        before=self.dump()
        with closing(self.db.connect()) as c,c:close_due(c)
        self.assertEqual(before,self.dump())

    def test_existing_reservations_exclude_players_and_changed_owner_fails_atomically(self):
        self.prepare();self.generate();identity=self.pair()
        with closing(self.db.connect()) as c:
            terms=terms_of(c,c.execute('SELECT * FROM market_trades WHERE id=?',(identity,)).fetchone())
        # A new Monday must not use either reserved player in another proposal.
        self.day(14);self.generate()
        rows=self.rows("SELECT v.terms_json FROM market_trade_versions v JOIN market_trades t ON t.id=v.trade_id WHERE t.id LIKE 'ai-pair:%' AND t.status='accepted_pending'")
        ids=[p for raw, in rows for p in (json.loads(raw)['pro_a'],json.loads(raw)['pro_b'])]
        self.assertEqual(len(ids),len(set(ids)))
        with closing(self.db.connect()) as c,c:c.execute("UPDATE roster_memberships SET agency_id=NULL,career_status='fa' WHERE person_id=?",(terms['pro_a'],))
        owners=self.rows('SELECT * FROM roster_memberships ORDER BY person_id')
        with closing(self.db.connect()) as c,c:close_due(c)
        self.assertEqual(self.rows('SELECT status FROM market_trades WHERE id=?',(identity,)),[('void',)])
        self.assertEqual(owners,self.rows('SELECT * FROM roster_memberships ORDER BY person_id'))

    def test_insufficient_cash_and_storage_failure_leave_no_partial_exchange(self):
        self.prepare();self.generate();identity=self.pair();self.day(14)
        before=self.dump()
        with patch('idol_manager.market_service._history',side_effect=RuntimeError('write failed')):
            with self.assertRaises(RuntimeError):
                with closing(self.db.connect()) as c,c:close_due(c)
        self.assertEqual(before,self.dump())
        with closing(self.db.connect()) as c,c:
            row=c.execute('SELECT terms_json FROM market_trade_versions WHERE trade_id=?',(identity,)).fetchone();terms=json.loads(row[0]);terms['cash']=10**15
            c.execute('UPDATE market_trade_versions SET terms_json=? WHERE trade_id=?',(json.dumps(terms),identity))
        before=self.rows('SELECT * FROM roster_memberships ORDER BY person_id')
        with closing(self.db.connect()) as c,c:close_due(c)
        self.assertEqual(self.rows('SELECT status FROM market_trades WHERE id=?',(identity,)),[('void',)])
        self.assertEqual(before,self.rows('SELECT * FROM roster_memberships ORDER BY person_id'))

    def test_no_need_no_trade(self):
        self.prepare()
        with closing(self.db.connect()) as c,c:c.execute('UPDATE abilities SET value=80')
        self.generate();self.assertEqual(self.rows("SELECT id FROM market_trades WHERE id LIKE 'ai-pair:%'"),[])

    def test_final_first_team_count_is_rechecked(self):
        self.prepare();self.generate();identity=self.pair();self.day(14)
        with closing(self.db.connect()) as c,c:
            terms=terms_of(c,c.execute('SELECT * FROM market_trades WHERE id=?',(identity,)).fetchone())
            person=c.execute("SELECT person_id FROM roster_memberships WHERE agency_id='jyp' AND career_status='first_team' AND person_id!=? LIMIT 1",(terms['pro_a'],)).fetchone()[0]
            c.execute('DELETE FROM squad_leaders WHERE person_id=?',(person,))
            c.execute("UPDATE roster_memberships SET agency_id=NULL,career_status='fa' WHERE person_id=?",(person,))
        before=self.rows('SELECT * FROM roster_memberships ORDER BY person_id')
        with closing(self.db.connect()) as c,c:close_due(c)
        self.assertEqual(self.rows('SELECT status FROM market_trades WHERE id=?',(identity,)),[('void',)])
        self.assertEqual(before,self.rows('SELECT * FROM roster_memberships ORDER BY person_id'))
