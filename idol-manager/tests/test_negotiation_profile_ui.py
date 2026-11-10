import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','windows')
from contextlib import closing
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from unittest.mock import patch
from tests import test_season32 as fixture
from idol_manager.ui.main_window import MainWindow
from idol_manager.ui.match_page import PROFILE_ROLE

class NegotiationProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        fixture.Season32Tests.setUpClass.__func__(cls)
    setUp=fixture.Season32Tests.setUp
    day=fixture.Season32Tests.day
    def test_name_click_opens_correct_profile_after_sort_reload_without_writes(self):
        self.day(203);w=MainWindow(self.service);self.addCleanup(w.close)
        w.resize(1600,950);w.show();w.show_market();p=w.market_page;p.tabs.setCurrentIndex(1);QTest.qWait(150)
        t=p.negotiation_table;self.assertGreater(t.rowCount(),0)
        with closing(self.db.connect()) as c:before=list(c.iterdump())
        for order in (Qt.SortOrder.DescendingOrder,Qt.SortOrder.AscendingOrder):
            t.sortItems(1,order);p.reload();QTest.qWait(80)
            item=t.item(0,1);expected=item.data(PROFILE_ROLE)
            n=next(n for n in p.sessions if n['id']==t.item(0,0).text())
            self.assertEqual(expected,n['person_id'])
            t.scrollToItem(item);QTest.qWait(30)
            QTest.mouseClick(t.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,t.visualItemRect(item).center())
            QTest.qWait(60);self.assertIsNotNone(w.profiles.dialog)
            self.assertEqual(w.profiles.dialog.panels[0].person,expected);w.profiles.dialog.close()
        with patch.object(w.profiles,'open') as opened:
            item=t.item(0,0);QTest.mouseClick(t.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,t.visualItemRect(item).center());opened.assert_not_called()
        with closing(self.db.connect()) as c:self.assertEqual(before,list(c.iterdump()))
