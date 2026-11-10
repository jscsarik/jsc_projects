import os,unittest,json,sqlite3
os.environ.setdefault('QT_QPA_PLATFORM','windows')
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from idol_manager.ai_trades import generate,close_due,AITradeService
from idol_manager.market_service import MarketError,MarketService,process_market
from tests import test_market as fixture

class AITradeTests(unittest.TestCase):
    setUpClass=classmethod(fixture.MarketTests.setUpClass.__func__)
    setUp=fixture.MarketTests.setUp;day=fixture.MarketTests.day
    rows=fixture.MarketTests.rows;dump=fixture.MarketTests.dump;member=fixture.MarketTests.member
    def seed(self):
        # Fixed public skill examples ensure an actual improvement is available.
        self.day(7)
        with closing(self.db.connect()) as c,c:
            c.execute('UPDATE abilities SET value=80,potential=100')
            c.execute("UPDATE abilities SET value=60 WHERE person_id IN (SELECT person_id FROM roster_memberships WHERE agency_id='jyp')")
            c.execute("UPDATE abilities SET value=20 WHERE skill='vocal' AND person_id IN (SELECT person_id FROM roster_memberships WHERE agency_id='jyp')")
            c.execute("UPDATE abilities SET value=MIN(80,potential) WHERE person_id IN (SELECT person_id FROM roster_memberships WHERE agency_id='ador')")
            generate(c)
        self.api=AITradeService(self.db)
        return next(r for r in self.api.inbox() if r['agency_a']=='jyp')
    def test_monday_once_per_ai_and_no_hidden_reads(self):
        self.seed();before=self.rows('SELECT * FROM market_trades ORDER BY id')
        with closing(self.db.connect()) as c,c:
            c.set_authorizer(lambda a,t,col,*_:sqlite3.SQLITE_DENY if a==sqlite3.SQLITE_READ and (col in ('potential','archetype') or t=='annual_secrets') else sqlite3.SQLITE_OK)
            generate(c)
        self.assertEqual(before,self.rows('SELECT * FROM market_trades ORDER BY id'))
        self.assertTrue(all(n<=1 for n, in self.rows('SELECT COUNT(*) FROM market_trades t JOIN ai_trade_windows w ON w.trade_id=t.id GROUP BY t.agency_a,t.created_day')))
        self.day(8)
        with closing(self.db.connect()) as c,c:generate(c)
        self.assertEqual(before,self.rows('SELECT * FROM market_trades ORDER BY id'))
    def test_accept_waits_until_deadline_closing_and_idempotent(self):
        r=self.seed();terms=r['terms'];self.day(9)
        owners=self.rows('SELECT person_id,agency_id FROM roster_memberships ORDER BY person_id')
        self.api.respond(r['id'],'ador','accept',expected_revision=r['revision'])
        self.assertEqual(owners,self.rows('SELECT person_id,agency_id FROM roster_memberships ORDER BY person_id'))
        self.day(14)
        with closing(self.db.connect()) as c,c:process_market(c,14,run_ai=False)
        self.assertEqual(owners,self.rows('SELECT person_id,agency_id FROM roster_memberships ORDER BY person_id'))
        with closing(self.db.connect()) as c,c:close_due(c)
        self.assertEqual(self.rows('SELECT agency_id FROM roster_memberships WHERE person_id=?',(terms['pro_a'],))[0][0],'ador')
        self.assertEqual(self.rows('SELECT status FROM market_trades WHERE id=?',(r['id'],))[0][0],'completed')
        before=self.dump()
        with closing(self.db.connect()) as c,c:close_due(c)
        self.assertEqual(before,self.dump())
    def test_deadline_monday_accept_and_expire_other(self):
        r=self.seed();self.day(14)
        self.api.respond(r['id'],'ador','accept',expected_revision=r['revision'])
        with closing(self.db.connect()) as c,c:close_due(c)
        self.assertEqual(self.rows('SELECT status FROM market_trades WHERE id=?',(r['id'],))[0][0],'completed')
    def test_pending_expires_and_reject_persists(self):
        r=self.seed();self.day(14)
        with closing(self.db.connect()) as c,c:close_due(c)
        self.assertEqual(self.rows('SELECT status FROM market_trades WHERE id=?',(r['id'],))[0][0],'expired')
        with self.assertRaises(MarketError):self.api.respond(r['id'],'ador','accept',expected_revision=1)
    def test_reject_and_three_counter_rejections_keep_original_offer(self):
        r=self.seed();self.day(8)
        for n in range(3):
            with patch('idol_manager.market_service._evaluate_trade',return_value=dict(action='reject')):
                self.api.respond(r['id'],'ador','counter',terms=r['terms'],expected_revision=n+1)
        with self.assertRaises(MarketError):self.api.respond(r['id'],'ador','counter',terms=r['terms'],expected_revision=4)
        current=next(x for x in self.api.inbox() if x['id']==r['id'])
        self.assertEqual(current['terms'],r['terms']);self.assertEqual(current['counter_count'],3)
        self.api.respond(r['id'],'ador','reject',expected_revision=4)
        self.assertEqual(next(x for x in AITradeService(self.db).inbox() if x['id']==r['id'])['status'],'rejected')
    def test_accepted_counter_and_changed_owner_failure(self):
        r=self.seed();self.day(10)
        with patch('idol_manager.market_service._evaluate_trade',return_value=dict(action='accept')):
            self.api.respond(r['id'],'ador','counter',terms=r['terms'],expected_revision=1)
        self.assertEqual(next(x for x in self.api.inbox() if x['id']==r['id'])['status'],'accepted_pending')
        with closing(self.db.connect()) as c,c:c.execute("UPDATE roster_memberships SET agency_id=NULL,career_status='fa' WHERE person_id=?",(r['terms']['pro_a'],))
        self.day(14)
        with closing(self.db.connect()) as c,c:close_due(c)
        self.assertEqual(self.rows('SELECT status FROM market_trades WHERE id=?',(r['id'],))[0][0],'void')
    def test_chat_card_counter_editor_and_database_messages(self):
        r=self.seed()
        from idol_manager.ui.main_window import MainWindow
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QMessageBox
        w=MainWindow(self.service);self.addCleanup(w.close);w.resize(1440,1000);w.show();w.chat_button.click();QTest.qWait(50)
        chat=w.trade_chat;chat.agency.setCurrentIndex(chat.agency.findData('jyp'))
        self.assertTrue(chat.isVisible());self.assertIn('역제안 0/3',chat.summary.text())
        self.assertTrue(chat.accept.isEnabled());self.assertIn('새로운 트레이드',chat.messages.toPlainText())
        root=Path(__file__).resolve().parents[1]/'reports/ai_trades';root.mkdir(exist_ok=True);w.grab().save(str(root/'chat.png'))
        chat.counter.click();self.assertIs(w.pages.currentWidget(),w.market_page)
        self.assertEqual(w.market_page.other.currentData(),'jyp')
        self.day(8);w.market_page.reload();self.assertTrue(w.market_page.trade_reply_buttons[2].isEnabled())

    def test_close_failure_rolls_back_and_cash_moves_once(self):
        r=self.seed();terms=dict(r['terms'],cash=1000000)
        with patch('idol_manager.market_service._evaluate_trade',return_value=dict(action='accept')):
            self.api.respond(r['id'],'ador','counter',terms=terms,expected_revision=1)
        self.day(14);before=self.dump()
        with patch('idol_manager.market_service._history',side_effect=RuntimeError('disk failure')):
            with self.assertRaises(RuntimeError):
                with closing(self.db.connect()) as c,c:close_due(c)
        self.assertEqual(before,self.dump())
        cash=self.rows("SELECT funds_krw FROM agencies WHERE id='ador'")[0][0]
        with closing(self.db.connect()) as c,c:close_due(c)
        self.assertEqual(self.rows("SELECT funds_krw FROM agencies WHERE id='ador'")[0][0],cash+1000000)
        before=self.dump()
        with closing(self.db.connect()) as c,c:close_due(c)
        self.assertEqual(before,self.dump())

    def test_v19_migration_backups_and_preserves_old_trades(self):
        from idol_manager.database import Database
        with closing(self.db.connect()) as c,c:
            for table in ('training_choices','training_sheets','ai_trade_messages','ai_trade_windows','ai_trade_checks','trade_decisions','trade_rng'):c.execute('DROP TABLE '+table)
            c.execute('DROP INDEX trade_season_lookup')
            c.execute('PRAGMA user_version=19')
            before={t:[tuple(r) for r in c.execute('SELECT * FROM '+t)] for t in ('game_clock','abilities','market_trades','market_trade_versions','finance_contracts','agencies','draft_picks')}
        db=Database(self.path);self.assertTrue(db.last_backup_path.is_file())
        with closing(db.connect()) as c:
            from idol_manager.migrations import SCHEMA_VERSION
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],SCHEMA_VERSION)
            for t,rows in before.items():self.assertEqual(rows,[tuple(r) for r in c.execute('SELECT * FROM '+t)],t)
            self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())

    def test_calendar_closes_on_deadline_monday_not_on_entry(self):
        from idol_manager.calendar_service import CalendarService
        r=self.seed()
        leader={p for p, in self.rows("SELECT person_id FROM squad_leaders WHERE agency_id='ador'")}
        person=next(p for p, in self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='second_team'") if p not in leader)
        terms=dict(r['terms'],pro_b=person);terms.pop('contract_b',None)
        with patch('idol_manager.market_service._evaluate_trade',return_value=dict(action='accept')):
            self.api.respond(r['id'],'ador','counter',terms=terms,expected_revision=1)
        self.day(14)
        # Only the match backlog is bypassed in this focused fixture; date-close
        # transaction, market settlement and payroll hooks are real.
        with patch.object(CalendarService,'_pending',return_value=0):
            result=CalendarService(self.db).advance_day(expected_absolute_day=14)
        self.assertEqual(result.absolute_day,15)
        self.assertEqual(self.rows('SELECT executed_day FROM market_trades WHERE id=?',(r['id'],))[0][0],14)
