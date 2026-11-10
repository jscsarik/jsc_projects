from contextlib import closing
import gc,json,unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from idol_manager.ui.main_window import MainWindow
from idol_manager.ui.profile_dialog import ProfileDialog,ProfilePanel
from tests import test_profiles as profile_fixture
from tests import test_match_ui as fixture


class ProfileUITests(unittest.TestCase):
    setUpClass=classmethod(fixture.MatchUITests.setUpClass.__func__)
    dump=profile_fixture.ProfileServiceTests.dump
    def setUp(self):
        profile_fixture.ProfileServiceTests.setUp(self);gc.collect();self.app.processEvents()
        self.warnings=[]
        warning=patch('idol_manager.ui.profile_controller.QMessageBox.warning',side_effect=lambda *args:self.warnings.append(args[-1]))
        warning.start();self.addCleanup(warning.stop)
        self.window=MainWindow(self.service);self.addCleanup(self.window.close);self.window.resize(1500,950);self.window.show();self.app.processEvents()
        if self.app.platformName()=='windows':
            self.assertTrue(QTest.qWaitForWindowExposed(self.window,5000));self.window.raise_();self.window.activateWindow();self.assertTrue(QTest.qWaitForWindowActive(self.window,5000))

    def click(self,table,row,col):
        index=table.model().index(row,col);table.scrollTo(index);self.app.processEvents()
        QTest.mouseClick(table.viewport(),Qt.MouseButton.LeftButton,pos=table.visualRect(index).center());self.app.processEvents()

    def test_other_agency_search_click_profile_filters_compare_and_close_no_write(self):
        self.window.show_explorer();page=self.window.explorer_page;before=self.dump()
        page.agency.setCurrentIndex(page.agency.findData('jyp'));expected=len(self.service.agency_roster('jyp'));self.assertEqual(page.table.rowCount(),expected)
        target=page.table.item(0,0).data(Qt.ItemDataRole.UserRole)
        self.click(page.table,0,2);dialog=self.window.profiles.dialog;self.assertIsNotNone(dialog)
        panel=dialog.panels[0];self.assertEqual(panel.person,target);self.assertTrue(panel.data['exact']);self.assertEqual(panel.tabs.count(),6)
        self.assertLess(panel.photo.geometry().right(),panel.name.geometry().left())
        dialog.close();self.assertIs(self.window.pages.currentWidget(),page);self.assertEqual(page.table.rowCount(),expected)
        for row in (0,1):page.table.item(row,0).setCheckState(Qt.CheckState.Checked)
        self.assertTrue(page.compare.isEnabled());QTest.mouseClick(page.compare,Qt.MouseButton.LeftButton)
        self.assertEqual(len(self.window.profiles.dialog.panels),2);self.window.profiles.dialog.close()
        self.window.profiles.compare([target,self.hidden]);panels=self.window.profiles.dialog.panels
        self.assertTrue(panels[0].data['exact']);self.assertFalse(panels[1].data['exact'])
        self.assertTrue(all('~' in label.text() for bar,label in panels[1].bars));self.window.profiles.dialog.close()
        self.assertEqual(before,self.dump())

    def test_candidate_click_shows_same_estimates_no_pick_and_pa_not_in_widget(self):
        before=self.dump();self.window.show_draft();page=self.window.draft_page
        index=next(page.proxy.index(i,1) for i in range(page.proxy.rowCount()) if page.candidate_model.rows[page.proxy.mapToSource(page.proxy.index(i,1)).row()].id==self.hidden)
        self.click(page.candidate_table,index.row(),1);dialog=self.window.profiles.dialog;self.assertIsNotNone(dialog)
        panel=dialog.panels[0];self.assertFalse(panel.data['exact']);self.assertIn('스카우팅 추정치',panel.publication.text())
        self.assertTrue(all('~' in label.text() for bar,label in panel.bars))
        self.assertTrue(all('~' in bar.format() for bar,label in panel.bars));self.assertIsNone(panel.data['health'])
        self.assertEqual(before,self.dump());dialog.close()

    def test_squad_name_click_sorted_proxy_id_and_checkbox_separate(self):
        self.window.show_squads();page=self.window.squad_page;page.table.sortByColumn(2,Qt.SortOrder.DescendingOrder)
        index=page.proxy.mapToSource(page.proxy.index(0,2));expected=page.model.rows[index.row()].id
        self.click(page.table,0,2);self.assertEqual(self.window.profiles.dialog.panels[0].person,expected)

    def test_small_window_and_repeated_profiles_release_and_latest_ca_refresh(self):
        before=self.dump()
        for person in (self.person,self.hidden,self.person,self.hidden):
            self.window.profiles.open(person);dialog=self.window.profiles.dialog;dialog.resize(660,500);self.app.processEvents()
            panel=dialog.panels[0];self.assertEqual(panel.person,person);dialog.close();self.app.processEvents()
        self.assertIsNone(self.window.profiles.dialog);self.assertEqual(before,self.dump())

    def test_battle_card_and_records_use_frozen_person_ids(self):
        fixture_=next(f for f in self.service.matches.fixtures() if f.player_participates)
        result=self.service.matches.play(fixture_.id);self.window.show_matches();page=self.window.match_page
        page.selection=self.service.matches.selection(fixture_.id)
        # Saved result has only one projection; names need not be unique.
        page._show_result(result);before=self.dump();self.click(page.records_table,0,1)
        self.assertIsNotNone(self.window.profiles.dialog);person=self.window.profiles.dialog.panels[0].person
        self.assertIn(person,{r['person_id'] for r in result.players});self.window.profiles.dialog.close()
        page.names=self.service.matches.result_names(result.match_id)
        page._configure_battle(result);card=next(iter(page.battle.cards.values()))
        card.photo.clicked.emit();self.assertEqual(self.window.profiles.dialog.panels[0].person,card.person['id']);self.assertEqual(before,self.dump())
