import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','windows')
from pathlib import Path
from PySide6.QtCore import QPoint,QRect
from PySide6.QtTest import QTest
from tests import test_market_ui as fixture

class TradeLayoutTests(unittest.TestCase):
    setUpClass=classmethod(fixture.MarketUITests.setUpClass.__func__)
    setUp=fixture.MarketUITests.setUp
    dump=fixture.MarketUITests.dump;rows=fixture.MarketUITests.rows
    day=fixture.MarketUITests.day;finite=fixture.MarketUITests.finite
    member=fixture.MarketUITests.member;vacancy=fixture.MarketUITests.vacancy
    def test_photos_and_selection_do_not_overlap_at_supported_sizes(self):
        page=self.page;page.tabs.setCurrentIndex(2);before=self.dump()
        root=Path(__file__).resolve().parents[1]/'reports/trade_layout';root.mkdir(exist_ok=True)
        for width,height in ((1900,1040),(1440,900),(1300,800),(900,1600)):
            self.window.resize(width,height);QTest.qWait(150)
            for photo,pro,extra in ((page.photo_a,page.pro_a,page.extra_a),(page.photo_b,page.pro_b,page.extra_b)):
                self.assertEqual((photo.width(),photo.height()),(96,120))
                self.assertTrue(photo.visibleRegion().contains(photo.rect()),(width,height,photo.visibleRegion().boundingRect()))
                photo_rect=QRect(photo.mapTo(self.window,QPoint()),photo.size())
                for field in (pro,extra):
                    field_rect=QRect(field.mapTo(self.window,QPoint()),field.size())
                    self.assertFalse(photo_rect.intersects(field_rect),(width,height))
            if width==1440:self.window.grab().save(str(root/'screen.png'))
        self.assertEqual(before,self.dump())
