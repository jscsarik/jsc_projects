import os
import random
from contextlib import closing
from unittest.mock import patch
import unittest

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox
from tests import test_draft_ui as fixture
from idol_manager.config import SKILLS
from idol_manager.ui.draft_models import SORT_ROLE
from idol_manager.service import GameService
from idol_manager.ui.main_window import MainWindow


class EstimateUITests(unittest.TestCase):
    setUpClass=classmethod(fixture.DraftUITests.setUpClass.__func__)
    setUp=fixture.DraftUITests.setUp
    select_agency=fixture.DraftUITests.select_agency

    def first_turn(self):
        ids=sorted(a.id for a in self.service.agencies());random.Random(8).shuffle(ids)
        self.page._paused=True
        self.select_agency(ids[0])
        self.service.draft.start(rng=random.Random(8));self.page.reload()
        self.page.candidate_table.setCurrentIndex(self.page.proxy.index(0,1))
        return self.page.selected_candidate()

    def confirm(self):
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):
            QTest.mouseClick(self.page.pick_button,Qt.MouseButton.LeftButton)
        self.page.ai_timer.stop()

    def test_public_ranges_numeric_sort_search_age_and_status_filters(self):
        self.page.candidate_table.setCurrentIndex(self.page.proxy.index(0,1))
        candidate=self.page.selected_candidate()
        self.assertEqual(self.page.detail_table.item(0,1).text(),str(candidate.estimates[0]))
        self.assertIn('잠재력',self.page.detail_label.text())
        for column in range(3,12):
            self.page.candidate_table.sortByColumn(column,Qt.SortOrder.AscendingOrder)
            values=[self.page.proxy.index(i,column).data(SORT_ROLE) for i in range(self.page.proxy.rowCount())]
            self.assertEqual(values,sorted(values))
        self.page.min_age.setValue(candidate.age);self.page.max_age.setValue(candidate.age)
        self.assertTrue(all(self.page.proxy.index(i,2).data()==candidate.age for i in range(self.page.proxy.rowCount())))
        self.page.search.setText(candidate.name);self.assertEqual(self.page.proxy.rowCount(),1)
        self.page.search.clear();self.page.min_age.setValue(0);self.page.max_age.setValue(100)
        self.page.status_filter.setCurrentIndex(self.page.status_filter.findData('picked'))
        self.assertEqual(self.page.proxy.rowCount(),0)
        self.page.status_filter.setCurrentIndex(self.page.status_filter.findData('all'))
        self.assertEqual(self.page.proxy.rowCount(),200)

    def test_pick_reveals_only_owned_ca_history_and_restart_preserve_ranges(self):
        candidate=self.first_turn();before=self.service.draft_session.snapshot().prospects
        self.assertTrue(self.page.pick_button.isEnabled());self.confirm()
        self.assertEqual(self.service.draft.state().picks_made,1)
        self.assertEqual(self.page.detail_table.horizontalHeaderItem(1).text(),'실제 현재 값')
        with closing(self.service.database.connect()) as c:
            values=dict(c.execute('SELECT skill,value FROM abilities WHERE person_id=?',(candidate.id,)))
        self.assertEqual([self.page.detail_table.item(i,1).text() for i in range(8)],[str(values[s]) for s in SKILLS])
        self.page.history_table.setCurrentIndex(self.page.history_model.index(0,3))
        self.assertEqual(self.page.detail_table.horizontalHeaderItem(1).text(),'실제 현재 값')
        self.assertFalse(self.page.pick_button.isEnabled())
        self.page.status_filter.setCurrentIndex(self.page.status_filter.findData('picked'))
        self.assertEqual(self.page.proxy.rowCount(),1)
        self.page.candidate_table.setCurrentIndex(self.page.proxy.index(0,1))
        self.assertEqual(self.page.proxy.index(0,3).data(),str(candidate.estimates[0]))
        self.assertFalse(self.page.pick_button.isEnabled())
        self.service.draft_session.pick_ai_turn();self.page.reload()
        self.page.history_table.setCurrentIndex(self.page.history_model.index(1,3))
        self.assertEqual(self.page.detail_table.horizontalHeaderItem(1).text(),'추정 범위')
        self.assertIn('~',self.page.detail_table.item(0,1).text())
        self.window.close()
        service=GameService(self.root);window=MainWindow(service);self.addCleanup(window.close)
        window.draft_page._paused=True;window.show();window.show_draft()
        after=service.draft_session.snapshot().prospects
        self.assertEqual([(p.id,p.estimates) for p in before],[(p.id,p.estimates) for p in after])
        window.draft_page.history_table.setCurrentIndex(window.draft_page.history_model.index(0,3))
        self.assertEqual(window.draft_page.detail_table.item(0,1).text(),str(values[SKILLS[0]]))


if __name__=='__main__':unittest.main()
