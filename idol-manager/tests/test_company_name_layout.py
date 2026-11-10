import os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','windows')
from pathlib import Path
from contextlib import closing
from PySide6.QtCore import Qt,QPoint
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from idol_manager.agencies import AGENCY_SEEDS
from idol_manager.ui.match_page import make_table,fill_table
from idol_manager.ui.agency_table_layout import text_height,agency_columns
from tests import test_market as fixture

LONG_NAME='주식회사 에스엠엔터테인먼트 SM ENTERTAINMENT Co., Ltd.'

class CompanyTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_registered_longest_and_long_company_wrap_sort_and_fit(self):
        with tempfile.TemporaryDirectory() as folder:
            table=make_table();self.addCleanup(table.close)
            names=[a[1] for a in AGENCY_SEEDS]+[LONG_NAME]
            fill_table(table,('순위','기획사','승점','승','패','자금'),[(i+1,n,117,100,17,1000000000) for i,n in enumerate(names)])
            table.bind_layout(Path(folder)/'ui.ini','company-test');table.resize(720,700);table.show();QTest.qWait(100)
            for width in (720,1000,560):
                table.resize(width,800);QTest.qWait(60)
                self.assertLessEqual(sum(table.columnWidth(c) for c in range(6)),table.viewport().width())
                self.assertFalse(table.horizontalScrollBar().isVisible())
                self.assertGreater(table.columnWidth(1),table.columnWidth(2))
                self.assertEqual(table.textElideMode(),Qt.TextElideMode.ElideNone)
                for row in range(table.rowCount()):
                    item=table.item(row,1);self.assertGreaterEqual(table.rowHeight(row),text_height(table.fontMetrics(),item.text(),table.columnWidth(1)))
            table.sortItems(1,Qt.SortOrder.AscendingOrder)
            actual=[table.item(r,1).text() for r in range(table.rowCount())]
            self.assertEqual(actual,sorted(names))
            header=table.horizontalHeader();self.assertTrue(header.sectionsClickable())
            QTest.mouseClick(header.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,
                QPoint(header.sectionViewportPosition(1)+table.columnWidth(1)//2,header.height()//2))
            self.assertEqual([table.item(r,1).text() for r in range(table.rowCount())],sorted(names,reverse=True))

class CompanyPageTests(unittest.TestCase):
    setUpClass=classmethod(fixture.MarketTests.setUpClass.__func__)
    setUp=fixture.MarketTests.setUp
    rows=fixture.MarketTests.rows;day=fixture.MarketTests.day;dump=fixture.MarketTests.dump
    def test_related_windows_keep_names_and_fit(self):
        with closing(self.db.connect()) as c,c:c.execute("UPDATE agencies SET name=? WHERE id='sm'",(LONG_NAME,))
        from idol_manager.ui.main_window import MainWindow
        w=MainWindow(self.service);self.addCleanup(w.close);w.show()
        before=self.dump();out=Path(__file__).resolve().parents[1]/'reports/company_names';out.mkdir(exist_ok=True)
        for width,height in ((1700,1000),(1300,900),(900,1600)):
            w.resize(width,height);w.show_matches();w.match_page.tabs.setCurrentIndex(3);QTest.qWait(160)
            table=w.match_page.standings_table
            self.assertTrue(table.isVisible())
            if width>=1300:
                company=agency_columns(table)[0]
                self.assertLessEqual(table.columnWidth(company),280)
                self.assertGreater(table.columnWidth(2),100)
            visible=[c for c in range(table.model().columnCount()) if not table.isColumnHidden(c)]
            self.assertLessEqual(sum(table.columnWidth(c) for c in visible),table.viewport().width())
            self.assertFalse(table.horizontalScrollBar().isVisible())
            w.show_draft();QTest.qWait(100)
            for table in (w.draft_page.history_table,w.draft_page.order_table):
                if table.isVisible():
                    visible=[c for c in range(table.model().columnCount()) if not table.isColumnHidden(c)]
                    self.assertLessEqual(sum(table.columnWidth(c) for c in visible),table.viewport().width(),
                        (width,table.objectName(),[(table.model().headerData(c,Qt.Orientation.Horizontal),table.columnWidth(c)) for c in visible]))
                    self.assertFalse(table.horizontalScrollBar().isVisible())
            w.show_market();w.market_page.tabs.setCurrentIndex(2);QTest.qWait(100)
            table=w.market_page.trade_table
            visible=[c for c in range(table.columnCount()) if not table.isColumnHidden(c)]
            self.assertLessEqual(sum(table.columnWidth(c) for c in visible),table.viewport().width())
            self.assertFalse(table.horizontalScrollBar().isVisible())
            w.trade_chat.toggle();w.trade_chat.agency.setCurrentIndex(w.trade_chat.agency.findData('sm'));QTest.qWait(30)
            self.assertIn(LONG_NAME,w.trade_chat.agency.currentText())
            self.assertIn(LONG_NAME,w.trade_chat.agency_name.text())
            self.assertTrue(w.trade_chat.agency_name.wordWrap());w.trade_chat.hide()
            if width==1300:
                w.show_matches();w.match_page.tabs.setCurrentIndex(3);QTest.qWait(100);w.grab().save(str(out/'league.png'))
        self.assertEqual(before,self.dump())

class ManualTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_manual_drag_survives_refresh_resize_and_reopen(self):
        from PySide6.QtWidgets import QHeaderView
        with tempfile.TemporaryDirectory() as folder:
            for all_columns in (False,True):
                key='all' if all_columns else 'company'
                table=make_table();self.addCleanup(table.close)
                table.setProperty('fitAllColumns',all_columns)
                fill_table(table,('순위','기획사','승점','승'),[(1,'JYP entertainment',10,10)])
                path=Path(folder)/'ui.ini';table.bind_layout(path,key);table.resize(1000,500);table.show();QTest.qWait(80)
                header=table.horizontalHeader()
                self.assertEqual(header.sectionResizeMode(1),QHeaderView.ResizeMode.Interactive)
                before=table.columnWidth(1)
                edge=header.sectionViewportPosition(1)+before-1
                QTest.mousePress(header.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(edge,header.height()//2))
                QTest.mouseMove(header.viewport(),QPoint(edge+50,header.height()//2),20)
                QTest.mouseRelease(header.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(edge+50,header.height()//2));QTest.qWait(60)
                self.assertGreater(table.columnWidth(1),before)
                widths=[table.columnWidth(c) for c in range(4)]
                table.item(0,2).setText('11');QTest.qWait(50)
                self.assertEqual(widths,[table.columnWidth(c) for c in range(4)])
                self.assertEqual(sum(widths),table.viewport().width())
                table.resize(780,500);QTest.qWait(50)
                self.assertLessEqual(sum(table.columnWidth(c) for c in range(4)),table.viewport().width())
                table.resize(1000,500);QTest.qWait(50)
                self.assertEqual(widths,[table.columnWidth(c) for c in range(4)])
                table.close()
                loaded=make_table();self.addCleanup(loaded.close);loaded.setProperty('fitAllColumns',all_columns)
                fill_table(loaded,('순위','기획사','승점','승'),[(1,'JYP entertainment',11,10)])
                loaded.bind_layout(path,key);loaded.resize(1000,500);loaded.show();QTest.qWait(80)
                self.assertEqual(widths,[loaded.columnWidth(c) for c in range(4)])
                loaded.reset_columns();QTest.qWait(50);self.assertFalse(loaded._saved_widths)
                loaded.close()
