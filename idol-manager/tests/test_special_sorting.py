import os,unittest,hashlib
os.environ.setdefault('QT_QPA_PLATFORM','windows')
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap,QColor
from PySide6.QtTest import QTest
from tests import test_special_ui as fixture
from idol_manager.ui.special_page import STAGES

class SpecialSortingTests(unittest.TestCase):
    setUpClass=classmethod(fixture.SpecialUITests.setUpClass.__func__)
    setUp=fixture.SpecialUITests.setUp;open=fixture.SpecialUITests.open
    wait=fixture.SpecialUITests.wait;dump=fixture.SpecialUITests.dump
    start_event=fixture.SpecialUITests.start_event
    def test_repeated_name_sort_reload_and_photo_refresh_keep_identity(self):
        page=self.open();self.start_event();table=page.lineup_table;before=self.dump()
        agency=self.service.draft_session.player_agency()
        target=next(r['id'] for r in page.event_state['rounds'] if agency in r['agencies'])
        row=next(i for i in range(page.round_table.rowCount()) if page.round_table.item(i,0).data(Qt.ItemDataRole.UserRole)==target)
        page.round_table.setCurrentCell(row,0);page.select_round()
        self.assertGreater(table.rowCount(),0)
        selected=set(page.selected_ids())
        def color(path):return QColor('#'+hashlib.sha256(str(path).encode()).hexdigest()[:6])
        def photo(path):
            pix=QPixmap(48,60);pix.fill(color(path));return pix
        with patch.object(page.thumbnails,'get',side_effect=photo):
            for order in (Qt.SortOrder.AscendingOrder,Qt.SortOrder.DescendingOrder)*3:
                table.sortItems(1,order);page.select_round();page._photos_changed();QTest.qWait(20)
                options={o['player'].id:o for o in page.selection['options']}
                self.assertEqual(set(page.selected_ids()),selected)
                for row in range(table.rowCount()):
                    identity=table.item(row,0).data(Qt.ItemDataRole.UserRole);o=options[identity]
                    self.assertEqual(table.item(row,1).text(),o['player'].name)
                    self.assertEqual(table.item(row,3).data(Qt.ItemDataRole.DisplayRole),round(sum(o['player'].skills)/8,1))
                    self.assertEqual(table.item(row,4).data(Qt.ItemDataRole.DisplayRole),o['player'].health)
                    self.assertEqual(table.item(row,1).icon().pixmap(32,32).toImage().pixelColor(10,10),color(o['path']))
            root=Path(__file__).resolve().parents[1]/'reports/special_sorting';root.mkdir(exist_ok=True)
            self.window.grab().save(str(root/'screen.png'))
        self.assertEqual(before,self.dump())

    def test_sorted_stage_ids_survive_reload(self):
        page=self.open();self.start_event();before=self.dump()
        for order in (Qt.SortOrder.AscendingOrder,Qt.SortOrder.DescendingOrder):
            page.round_table.sortItems(0,order);page.reload()
            rounds={r['id']:r for r in page.event_state['rounds']}
            for row in range(page.round_table.rowCount()):
                item=page.round_table.item(row,0)
                self.assertEqual(item.text(),STAGES[rounds[item.data(Qt.ItemDataRole.UserRole)]['stage']])
        self.assertEqual(before,self.dump())
