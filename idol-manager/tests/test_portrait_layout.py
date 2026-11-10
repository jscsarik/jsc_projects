"""Presentation-only paging: no source model replacement, no game mutations."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile,unittest
from types import SimpleNamespace
from PySide6.QtCore import Qt,QSortFilterProxyModel
from PySide6.QtGui import QStandardItemModel,QStandardItem
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QTableWidgetItem,QAbstractScrollArea
from idol_manager.ui.table_widgets import QTableView,QTableWidget
from idol_manager.ui.portrait_layout import TablePages,RowDetails
from idol_manager.ui.main_window import MainWindow
from tests import test_market as fixture


class PageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def make(self,widget=True):
        root=QWidget();root.resize(850,600);box=QVBoxLayout(root)
        table=QTableWidget(80,15) if widget else QTableView()
        if widget:
            table.setHorizontalHeaderLabels(['이름']+[f'항목 {c}' for c in range(1,15)])
            for r in range(80):
                for c in range(15):table.setItem(r,c,QTableWidgetItem(f'가상 {r:03d} / {c}'))
        else:
            model=QStandardItemModel(80,15,table);model.setHorizontalHeaderLabels(['이름']+[f'항목 {c}' for c in range(1,15)])
            for r in range(80):
                for c in range(15):model.setItem(r,c,QStandardItem(f'가상 {r:03d} / {c}'))
            proxy=QSortFilterProxyModel(table);proxy.setSourceModel(model);table.setModel(proxy)
        box.addWidget(table);root.show();self.addCleanup(root.close)
        pager=TablePages(table,SimpleNamespace(window=root));pager.enable(True);QTest.qWait(70)
        return root,table,pager

    def test_every_row_and_column_reachable_without_scroll(self):
        root,table,pager=self.make();rows=[]
        table.setHorizontalHeaderLabels(['선택','사진','이름']+[f'항목 {c}' for c in range(3,15)])
        QTest.qWait(40)
        while True:
            QTest.qWait(30);rows.extend(r for r in range(80) if not table.isRowHidden(r))
            self.assertEqual(table.verticalScrollBar().maximum(),0)
            self.assertEqual(table.horizontalScrollBar().maximum(),0,(pager.row_page,table.viewport().size(),table.horizontalHeader().length(),[(c,table.columnWidth(c)) for c in range(15) if not table.isColumnHidden(c)]))
            if not pager.next.isEnabled():break
            QTest.mouseClick(pager.next,Qt.MouseButton.LeftButton)
        self.assertEqual(rows,list(range(80)))
        columns=set()
        for i in range(pager.fields.count()):
            pager.fields.setCurrentIndex(i);QTest.qWait(20)
            self.assertFalse(table.isColumnHidden(0));self.assertFalse(table.isColumnHidden(2))
            columns.update(c for c in range(15) if not table.isColumnHidden(c))
            self.assertEqual(table.horizontalScrollBar().maximum(),0,(pager.row_page,table.viewport().size(),table.horizontalHeader().length(),[(c,table.columnWidth(c)) for c in range(15) if not table.isColumnHidden(c)]))
        self.assertEqual(columns,set(range(15)))

    def test_proxy_sort_filter_and_original_indexes_preserved(self):
        root,table,pager=self.make(False);proxy=table.model();table.setSortingEnabled(True)
        proxy.sort(0,Qt.SortOrder.DescendingOrder);QTest.qWait(50)
        self.assertIs(table.model(),proxy);self.assertEqual(proxy.index(0,0).data(),'가상 079 / 0')
        proxy.setFilterFixedString('가상 001');QTest.qWait(50)
        self.assertEqual(proxy.rowCount(),1);self.assertFalse(table.isRowHidden(0));self.assertFalse(pager.next.isEnabled())
        self.assertEqual(proxy.mapToSource(proxy.index(0,0)).row(),1)

    def test_checkboxes_across_pages_and_selection_detail(self):
        root,table,pager=self.make()
        for r in (0,79):table.item(r,0).setCheckState(Qt.CheckState.Checked)
        table.setCurrentCell(0,0);QTest.qWait(30)
        self.assertTrue(pager.details.isEnabled());pager.open_details()
        self.addCleanup(pager.dialog.close)
        self.assertIn('가상 000',pager.dialog.text.text())
        pager.turn(1)
        for r in (0,79):self.assertEqual(table.item(r,0).checkState(),Qt.CheckState.Checked)
        table.setCurrentCell(79,0)
        self.assertFalse(table.isRowHidden(79))
        self.assertGreater(pager.row_page,0)

    def test_portrait_does_not_overwrite_saved_column_preferences(self):
        root,table,pager=self.make();pager.enable(False)
        with tempfile.TemporaryDirectory() as folder:
            table.bind_layout(Path(folder)/'layout.ini','test');table.horizontalHeader().resizeSection(2,250)
            saved=dict(table._saved_widths);pager.enable(True);QTest.qWait(50)
            pager.fields.setCurrentIndex(1);QTest.qWait(30);pager.enable(False)
            self.assertEqual(table._saved_widths,saved);self.assertEqual(table.columnWidth(2),250)

    def test_resize_recalculates_rows_and_no_scrollbar(self):
        root,table,pager=self.make();before=pager.page_size
        root.resize(850,900);QTest.qWait(70)
        self.assertGreater(pager.page_size,before)
        self.assertEqual(table.verticalScrollBar().maximum(),0)


class PortraitWindowTests(unittest.TestCase):
    setUpClass=classmethod(fixture.MarketTests.setUpClass.__func__)
    dump=fixture.MarketTests.dump
    day=fixture.MarketTests.day
    rows=fixture.MarketTests.rows
    def setUp(self):
        fixture.MarketTests.setUp(self);self.window=MainWindow(self.service);self.addCleanup(self.window.close)
        self.window.show();QTest.qWait(100);self.start_size=self.window.size();self.window.resize(900,1560);QTest.qWait(130)

    def test_main_navigation_paging_and_save_preservation(self):
        before=self.dump();window=self.window
        self.assertLessEqual(self.start_size.width(),900)
        self.assertLessEqual(self.start_size.height(),1600)
        self.assertTrue(window.portrait_layout.enabled);self.assertTrue(window.portrait_layout.nav.isVisible())
        for index,method in enumerate(('show_roster','show_draft','show_squads','show_schedule','show_matches','show_specials','show_finals','show_development','show_explorer','show_finance','show_market')):
            getattr(window,method)();QTest.qWait(220)
            expected=next(i for i,(_,p) in enumerate(window.navigation_pages) if p is window.pages.currentWidget())
            self.assertEqual(window.portrait_layout.nav.currentIndex(),expected)
            for area in window.findChildren(QAbstractScrollArea):
                if area.window() is window and area.isVisible() and not area.visibleRegion().isEmpty():
                    self.assertFalse(area.horizontalScrollBar().isVisible())
                    self.assertFalse(area.verticalScrollBar().isVisible())
                    self.assertEqual(area.horizontalScrollBar().maximum(),0,(index,area.__class__.__name__,area.objectName(),area.size(),[(name) for name,value in vars(window.draft_page).items() if value is area], getattr(area,'horizontalHeader',lambda:None)().length() if hasattr(area,'horizontalHeader') else 0,area.viewport().size(),[(c,area.columnWidth(c)) for c in range(area.model().columnCount()) if not area.isColumnHidden(c)] if hasattr(area,'isColumnHidden') else None))
                    self.assertEqual(area.verticalScrollBar().maximum(),0,(index,area.__class__.__name__,area.objectName(),area.size(),[(name) for name,value in vars(window.draft_page).items() if value is area], getattr(area,'horizontalHeader',lambda:None)().length() if hasattr(area,'horizontalHeader') else 0,area.viewport().size(),[(c,area.columnWidth(c)) for c in range(area.model().columnCount()) if not area.isColumnHidden(c)] if hasattr(area,'isColumnHidden') else None))
        self.assertEqual(before,self.dump())

    def test_large_window_restores_regular_navigation(self):
        self.window.resize(1500,1000);QTest.qWait(100)
        self.assertFalse(self.window.portrait_layout.enabled);self.assertFalse(self.window.portrait_layout.nav.isVisible())
        self.assertTrue(self.window.explorer_menu.isVisible())

    def test_five_vs_five_battle_uses_available_height_without_card_scroll(self):
        self.window.show_matches();page=self.window.match_page
        page.battle.configure('5인 대결', [('a','팀 A'),('b','팀 B')],
            [dict(id=f'{team}{i}',agency_id=team,name=f'선수 {i}',leader=i==0,photo_path='') for team in ('a','b') for i in range(5)])
        page.tabs.setCurrentIndex(1);QTest.qWait(200)
        self.assertFalse(page.fixture_table.dock_panel.isVisible())
        for area in page.battle.findChildren(QAbstractScrollArea):
            self.assertEqual(area.horizontalScrollBar().maximum(),0);self.assertEqual(area.verticalScrollBar().maximum(),0)
        page.tabs.setCurrentIndex(0);QTest.qWait(70)
        self.assertTrue(page.fixture_table.dock_panel.isVisible())

    def test_profile_comparison_and_long_explanations_have_no_scroll(self):
        agency=self.service.draft_session.player_agency();people=[p.id for p in self.service.agency_roster(agency)][:2]
        self.window.profiles.compare(people);QTest.qWait(100);dialog=self.window.profiles.dialog
        self.addCleanup(dialog.close)
        for panel in dialog.panels:
            for i in range(panel.tabs.count()):
                panel.tabs.setCurrentIndex(i);QTest.qWait(50)
        self.assertLessEqual(dialog.width(),900)
        for area in dialog.findChildren(QAbstractScrollArea):
            if area.isVisible() and not area.visibleRegion().isEmpty():
                self.assertEqual(area.horizontalScrollBar().maximum(),0);self.assertEqual(area.verticalScrollBar().maximum(),0)








