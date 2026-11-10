"""Finance rules and transactional integrations, using disposable saves only."""
from contextlib import closing
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import json,sqlite3,unittest,subprocess,sys
from idol_manager.service import GameService
from idol_manager.database import Database
from idol_manager.finance_service import (FinanceService,FinanceError,salary_parts,role_week,settle_week,
    initialize_finance,close_season,begin,income,obligation,cash,debt)
from idol_manager.development_service import capture_day
from idol_manager.league import standings
from tests import test_match_ui as fixture

class FinanceTests(unittest.TestCase):
    setUpClass=classmethod(fixture.MatchUITests.setUpClass.__func__)
    def setUp(self):
        fixture.MatchUITests.setUp(self);self.service=GameService(self.base,database_path=self.path)
        self.db=self.service.database;self.finance=self.service.finance
    def rows(self,sql,args=()):
        with closing(self.db.connect()) as c:return [tuple(r) for r in c.execute(sql,args)]
    def dump(self):
        with closing(self.db.connect()) as c:return list(c.iterdump())
    def week(self,w,season=1):
        end=(season-1)*217+w*7-1
        with closing(self.db.connect()) as c,c:
            c.execute('BEGIN IMMEDIATE')
            for d in range(end-6,end+1):capture_day(c,d)
            c.execute('UPDATE game_clock SET absolute_day=?',(end,));settle_week(c,end)
    def test_new_initial_funds_10_agencies_no_double_grant_on_read_restart(self):
        self.assertEqual(self.rows('SELECT COUNT(*) FROM agencies WHERE funds_krw=1000000000'),[(10,)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM finance_ledger WHERE kind='initial_funds'"),[(10,)])
        before=self.dump();self.finance.dashboard('ador');self.finance.ledger('ador');self.finance.contracts('ador');self.finance.payroll('ador');Database(self.path)
        self.assertEqual(before,self.dump())
    def test_rounding_six_payments_exact_annual_and_offsets(self):
        self.assertEqual(salary_parts(60000000,1,0,0),(10000000,0,0,10000000))
        self.assertEqual(salary_parts(60000000,1,3,0)[3],11000000)
        self.assertEqual(salary_parts(60000000,1,0,3)[3],9000000)
        self.assertEqual(salary_parts(60000000,1,3,3)[3],10000000)
        self.assertEqual(sum(salary_parts(31000000,i,0,0)[0] for i in range(1,7)),31000000)
        self.assertEqual(salary_parts(30030000,1,0,0)[0],5010000)
    def test_role_majority_and_ties_and_forced_second(self):
        priority=['first_team','second_team','trainee']
        self.assertEqual(role_week(['second_team']*4+['first_team']*3,priority),'second_team')
        self.assertEqual(role_week(['second_team']*3+['first_team']*4,priority),'first_team')
        self.assertEqual(role_week(['second_team','first_team'],priority),'first_team')
    def test_weekly_sponsor_training_and_no_duplicate(self):
        self.week(1)
        self.assertEqual(self.rows("SELECT COUNT(*),SUM(amount) FROM finance_ledger WHERE kind='weekly_sponsor'"),[(10,100000000)])
        self.assertEqual(self.rows("SELECT COUNT(*),SUM(amount) FROM finance_ledger WHERE kind='second_training'"),[(110,11000000)])
        self.assertEqual(self.rows("SELECT funds_krw FROM agencies WHERE id='ador'"),[(1008900000,)])
        before=self.dump();self.week(1);self.assertEqual(before,self.dump())
        self.assertFalse(self.rows("SELECT 1 FROM finance_ledger WHERE kind IN ('focus_training','match_prize')"))
    def test_salary_only_six_regular_cycles_and_24_sponsors(self):
        for w in range(1,25):self.week(w)
        self.assertEqual(self.rows("SELECT SUM(amount) FROM finance_ledger WHERE agency_id='ador' AND kind='weekly_sponsor'"),[(240000000,)])
        self.assertEqual(self.rows("SELECT DISTINCT cycle FROM finance_payroll ORDER BY cycle"),[(i,) for i in range(1,7)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM finance_payroll'),[(960,)])
        before=self.rows('SELECT COUNT(*) FROM finance_ledger')
        self.week(25);self.week(28);self.assertEqual(before,self.rows('SELECT COUNT(*) FROM finance_ledger'))
    def test_registered_first_not_actual_activity_and_second_reduction(self):
        for w in range(1,5):self.week(w)
        rows=self.finance.payroll('ador')
        self.assertEqual(len(rows),16)
        self.assertTrue(all(r['first_weeks']==0 and r['bonus_krw']==0 for r in rows))
        self.assertEqual(sum(r['reduction_krw']>0 for r in rows),11)
        self.assertTrue(all(r['due_krw']==r['paid_krw'] for r in rows))
    def test_real_three_week_first_bonus_and_second_offset_survive_injury(self):
        from idol_manager.finance_service import payroll_activity,load_rules
        people=[r[0] for r in self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='first_team' ORDER BY person_id")]
        person=people[0]
        for week in (1,2,3):
            with closing(self.db.connect()) as c,c:
                c.execute('UPDATE game_clock SET absolute_day=?',((week-1)*7+2,))
                c.execute('UPDATE player_conditions SET injured=0')
            self.service.calendar.ensure_current_schedule()
            match=next(f for f in self.service.matches.fixtures() if f.player_participates)
            needed=self.service.matches.selection(match.id).selection_count
            self.service.matches.play(match.id,lineups={'ador':tuple(people[:needed])})
        with closing(self.db.connect()) as c,c:
            for d in range(28):capture_day(c,d)
            c.execute("UPDATE development_days SET role='second_team' WHERE person_id=? AND absolute_day%7!=2",(person,))
            c.execute('UPDATE player_conditions SET injured=1 WHERE person_id=?',(person,))
            first,second,facts=payroll_activity(c,person,'ador',0,27,load_rules())
            self.assertEqual((first,second),(3,4))
            settle_week(c,27)
        row=next(r for r in self.finance.payroll('ador') if r['person_id']==person)
        self.assertEqual((row['first_weeks'],row['bonus_krw'],row['reduction_krw'],row['due_krw']),(3,500000,500000,5000000))

    def test_insolvency_debt_and_once_per_agency_cycle_points(self):
        with closing(self.db.connect()) as c,c:c.execute('UPDATE agencies SET funds_krw=0')
        for w in range(1,5):self.week(w)
        self.assertEqual(self.rows('SELECT COUNT(*) FROM finance_points'),[(10,)])
        self.assertTrue(all(p['points']==-2 for p in self.service.matches.standings(1)))
        self.assertTrue(self.rows('SELECT 1 FROM finance_debts WHERE outstanding_krw>0 LIMIT 1'))
        self.assertFalse(self.rows('SELECT 1 FROM agencies WHERE funds_krw<0'))
        before=self.dump();self.week(4);self.assertEqual(before,self.dump())
        self.week(5);self.assertEqual(self.rows('SELECT COUNT(*) FROM finance_points'),[(10,)])
        with self.assertRaises(FinanceError):self.finance.validate_spend('ador',1)
    def test_income_repayment_tracks_salary_and_leaves_only_surplus_cash(self):
        self.week(4)
        with closing(self.db.connect()) as c,c:
            c.execute('BEGIN IMMEDIATE');c.execute("UPDATE agencies SET funds_krw=0 WHERE id='ador'")
            s=begin(c,'ador',34,'weekly');paid,unpaid=obligation(c,s,'fixed_obligation',15000000)
            self.assertEqual((paid,unpaid),(0,15000000));income(c,s,'weekly_sponsor',10000000)
            self.assertEqual((cash(c,'ador'),debt(c,'ador')),(0,5000000))
            income(c,s,'season_bonus',10000000)
            self.assertEqual((cash(c,'ador'),debt(c,'ador')),(5000000,0))
    def test_salary_debt_repayment_updates_paid_totals_without_new_points(self):
        with closing(self.db.connect()) as c,c:c.execute('UPDATE agencies SET funds_krw=0')
        self.week(4);before=sum(r['due_krw']-r['paid_krw'] for r in self.finance.payroll('ador'))
        self.week(5);after=sum(r['due_krw']-r['paid_krw'] for r in self.finance.payroll('ador'))
        self.assertGreater(before,after);self.assertEqual(self.rows('SELECT COUNT(*) FROM finance_points'),[(10,)])
    def test_partial_cash_payment_500_to_2000_obligation(self):
        with closing(self.db.connect()) as c,c:
            c.execute('BEGIN IMMEDIATE');c.execute("UPDATE agencies SET funds_krw=5000000 WHERE id='ador'")
            s=begin(c,'ador',6,'weekly');self.assertEqual(obligation(c,s,'salary_test',20000000),(5000000,15000000))
            self.assertEqual((cash(c,'ador'),debt(c,'ador')),(0,15000000))
    def test_week_atomic_rollback_on_any_agency_error(self):
        before=self.dump()
        from idol_manager import finance_service as module
        original=module.journal;calls=[]
        def fail_after_first_agency(*args,**kwargs):
            calls.append(1)
            if len(calls)==15:raise RuntimeError('disk write failed')
            return original(*args,**kwargs)
        with patch('idol_manager.finance_service.journal',side_effect=fail_after_first_agency):
            with self.assertRaises(RuntimeError):self.week(1)
        self.assertEqual(before,self.dump())
    def test_concurrent_same_week_once(self):
        with closing(self.db.connect()) as c,c:
            for d in range(7):capture_day(c,d)
        def run():
            with closing(self.db.connect()) as c,c:c.execute('BEGIN IMMEDIATE');settle_week(c,6)
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:run(),range(2)))
        self.assertEqual(self.rows("SELECT COUNT(*) FROM finance_settlements WHERE kind='weekly'"),[(10,)])
    def test_cash_journal_reconciles_and_adjustments_not_income(self):
        for w in range(1,9):self.week(w)
        for a in self.service.agencies():
            entries=self.finance.ledger(a.id);self.assertEqual(1000000000+sum(r['cash_delta'] for r in entries),a.funds_krw)
            self.assertEqual(sum(r['debt_delta'] for r in entries),self.finance.dashboard(a.id)['debt'])
        self.assertTrue(all(r['cash_delta']==0 and r['amount']<0 for r in self.finance.ledger('ador') if r['kind']=='second_reduction'))
    def test_restart_persists_cash_debt_payroll_journal(self):
        self.week(4);before=self.dump();other=FinanceService(Database(self.path))
        self.assertEqual(self.finance.payroll('ador'),other.payroll('ador'));self.assertEqual(self.finance.ledger('ador'),other.ledger('ador'));self.assertEqual(before,self.dump())
    def test_trainee_care_actual_days_and_salary_no_invented_payment(self):
        person=self.rows("SELECT person_id FROM roster_memberships WHERE career_status='unassigned' LIMIT 1")[0][0]
        with closing(self.db.connect()) as c,c:c.execute("UPDATE roster_memberships SET agency_id='ador',career_status='trainee' WHERE person_id=?",(person,))
        self.week(1);self.week(2)
        self.assertEqual(self.rows("SELECT SUM(amount) FROM finance_ledger WHERE person_id=? AND kind='trainee_care'",(person,)),[(200000,)])
        self.assertFalse(self.rows('SELECT 1 FROM finance_payroll WHERE person_id=?',(person,)))
    def test_sale_only_candidates_buyer_cash_and_capacity_no_fake_transfer(self):
        with closing(self.db.connect()) as c,c:
            s=begin(c,'ador',6,'weekly');c.execute("UPDATE agencies SET funds_krw=0 WHERE id='ador'");obligation(c,s,'salary_test',100000000)
        before=self.dump();candidates=self.finance.sale_candidates('ador');self.assertEqual(len(candidates),16)
        self.assertTrue(all(not r['buyers'] and not r['executable'] for r in candidates));self.assertEqual(before,self.dump())
        # Free a real roster place in this disposable scenario, without inventing a sale.
        person=self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='jyp' AND career_status='second_team' LIMIT 1")[0][0]
        with closing(self.db.connect()) as c,c:c.execute("UPDATE roster_memberships SET career_status='fa',agency_id=NULL WHERE person_id=?",(person,))
        self.assertTrue(all('jyp' in r['buyers'] for r in self.finance.sale_candidates('ador')))
        with closing(self.db.connect()) as c,c:c.execute("UPDATE agencies SET funds_krw=0 WHERE id='jyp'")
        self.assertTrue(all('jyp' not in r['buyers'] for r in self.finance.sale_candidates('ador')))
    def test_ai_budget_public_only_and_same_money_rules(self):
        original=self.db.connect
        def connect():
            c=original();c.set_authorizer(lambda action,table,col,*_:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_READ and (table=='abilities' or col in ('potential','archetype')) else sqlite3.SQLITE_OK);return c
        with patch.object(self.db,'connect',side_effect=connect):
            self.assertLessEqual(self.finance.budget('ador','stable'),self.finance.budget('ador','balanced'))
            self.assertLessEqual(self.finance.budget('ador','balanced'),self.finance.budget('ador','aggressive'))
            self.finance.sale_candidates('ador');self.finance.dashboard('jyp')
    def test_contract_terms_cannot_rewrite_paid_history(self):
        self.week(4);before=self.dump()
        with closing(self.db.connect()) as c,c:
            with self.assertRaises(sqlite3.IntegrityError):c.execute('UPDATE finance_contracts SET annual_krw=60000000')
        self.assertEqual(before,self.dump())
    def test_calendar_finance_rollback_preserves_day_and_growth(self):
        # All real Wednesday fixtures are completed in a disposable DB, then
        # arrange a quiet Sunday to exercise the transaction boundary itself.
        with closing(self.db.connect()) as c,c:
            c.execute("UPDATE scheduled_matches SET status='completed' WHERE week=1")
            c.execute('UPDATE game_clock SET absolute_day=6')
        before=self.dump()
        with patch('idol_manager.finance_service.journal',side_effect=ValueError('accounting failure')):
            with self.assertRaises(ValueError):self.service.calendar.advance_day(expected_absolute_day=6)
        self.assertEqual(before,self.dump())
        self.service.calendar.advance_day(expected_absolute_day=6)
        self.assertEqual(self.rows('SELECT absolute_day FROM game_clock'),[(7,)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM finance_ledger WHERE kind='weekly_sponsor'"),[(10,)])

    def test_bonus_only_after_final_completion_once_and_debt_first(self):
        with closing(self.db.connect()) as c,c:
            close_season(c,1,183)
            self.assertFalse(c.execute("SELECT 1 FROM finance_settlements WHERE kind='bonus'").fetchone())
            c.execute("INSERT INTO season_finals(season,status,frozen_json,standings_json) VALUES (1,'completed','{}','[]')")
            s=begin(c,'ador',182,'weekly');c.execute("UPDATE agencies SET funds_krw=0 WHERE id='ador'");obligation(c,s,'prior_obligation',15000000)
            close_season(c,1,183)
            self.assertEqual((cash(c,'ador'),debt(c,'ador')),(985000000,0))
        before=self.dump()
        with closing(self.db.connect()) as c,c:close_season(c,1,188)
        self.assertEqual(before,self.dump())
        self.assertEqual(self.rows("SELECT COUNT(*) FROM finance_ledger WHERE kind='season_bonus'"),[(10,)])

    def test_process_exit_before_commit_has_no_partial_writes(self):
        before=self.dump()
        code="""import os,sys
from pathlib import Path
from idol_manager.database import Database
from idol_manager.finance_service import settle_week
from idol_manager.development_service import capture_day
c=Database(Path(sys.argv[1])).connect()
c.execute('BEGIN IMMEDIATE')
for d in range(7):capture_day(c,d)
settle_week(c,6)
os._exit(57)
"""
        result=subprocess.run([sys.executable,'-c',code,str(self.path)],capture_output=True)
        self.assertEqual(result.returncode,57,result.stderr.decode(errors='replace'))
        self.assertEqual(before,self.dump())

if __name__=='__main__':unittest.main()
