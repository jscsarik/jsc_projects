import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','windows')
from contextlib import closing
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from tests import test_season32 as fixture
from idol_manager.ui.main_window import MainWindow

class MarketPhotoRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        fixture.Season32Tests.setUpClass.__func__(cls)
    setUp=fixture.Season32Tests.setUp
    day=fixture.Season32Tests.day
    def test_photo_refresh_does_not_query_contract_gates_or_change_save(self):
        self.day(203);w=MainWindow(self.service);self.addCleanup(w.close)
        w.resize(1600,900);w.show();w.show_market();QTest.qWait(300)
        p=w.market_page;p.photo_refresh_timer.stop()
        item=p.renew_table.item(0,0);item.setCheckState(Qt.CheckState.Checked)
        selected=p.checked_renew_ids()
        with closing(self.db.connect()) as c:before=list(c.iterdump())
        with patch.object(p,'update_actions') as actions,patch.object(self.service.market,'action_reason') as gates:
            p.refresh_market_photos()
            actions.assert_not_called();gates.assert_not_called()
        self.assertEqual(selected,p.checked_renew_ids());self.assertFalse(p.renew_table.signalsBlocked())
        with closing(self.db.connect()) as c:self.assertEqual(before,list(c.iterdump()))
        with patch.object(p,'update_actions') as actions:
            item.setCheckState(Qt.CheckState.Unchecked);actions.assert_called_once()
    def test_thumbnail_burst_is_batched_and_screen_stays_responsive(self):
        w=MainWindow(self.service);self.addCleanup(w.close);w.resize(1600,900);w.show();w.show_market();QTest.qWait(350)
        p=w.market_page;p.photo_refresh_timer.stop()
        with patch.object(p,'trade_preview') as refresh:
            for _ in range(200):p.queue_market_photos()
            self.assertTrue(p.photo_refresh_timer.isActive());QTest.qWait(90)
            refresh.assert_called_once()
        w.show_squads();w.show_market();QTest.qWait(90)
        self.assertIs(w.pages.currentWidget(),p)
