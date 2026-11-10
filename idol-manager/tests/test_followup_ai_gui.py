"""Actual button path for a follow-up special round without the player."""
from contextlib import closing
import unittest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from tests import test_competition_progress as fixture

class FollowupAIGUITests(unittest.TestCase):
    setUpClass=classmethod(fixture.CompetitionProgressTests.setUpClass.__func__)
    setUp=fixture.CompetitionProgressTests.setUp
    rows=fixture.CompetitionProgressTests.rows;day=fixture.CompetitionProgressTests.day
    special=fixture.CompetitionProgressTests.special;open=fixture.CompetitionProgressTests.open
    wait=fixture.CompetitionProgressTests.wait

    def test_ai_followup_button_skip_saved_result_and_next_day(self):
        event=self.special()
        # Synthetic public CA makes the player upper-group winner; only lower
        # upper-group ranks qualify for follow-up. The actual engine still rolls.
        with closing(self.db.connect()) as c,c:
            c.execute("UPDATE abilities SET value=100,potential=100 WHERE person_id IN (SELECT person_id FROM roster_memberships WHERE agency_id='ador')")
            c.execute("UPDATE idols SET average=100 WHERE person_id IN (SELECT person_id FROM roster_memberships WHERE agency_id='ador')")
        for stage in ('upper','lower'):
            r=next(r for r in self.service.specials.state(event['id'])['rounds'] if r['stage']==stage)
            self.service.specials.play(r['id'])
        final=next(r for r in self.service.specials.state(event['id'])['rounds'] if r['stage']=='final')
        self.assertNotIn('ador',final['agencies'])
        self.open();self.window.show_specials();page=self.window.special_page;page.choose_stage(final['id'])
        self.assertTrue(page.lineup_table.isHidden());self.assertEqual(page.start_button.text(),'AI 경기 진행')
        QTest.mouseClick(page.start_button,Qt.MouseButton.LeftButton);self.wait(lambda:page.job is None)
        if page.replaying:QTest.mouseClick(page.skip_button,Qt.MouseButton.LeftButton)
        saved=self.service.specials.result(final['id']);self.assertIsNotNone(saved)
        page.reload_button.click();self.assertEqual(saved,self.service.specials.result(final['id']))
        self.assertFalse(page.tabs.isTabVisible(0))
        today=self.service.calendar.state().date.absolute_day
        QTest.mouseClick(self.window.day_button,Qt.MouseButton.LeftButton)
        self.assertEqual(self.service.calendar.state().date.absolute_day,today+1)
