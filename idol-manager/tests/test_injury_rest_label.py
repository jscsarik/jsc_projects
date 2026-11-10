import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','windows')
from contextlib import closing
from tests import test_season32 as fixture
from idol_manager.conditions import enter_day

class InjuryRestLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.Season32Tests.setUpClass.__func__(cls)
    setUp=fixture.Season32Tests.setUp
    rows=fixture.Season32Tests.rows
    day=fixture.Season32Tests.day
    def test_last_week_injury_and_forced_rest_are_distinct_from_new_injury(self):
        self.day(133)
        ids=[r[0] for r in self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='second_team' ORDER BY person_id LIMIT 3")]
        with closing(self.db.connect()) as c,c:
            for p,injured,injury,limit in ((ids[0],1,132,147),(ids[1],1,133,None),(ids[2],0,132,147)):
                c.execute('UPDATE player_conditions SET injured=?,injury_day=?,recovery_day=135,return_not_before=? WHERE person_id=?',(injured,injury,limit,p))
        values={p['id']:p for p in self.service.profiles.search(injured=True)}
        self.assertTrue(values[ids[0]]['injury_rest']);self.assertFalse(values[ids[1]]['injury_rest'])
        self.assertTrue(values[ids[2]]['injury_rest']);self.assertFalse(values[ids[2]]['injured'])
        self.assertNotIn(ids[2],{p['id'] for p in self.service.profiles.search(injured=False)})
        self.day(147)
        with closing(self.db.connect()) as c,c:enter_day(c,147)
        values={p['id']:p for p in self.service.profiles.search()}
        self.assertFalse(values[ids[0]]['injury_rest']);self.assertFalse(values[ids[2]]['injury_rest'])

    def test_explorer_displays_injury_rest(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from idol_manager.ui.main_window import MainWindow
        app=QApplication.instance() or QApplication([]);self.day(133)
        p=self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='second_team' LIMIT 1")[0][0]
        with closing(self.db.connect()) as c,c:c.execute('UPDATE player_conditions SET injured=1,injury_day=132,recovery_day=135 WHERE person_id=?',(p,))
        window=MainWindow(self.service);self.addCleanup(window.close);window.show();page=window.explorer_page
        page.reload();QTest.qWait(60)
        row=next(i for i,r in enumerate(page.rows) if r['id']==p)
        # Resolve the stable person ID after the table's initial sort.
        from PySide6.QtCore import Qt
        row=next(i for i in range(page.table.rowCount()) if page.table.item(i,0).data(Qt.ItemDataRole.UserRole)==p)
        self.assertEqual(page.table.item(row,18).text(),'부상(휴식)')
