import os,unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtTest import QTest
from idol_manager.service import GameService
from idol_manager.ui.main_window import MainWindow
from tests import test_records as fixtures

class CompactProfileTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.RecordsTests.setUpClass.__func__)
    setUp=fixtures.RecordsTests.setUp
    def test_default_size_and_recent_selection_flags(self):
        from contextlib import closing
        service=GameService(self.root,self.path);w=MainWindow(service);self.addCleanup(w.close);w.show()
        w.profiles.open('p0');dialog=w.profiles.dialog;panel=dialog.panels[0]
        panel.tabs.setCurrentIndex(3);panel.record_tabs.setCurrentIndex(1);QTest.qWait(80)
        self.assertEqual((dialog.width(),dialog.height()),(1400,800))
        headers=[panel.match_table.horizontalHeaderItem(c).text() for c in range(panel.match_table.columnCount())]
        self.assertEqual(headers[-2:],['승리 아이돌','패배 아이돌'])
        displayed={panel.match_table.item(r,c).text() for r in range(panel.match_table.rowCount()) for c in (11,12)}
        self.assertTrue(displayed <= {'O',''})
        self.assertIn('O',displayed);self.assertIn('',displayed)
        with closing(service.database.connect()) as c:
            records=service.profiles.matches(c,'p0',1)
            for r in records:
                if r['kind']!='regular':continue
                expected=c.execute('SELECT winning_idol,losing_idol FROM match_player_stats WHERE match_id=? AND person_id=?',(r['id'],'p0')).fetchone()
                self.assertEqual((r['winning_idol'],r['losing_idol']),tuple(map(bool,expected)))
        with closing(service.database.connect()) as c,c:
            c.execute("INSERT OR REPLACE INTO award_match_selections VALUES (?,'winning_idol','p1','fixed')",(self.first,))
            records=service.profiles.matches(c,'p0',1)
            self.assertFalse(next(r for r in records if r['id']==self.first)['winning_idol'])
        out=Path(__file__).resolve().parents[1]/'reports/profile_recent';out.mkdir(exist_ok=True)
        dialog.grab().save(str(out/'screen.png'));dialog.close()
    def test_content_widths_and_main_table_unchanged(self):
        service=GameService(self.root,self.path);w=MainWindow(service);self.addCleanup(w.close);w.resize(1500,950);w.show()
        before=w.squad_page.table.columnWidth(5)
        w.profiles.open('p0');dialog=w.profiles.dialog;dialog.resize(1430,850);panel=dialog.panels[0];panel.tabs.setCurrentIndex(3);QTest.qWait(100)
        table=panel.season_history_table
        widths=[table.columnWidth(c) for c in range(table.columnCount())]
        self.assertLess(widths[5],60);self.assertLess(widths[6],60)
        self.assertLessEqual(sum(widths),table.viewport().width())
        self.assertEqual(w.squad_page.table.columnWidth(5),before)
        out=Path(__file__).resolve().parents[1]/'reports/profile_compact';out.mkdir(exist_ok=True);dialog.grab().save(str(out/'profile.png'))
        print('Profile column widths:',widths,'total',sum(widths),'viewport',table.viewport().width())
        dialog.close()
    def test_reload_preserves_compact_profile_defaults(self):
        service=GameService(self.root,self.path);w=MainWindow(service);self.addCleanup(w.close);w.show();w.profiles.open('p0');panel=w.profiles.dialog.panels[0]
        panel.reload()
        self.assertTrue(panel.season_history_table.property('compactProfileTable'))
        self.assertFalse(panel.season_history_table.horizontalHeader().stretchLastSection())
        self.assertEqual(panel.growth_table.verticalHeader().defaultSectionSize(),28)
        self.assertLess(panel.season_history_table.columnWidth(5),60)
        w.profiles.dialog.close()
