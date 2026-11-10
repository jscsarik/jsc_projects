import os
os.environ.setdefault('QT_QPA_PLATFORM','windows')
from pathlib import Path
import unittest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from idol_manager.ui.awards_page import record_top_ten,CANDIDATE_ROLE
from idol_manager.ui.main_window import MainWindow
from tests import test_awards as fixture

class TopTenTests(unittest.TestCase):
    def test_attempt_boundary_and_success_order(self):
        records=[fixture.record(str(i)) for i in range(12)]
        for i,r in enumerate(records):r['skills']['vocal']={'attempts':120-i,'successes':i}
        result=record_top_ten(records,'vocal')
        self.assertEqual([r['id'] for r in result],['4','3','2','1','0','5','6','7','8','9'])
        self.assertEqual(record_top_ten([], 'vocal'),[])

    def test_success_rate_not_success_count_and_lower_five_by_attempts(self):
        records=[fixture.record(str(i)) for i in range(12)]
        for i,r in enumerate(records):r['skills']['vocal']={'attempts':100-i,'successes':10}
        records[0]['skills']['vocal']['successes']=60
        records[1]['skills']['vocal']['successes']=60
        records[5]['skills']['vocal']['successes']=95
        result=record_top_ten(records,'vocal')
        self.assertEqual([r['id'] for r in result[:2]],['1','0'])
        self.assertEqual([r['id'] for r in result[5:]],['5','6','7','8','9'])

    def test_saved_official_boundary_tie_is_preserved(self):
        records=[fixture.record(str(i)) for i in range(12)]
        official=[records[i] for i in (7,9,11,5,3)]
        result=record_top_ten(records,'vocal',official_candidates=official)
        self.assertEqual([r['id'] for r in result[:5]],['7','9','11','5','3'])

    def test_winning_idol_order_and_no_mutation(self):
        records=[fixture.record(str(i),wins=i) for i in range(12)]
        self.assertEqual([r['winning_idol'] for r in record_top_ten(records,'winning_idol')],list(reversed(range(2,12))))
        self.assertEqual([r['winning_idol'] for r in records],list(range(12)))

class TopTenUITests(unittest.TestCase):
    setUpClass=classmethod(fixture.AwardsTests.setUpClass.__func__)
    day=fixture.AwardsTests.day;rows=fixture.AwardsTests.rows;dump=fixture.AwardsTests.dump
    complete_fixture=fixture.AwardsTests.complete_fixture
    def setUp(self):fixture.AwardsTests.setUp(self)

    def test_arrows_and_read_only(self):
        self.complete_fixture();before=self.dump()
        w=MainWindow(self.service);self.addCleanup(w.close);w.resize(1440,900);w.show();w.show_awards()
        page=w.awards_page;page.tabs.setCurrentIndex(2);QTest.qWait(80)
        self.assertEqual(page.record_kind.count(),9)
        self.assertEqual(page.table.model().columnCount(),5)
        QTest.mouseClick(page.record_next,Qt.MouseButton.LeftButton)
        self.assertEqual(page.record_kind.currentData(),'vocal')
        self.assertEqual(page.table.model().columnCount(),6)
        self.assertLessEqual(page.table.model().rowCount(),10)
        for row in range(page.table.rowCount()):self.assertTrue(page.table.item(row,0).data(CANDIDATE_ROLE))
        QTest.qWait(60)
        widths=[page.table.columnWidth(c) for c in range(6)]
        self.assertLessEqual(max(widths)-min(widths),1)
        self.assertGreaterEqual(sum(widths),page.table.viewport().width()-6)
        page.record_kind.setCurrentIndex(2);QTest.qWait(60)
        self.assertEqual(widths,[page.table.columnWidth(c) for c in range(6)])
        page.record_kind.setCurrentIndex(1)
        QTest.mouseClick(page.record_previous,Qt.MouseButton.LeftButton)
        self.assertEqual(page.record_kind.currentData(),'winning_idol')
        for row in range(page.table.rowCount()):self.assertFalse(page.table.item(row,0).data(CANDIDATE_ROLE))
        QTest.mouseClick(page.record_previous,Qt.MouseButton.LeftButton)
        self.assertEqual(page.record_kind.currentData(),'leadership')
        QTest.qWait(60)
        # A full ten-row display proves only the five candidates are outlined.
        records=[fixture.record('display'+str(i)) for i in range(12)]
        for i,r in enumerate(records):
            r['name']='후보 '+str(i+1);r['skills']['vocal']={'attempts':100-i*3,'successes':60-i}
        page.data['records']=records;page.data['awards']=[];page.record_kind.setCurrentIndex(1);page.render_records();QTest.qWait(60)
        for row in range(10):self.assertEqual(bool(page.table.item(row,0).data(CANDIDATE_ROLE)),row<5)
        page.table.sortItems(4,Qt.SortOrder.AscendingOrder);page.render_records();QTest.qWait(40)
        self.assertEqual(page.table.item(0,0).text(),'1')
        for row in range(10):self.assertEqual(bool(page.table.item(row,0).data(CANDIDATE_ROLE)),row<5)
        preview=Path(__file__).resolve().parents[1]/'reports/awards_candidates';preview.mkdir(exist_ok=True)
        w.grab().save(str(preview/'screen.png'))
        root=Path(__file__).resolve().parents[1]/'reports'/'awards_top_ten'
        root.mkdir(parents=True,exist_ok=True);w.grab().save(str(root/'screen.png'))
        self.assertEqual(before,self.dump())
