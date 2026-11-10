import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','windows')
from contextlib import closing
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from tests import test_season32 as fixture
from idol_manager.ui.main_window import MainWindow
from idol_manager.squads import SquadError

class PreparationVacancyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        fixture.Season32Tests.setUpClass.__func__(cls)
    setUp=fixture.Season32Tests.setUp
    day=fixture.Season32Tests.day
    def missing(self,n=3):
        self.day(230)
        with closing(self.db.connect()) as c,c:
            from idol_manager.market_service import _close,active_contract,_move
            ids=[r[0] for r in c.execute("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='first_team' ORDER BY person_id LIMIT ?",(n,))]
            for person in ids:
                _close(c,active_contract(c,person),230);_move(c,person,None,'fa','fixture_departure')
    def move_one(self):
        snap=self.service.squads.snapshot();person=next(m.id for m in snap.members if m.squad=='second_team')
        self.service.squads.move(person,'first_team',expected_revision=snap.revision);return person
    def counts(self):
        snap=self.service.squads.snapshot()
        return sum(m.squad=='first_team' for m in snap.members),sum(m.squad=='second_team' for m in snap.members)
    def test_fill_vacancies_debut_and_regular_start(self):
        self.missing();self.assertEqual(self.counts(),(2,11))
        with closing(self.db.connect()) as c:
            draft=[tuple(r) for r in c.execute('SELECT * FROM draft_picks')]
            fixtures=[tuple(r) for r in c.execute('SELECT * FROM scheduled_matches WHERE season=1')]
        for _ in range(3):self.move_one()
        self.assertEqual(self.counts(),(5,8))
        with self.assertRaises(SquadError):self.move_one()
        with closing(self.db.connect()) as c,c:
            from idol_manager.market_service import _move,_new_contract
            person=c.execute("SELECT person_id FROM roster_memberships WHERE agency_id IS NULL AND person_id NOT IN (SELECT person_id FROM professional_history) LIMIT 1").fetchone()[0]
            c.execute('UPDATE idols SET age=18 WHERE person_id=?',(person,))
            contract=_new_contract(c,person,'ador',0,1,'free_trainee');_move(c,person,'ador','trainee','fixture_trainee',contract)
        self.service.market.seed_factory=lambda:1
        n=self.service.market.start_negotiation('ador',person,'debut')
        self.assertTrue(self.service.market.offer(n,30000000,1,request_id='debut-after-fill')['accepted'])
        self.assertEqual(self.counts(),(5,9))
        for squad in ('first_team','second_team'):
            snap=self.service.squads.snapshot()
            if squad not in dict(snap.leaders):
                leader=next(m.id for m in snap.members if m.squad==squad)
                self.service.squads.set_leader(squad,leader,expected_revision=snap.revision)
        self.service.calendar.advance_day(expected_absolute_day=230)
        self.assertEqual(self.service.calendar.state().date.absolute_day,231)
        with closing(self.db.connect()) as c:
            self.assertEqual(draft,[tuple(r) for r in c.execute('SELECT * FROM draft_picks')])
            self.assertEqual(fixtures,[tuple(r) for r in c.execute('SELECT * FROM scheduled_matches WHERE season=1')])
    def test_regular_tuesday_and_general_preparation_moves_stay_blocked(self):
        self.missing();snap=self.service.squads.snapshot()
        first=next(m.id for m in snap.members if m.squad=='first_team');second=next(m.id for m in snap.members if m.squad=='second_team')
        with self.assertRaises(SquadError):self.service.squads.swap(first,second,expected_revision=snap.revision)
        with self.assertRaises(SquadError):self.service.squads.move(first,'second_team',expected_revision=snap.revision)
        self.day(232)
        with self.assertRaises(SquadError):self.move_one()
        self.day(231);self.move_one();self.assertEqual(self.counts(),(3,10))
    def test_injury_return_guard_preserved(self):
        self.missing();snap=self.service.squads.snapshot();second=next(m.id for m in snap.members if m.squad=='second_team')
        with closing(self.db.connect()) as c,c:c.execute('UPDATE player_conditions SET return_not_before=238 WHERE person_id=?',(second,))
        with self.assertRaisesRegex(SquadError,'복귀 제한'):self.service.squads.move(second,'first_team',expected_revision=snap.revision)
        self.assertEqual(self.counts(),(2,11))
    def test_windows_qt_promotion_button_on_preparation_sunday(self):
        self.missing();w=MainWindow(self.service);self.addCleanup(w.close)
        w.resize(1600,950);w.show();w.show_squads();p=w.squad_page;QTest.qWait(120)
        for row in range(p.proxy.rowCount()):
            member=p.model.rows[p.proxy.mapToSource(p.proxy.index(row,1)).row()]
            if member.squad=='second_team':p.table.setCurrentIndex(p.proxy.index(row,2));break
        QTest.qWait(30);self.assertTrue(p.promote_button.isEnabled());self.assertFalse(p.swap_button.isEnabled())
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):p.promote_button.click()
        self.assertEqual(self.counts(),(3,10));self.assertIn('저장',p.action_status.text())
