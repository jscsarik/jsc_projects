import unittest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from idol_manager.ui.table_widgets import QTableView,QTableWidget
from idol_manager.ui.dock_workspace import TabbedDockWorkspace
from tests import test_profile_ui as fixture


class DockUITests(unittest.TestCase):
    setUpClass=classmethod(fixture.ProfileUITests.setUpClass.__func__)
    setUp=fixture.ProfileUITests.setUp
    dump=fixture.ProfileUITests.dump
    def test_every_main_and_profile_table_has_dock_and_same_public_data(self):
        before=self.dump();tables=self.window.findChildren(QTableView)+self.window.findChildren(QTableWidget)
        self.assertGreaterEqual(len(tables),30)
        for table in tables:self.assertTrue(hasattr(table,'dock_panel'),table.objectName())
        self.window.show_matches();QTest.qWait(40)
        host=self.window.match_page.fixture_table.dock_panel.workspace
        self.assertFalse(host.isWindow());self.assertTrue(host.isVisible())
        self.assertGreater(host.height(),300)
        self.assertTrue(self.window.match_page.fixture_table.isVisible())
        self.window.profiles.open(self.person);panel=self.window.profiles.dialog.panels[0]
        for name,value in vars(panel).items():
            if isinstance(value,(QTableView,QTableWidget)):self.assertTrue(hasattr(value,'dock_panel'),name)
        self.assertIsInstance(panel.record_tabs,TabbedDockWorkspace);self.assertEqual(panel.record_tabs.count(),5)
        self.assertEqual(before,self.dump())

    def test_draft_rearrange_float_and_close_panels_does_not_draft(self):
        self.window.show_draft();page=self.window.draft_page;before=self.dump()
        a=page.candidate_table.dock_panel;b=page.history_table.dock_panel;host=a.workspace
        self.assertIs(host,b.workspace);self.assertEqual(len(host.panels),4)
        model=page.candidate_table.model();a.setFloating(True);a.resize(750,500);QTest.qWait(40)
        a.setFloating(False);host.tabifyDockWidget(a,b);QTest.qWait(30)
        self.assertIn(b,host.tabifiedDockWidgets(a));b.close();b.set_open(True)
        host.reset_layout();QTest.qWait(30);self.assertIs(page.candidate_table.model(),model)
        self.window.resize(1280,850);QTest.qWait(30)
        self.assertEqual(page.order_table.maximumHeight(),16777215)
        self.assertEqual(before,self.dump())

    def test_floating_record_survives_tab_switch_then_hides_on_other_page(self):
        self.window.show_matches();page=self.window.match_page;before=self.dump()
        panel=page.standings_table.dock_panel
        page.tabs.setCurrentIndex(3);QTest.qWait(40);panel.setFloating(True);QTest.qWait(40)
        self.assertTrue(panel.isVisible());page.tabs.setCurrentIndex(0);QTest.qWait(60)
        self.assertTrue(panel.isVisible());self.window.show_squads();QTest.qWait(40)
        self.assertFalse(panel.isVisible());self.window.show_matches();QTest.qWait(60)
        self.assertTrue(panel.isVisible());self.assertEqual(before,self.dump())

    def test_floating_panel_restart_and_reset_does_not_reset_game(self):
        from idol_manager.ui.main_window import MainWindow
        self.window.show_schedule();panel=self.window.schedule_page.table.dock_panel
        panel.setFloating(True);panel.resize(700,400);QTest.qWait(40)
        before=self.dump();self.window.close()
        self.window=MainWindow(self.service);self.addCleanup(self.window.close);self.window.resize(1500,950);self.window.show();self.window.show_schedule();QTest.qWait(100)
        restored=self.window.schedule_page.table.dock_panel;self.assertTrue(restored.isFloating())
        self.assertAlmostEqual(restored.width(),700,delta=30)
        restored.workspace.reset_layout();QTest.qWait(30);self.assertFalse(restored.isFloating())
        self.assertEqual(before,self.dump())

    def test_profile_records_can_split_and_float_while_other_profile_tab_is_visible(self):
        self.window.profiles.open(self.person);dialog=self.window.profiles.dialog;panel=dialog.panels[0]
        before=self.dump();panel.tabs.setCurrentIndex(3);panel.record_tabs.setCurrentIndex(0);QTest.qWait(40)
        first=panel.match_table.dock_panel;second=panel.skill_total_table.dock_panel;host=first.workspace
        self.assertIs(host,second.workspace)
        host.splitDockWidget(first,second,Qt.Orientation.Horizontal);first.setFloating(True);QTest.qWait(40)
        panel.tabs.setCurrentIndex(1);QTest.qWait(60);self.assertTrue(first.isVisible())
        dialog.close();QTest.qWait(30);self.assertEqual(before,self.dump())
