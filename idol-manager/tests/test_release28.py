"""Read-only query cancellation must not block close or hide real failures."""
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import patch
import sqlite3,threading,time,unittest
from tests import test_records as fixture
from idol_manager.records_service import RecordsService
from idol_manager.records_read import cancellation_scope
from idol_manager.ui.records_queries import QueryJob,QuerySignals
HEAVY='WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n WHERE x<100000000) SELECT sum(x) FROM n'

class Release28Tests(unittest.TestCase):
    setUpClass=classmethod(fixture.RecordsTests.setUpClass.__func__)
    setUp=fixture.RecordsTests.setUp
    dump=fixture.RecordsTests.dump
    def test_cancel_interrupts_only_scoped_read_and_preserves_database(self):
        api=RecordsService(self.db);cancel=threading.Event();entered=threading.Event();connections=[];errors=[];before=self.dump()
        def work():
            try:
                with cancellation_scope(cancel),api.read() as c:
                    connections.append(c);entered.set();c.execute(HEAVY).fetchone()
            except sqlite3.OperationalError as e:errors.append(str(e))
        worker=threading.Thread(target=work);worker.start();self.assertTrue(entered.wait(3))
        cancel.set();worker.join(2)
        cancelled_in_time=not worker.is_alive()
        if worker.is_alive():connections[0].interrupt();worker.join(3)
        self.assertTrue(cancelled_in_time,'SQLite did not stop cooperatively within two seconds')
        self.assertFalse(worker.is_alive());self.assertTrue(errors);self.assertIn('interrupt',errors[0])
        with api.read() as c:self.assertEqual(c.execute('SELECT 1').fetchone()[0],1)
        self.assertEqual(before,self.dump())
    def test_cancel_before_read_does_not_leak_scope_to_next_query(self):
        api=RecordsService(self.db);event=threading.Event();event.set()
        with cancellation_scope(event),self.assertRaises(sqlite3.OperationalError):
            with api.read():pass
        with api.read() as c:
            self.assertEqual(c.execute('SELECT 2').fetchone()[0],2)
            with self.assertRaises(sqlite3.OperationalError):c.execute('DELETE FROM people')
    def test_worker_cancellation_and_real_error_are_distinct(self):
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([]);values=[];signals=QuerySignals();signals.finished.connect(lambda *v:values.append(v))
        bad=SimpleNamespace(revision=lambda:('same',),league=lambda:(_ for _ in ()).throw(ValueError('real failure')))
        job=QueryJob(bad,1,[('league',(),{})],signals);job.run();app.processEvents()
        self.assertEqual(values[-1][2],'real failure')
        job=QueryJob(bad,2,[('league',(),{})],signals);job.cancelled.set();job.run();app.processEvents()
        self.assertIsNone(values[-1][2])
    def test_close_during_sql_cancels_worker_and_leaves_no_partial_cache(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from idol_manager.service import GameService
        from idol_manager.ui.main_window import MainWindow
        app=QApplication.instance() or QApplication([]);service=GameService(self.root,self.path)
        w=MainWindow(service);self.addCleanup(w.close);w.show();w.show_records();page=w.records_page
        end=time.monotonic()+5
        while page.rendered_generation!=page.query_generation and time.monotonic()<end:QTest.qWait(10);time.sleep(.002)
        entered=threading.Event();before=self.dump()
        def slow(**kwargs):
            with service.records.read() as c:entered.set();c.execute(HEAVY).fetchone()
            return []
        with patch.object(service.records,'players',side_effect=slow):
            page.api.values.clear();page.tabs.setCurrentIndex(1)
            end=time.monotonic()+3
            while not entered.is_set() and time.monotonic()<end:QTest.qWait(10);time.sleep(.002)
            self.assertTrue(entered.is_set());started=time.perf_counter();w.close()
            self.assertLess(time.perf_counter()-started,.8);self.assertEqual(page.query_pool.activeThreadCount(),0)
            self.assertFalse(page.query_jobs);self.assertFalse(any(k[0]=='players' for k in page.api.values))
        self.assertEqual(before,self.dump())

if __name__=='__main__':unittest.main()
