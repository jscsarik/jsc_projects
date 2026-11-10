"""Integrated 17 native profile/condition/statistics checks, temporary games only."""
import os
os.environ['QT_QPA_PLATFORM']='windows'
from pathlib import Path
from contextlib import closing
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtTest import QTest
from tools.verify_profiles_ui import NativeProfiles


class IntegratedNative(NativeProfiles):
    def test_extended_fatigue_growth_condition_and_original_values(self):
        with closing(self.db.connect()) as c,c:
            c.execute('UPDATE game_clock SET absolute_day=4')
            c.execute('UPDATE idols SET health=80 WHERE person_id=?',(self.person,))
            c.execute('UPDATE player_conditions SET registration_weeks=4,registration_week=0,last_appearance_day=4,consecutive_days=3 WHERE person_id=?',(self.person,))
            for day in (2,3,4):c.execute('INSERT OR IGNORE INTO appearance_days VALUES (?,?)',(self.person,day))
        before=self.dump();self.window.profiles.open(self.person);dialog=self.window.profiles.dialog;panel=dialog.panels[0]
        panel.tabs.setCurrentIndex(2);QTest.qWait(150)
        c=panel.data['condition'];self.assertAlmostEqual(c['probabilities']['match'],.04);self.assertAlmostEqual(c['probabilities']['first_rest'],.02)
        self.assertTrue(c['weekly_growth']['three_consecutive_days']);self.assertTrue(c['weekly_growth']['rise_restricted'])
        self.assertEqual(panel.effective_table.rowCount(),8);self.assertEqual(panel.calendar_table.rowCount(),5)
        self.assertLess(panel.photo.geometry().right(),panel.name.geometry().left())
        for i in range(8):self.assertAlmostEqual(float(panel.effective_table.item(i,2).text()),panel.data['bounds'][i][0]*.9,places=2)
        dialog.grab().save(str(ROOT/'.test-artifacts/integrated17_condition.png'))
        scroll=panel.tabs.widget(2);scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum());QTest.qWait(100)
        dialog.grab().save(str(ROOT/'.test-artifacts/integrated17_calendar_effective.png'))
        self.assertEqual(before,self.dump());self.assertEqual(self.warnings,[])

    def test_new_match_actual_skill_totals_and_group_counts_without_reroll(self):
        fixture=next(f for f in self.service.matches.fixtures() if f.player_participates)
        result=self.service.matches.play(fixture.id);person=result.players[0]['person_id'];before=self.dump()
        self.window.profiles.open(person);dialog=self.window.profiles.dialog;panel=dialog.panels[0]
        panel.tabs.setCurrentIndex(3);panel.record_tabs.setCurrentIndex(3);QTest.qWait(150)
        self.assertEqual(panel.skill_total_table.rowCount(),8)
        for row in range(8):
            table=panel.skill_total_table
            self.assertEqual(int(table.item(row,3).text()),int(table.item(row,1).text())+int(table.item(row,2).text()))
        self.assertEqual(sum(int(panel.skill_total_table.item(row,3).text()) for row in range(8)),60)
        dialog.grab().save(str(ROOT/'.test-artifacts/integrated17_skill_totals.png'))
        self.assertEqual(before,self.dump());self.assertEqual(self.service.matches.result(result.match_id),result)


if __name__=='__main__':
    names=('test_native_four_profile_states','test_extended_fatigue_growth_condition_and_original_values',
        'test_new_match_actual_skill_totals_and_group_counts_without_reroll',
        'test_other_agency_search_click_profile_filters_compare_and_close_no_write',
        'test_candidate_click_shows_same_estimates_no_pick_and_pa_not_in_widget',
        'test_small_window_and_repeated_profiles_release_and_latest_ca_refresh')
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(IntegratedNative(n) for n in names))
    (ROOT/'.test-artifacts/integrated17_windows_ui.json').write_text(json.dumps(dict(tests=result.testsRun,
        success=result.wasSuccessful(),qt_platform=IntegratedNative.app.platformName(),actual_save_modified=False),indent=2),encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
