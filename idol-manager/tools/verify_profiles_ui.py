"""Native Windows profile interactions and five screenshots, disposable save only."""
import os
os.environ['QT_QPA_PLATFORM']='windows'
from pathlib import Path
from contextlib import closing
import json,shutil,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtTest import QTest
from tests.test_profile_ui import ProfileUITests


class NativeProfiles(ProfileUITests):
    def test_native_four_profile_states(self):
        sources=[p for p in (ROOT/'assets/idols').iterdir() if p.suffix.lower() in ('.png','.jpg','.jpeg','.webp')]
        if sources:
            for i,target in enumerate((self.base/'assets/idols').glob('*.png')):shutil.copyfile(sources[i%len(sources)],target)
        fixture=next(f for f in self.service.matches.fixtures() if f.player_participates)
        result=self.service.matches.play(fixture.id)
        person=next(p['person_id'] for p in result.players if p['agency_id']!='ador')
        with closing(self.db.connect()) as c,c:
            c.execute('UPDATE idols SET age=30 WHERE person_id=?',(person,))
            c.execute('UPDATE game_clock SET absolute_day=7')
            for day in range(7):c.execute('''INSERT OR REPLACE INTO development_days
                SELECT 1,?,person_id,agency_id,career_status,0 FROM roster_memberships WHERE agency_id IS NOT NULL''',(day,))
        self.service.development.settle_current()
        with closing(self.db.connect()) as c,c:
            c.execute('UPDATE player_conditions SET registration_weeks=4,registration_week=1 WHERE person_id=?',(person,))
        before=self.dump();self.window.profiles.open(person);dialog=self.window.profiles.dialog
        self.assertTrue(QTest.qWaitForWindowExposed(dialog,5000));dialog.raise_();dialog.activateWindow();QTest.qWait(200)
        panel=dialog.panels[0]
        self.assertTrue(panel.data['exact']);self.assertEqual(panel.data['condition']['multiplier'],20)
        self.assertTrue(panel.data['matches']);self.assertTrue(panel.data['growth'])
        for tab,name in ((1,'other_agency'),(2,'condition_week4'),(3,'match_records'),(4,'growth_records')):
            panel.tabs.setCurrentIndex(tab);QTest.qWait(150)
            dialog.grab().save(str(ROOT/f'.test-artifacts/profile_windows_{name}.png'))
        dialog.close();self.window.profiles.open(self.hidden);dialog=self.window.profiles.dialog;dialog.panels[0].tabs.setCurrentIndex(1);QTest.qWait(200)
        self.assertFalse(dialog.panels[0].data['exact']);dialog.grab().save(str(ROOT/'.test-artifacts/profile_windows_candidate.png'))
        self.assertEqual(before,self.dump());self.assertEqual(self.warnings,[])


if __name__=='__main__':
    names=('test_native_four_profile_states','test_other_agency_search_click_profile_filters_compare_and_close_no_write',
        'test_candidate_click_shows_same_estimates_no_pick_and_pa_not_in_widget','test_small_window_and_repeated_profiles_release_and_latest_ca_refresh')
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(NativeProfiles(n) for n in names))
    (ROOT/'.test-artifacts/profile_windows_ui.json').write_text(json.dumps(dict(tests=result.testsRun,success=result.wasSuccessful(),
        qt_platform=NativeProfiles.app.platformName(),actual_save_modified=False),indent=2),encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
