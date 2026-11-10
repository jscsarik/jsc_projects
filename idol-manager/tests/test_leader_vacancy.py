import os,unittest,sqlite3
os.environ.setdefault('QT_QPA_PLATFORM','windows')
from contextlib import closing
from unittest.mock import patch
from tests import test_season32 as fixture
from idol_manager.database import Database
from idol_manager.squads import SquadError

class LeaderVacancyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.Season32Tests.setUpClass.__func__(cls)
    setUp=fixture.Season32Tests.setUp
    rows=fixture.Season32Tests.rows
    day=fixture.Season32Tests.day
    def vacancy(self,day=97):
        self.day(day)
        with closing(self.db.connect()) as c,c:c.execute("DELETE FROM squad_leaders WHERE agency_id='ador' AND squad='second_team'")
        return self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='second_team' ORDER BY person_id LIMIT 1")[0][0]

    def test_maintenance_sunday_fill_and_progress_no_date_reset(self):
        p=self.vacancy();snapshot=self.service.squads.snapshot()
        protected={t:self.rows('SELECT * FROM '+t+' ORDER BY 1') for t in ('abilities','idols','draft_picks','scheduled_matches','agencies','roster_memberships')}
        with patch.object(self.service.calendar,'_pending',return_value=0):
            with self.assertRaisesRegex(ValueError,'리더'):self.service.calendar.advance_day(expected_absolute_day=97)
        self.service.squads.set_leader('second_team',p,expected_revision=snapshot.revision)
        self.assertEqual(self.rows('SELECT absolute_day FROM game_clock'),[(97,)])
        for t,before in protected.items():self.assertEqual(before,self.rows('SELECT * FROM '+t+' ORDER BY 1'),t)
        self.assertEqual(dict(type(self.service)(self.root,database_path=self.path).squads.snapshot().leaders)['second_team'],p)
        with patch.object(self.service.calendar,'_pending',return_value=0):
            day=self.service.calendar.advance_day(expected_absolute_day=97)
        self.assertEqual(day.absolute_day,98)

    def test_existing_leader_swap_and_regular_tuesday_still_blocked(self):
        p=self.vacancy();snapshot=self.service.squads.snapshot()
        first=next(m.id for m in snapshot.members if m.squad=='first_team')
        with self.assertRaises(SquadError):self.service.squads.swap(first,p,expected_revision=snapshot.revision)
        self.service.squads.set_leader('second_team',p,expected_revision=snapshot.revision)
        other=self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='second_team' AND person_id!=? LIMIT 1",(p,))[0][0]
        with self.assertRaises(SquadError):self.service.squads.set_leader('second_team',other,expected_revision=self.service.squads.snapshot().revision)
        with closing(self.db.connect()) as c,c:
            with self.assertRaises(sqlite3.IntegrityError):c.execute("UPDATE squad_leaders SET person_id=? WHERE agency_id='ador' AND squad='second_team'",(other,))
        self.vacancy(8)
        with self.assertRaises(SquadError):self.service.squads.set_leader('second_team',p,expected_revision=self.service.squads.snapshot().revision)
        self.day(14);self.service.squads.set_leader('second_team',p,expected_revision=self.service.squads.snapshot().revision)

    def test_prepared_game_still_blocks_vacancy_repair(self):
        self.day(9);self.service.calendar.ensure_current_schedule()
        match=self.rows('SELECT id FROM scheduled_matches WHERE week=1 AND weekday=2 ORDER BY match_order LIMIT 1')[0][0]
        self.service.matches._prepare(match,None,None)
        p=self.vacancy()
        with self.assertRaises(SquadError):self.service.squads.set_leader('second_team',p,expected_revision=self.service.squads.snapshot().revision)
        with closing(self.db.connect()) as c,c:
            with self.assertRaises(sqlite3.IntegrityError):c.execute("INSERT INTO squad_leaders VALUES ('ador','second_team',?)",(p,))

    def test_preparation_vacancy_wrong_squad_and_stale_revision(self):
        p=self.vacancy(230);snapshot=self.service.squads.snapshot()
        wrong=next(m.id for m in snapshot.members if m.squad=='first_team')
        with self.assertRaises(SquadError):self.service.squads.set_leader('second_team',wrong,expected_revision=snapshot.revision)
        with self.assertRaises(SquadError):self.service.squads.set_leader('second_team',p,expected_revision=snapshot.revision+1)
        self.service.squads.set_leader('second_team',p,expected_revision=snapshot.revision)

    def test_same_team_same_squad_market_update_keeps_leader(self):
        from idol_manager.market_service import _move
        self.day(97);p=dict(self.service.squads.snapshot().leaders)['second_team']
        with closing(self.db.connect()) as c,c:_move(c,p,'ador','second_team','fixture_same_role')
        self.assertEqual(dict(self.service.squads.snapshot().leaders)['second_team'],p)

    def test_migration_backup_changes_only_trigger(self):
        self.vacancy();before={t:self.rows('SELECT * FROM '+t+' ORDER BY 1') for t in ('squad_leaders','game_clock','abilities','draft_picks','scheduled_matches','agencies')}
        with closing(self.db.connect()) as c,c:
            c.execute('DROP TABLE maintenance_condition_resets')
            c.execute('PRAGMA user_version=26')
        db=Database(self.path);self.assertTrue(db.last_backup_path.exists())
        for t,data in before.items():self.assertEqual(data,self.rows('SELECT * FROM '+t+' ORDER BY 1'))
        self.assertEqual(self.rows('PRAGMA foreign_key_check'),[])

    def test_gui_only_vacant_leader_button_enabled_and_click_saves(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from idol_manager.ui.main_window import MainWindow
        app=QApplication.instance() or QApplication([]);p=self.vacancy()
        window=MainWindow(self.service);self.addCleanup(window.close);window.show_squads();window.show();QTest.qWait(90)
        page=window.squad_page
        self.assertTrue(page.second_leader_button.isEnabled());self.assertFalse(page.first_leader_button.isEnabled());self.assertFalse(page.swap_button.isEnabled())
        page.second_leader_combo.setCurrentIndex(page.second_leader_combo.findData(p));page.second_leader_button.click()
        for _ in range(200):
            QTest.qWait(10)
            if not page.is_busy():break
        self.assertEqual(dict(self.service.squads.snapshot().leaders)['second_team'],p)
        self.assertFalse(page.second_leader_button.isEnabled())
