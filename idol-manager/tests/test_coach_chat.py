import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','windows')
from contextlib import closing
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QDialog
from PySide6.QtTest import QTest
from idol_manager.coach_service import CoachService
from tests import test_season32 as fixture

class CoachChatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.Season32Tests.setUpClass.__func__(cls)
    setUp=fixture.Season32Tests.setUp
    rows=fixture.Season32Tests.rows
    day=fixture.Season32Tests.day

    def test_today_tasks_only_old_unread_and_result_reports_stay_archived(self):
        self.day(7);api=CoachService(self.db);rows=api.refresh()
        self.assertTrue(rows);self.assertTrue(all(r['absolute_day']==7 and r['kind']=='daily' for r in rows))
        self.day(8);today=api.refresh()
        self.assertTrue(all(r['absolute_day']==8 and r['kind']=='daily' for r in today))
        self.assertTrue(any(t['target']=='training' for r in today for t in r['targets']))
        self.assertTrue(self.rows("SELECT report_key FROM coach_reports WHERE absolute_day=7 AND kind='daily'"))
        self.assertEqual([r['report_key'] for r in today],[r['report_key'] for r in api.refresh()])

    def test_chat_window_and_today_read_action_and_next_day_refresh(self):
        from idol_manager.ui.main_window import MainWindow
        app=QApplication.instance() or QApplication([])
        self.day(8);window=MainWindow(self.service);self.addCleanup(window.close)
        window.show();panel=window.coach_panel;panel.refresh();panel.expand();QTest.qWait(80)
        self.assertIsInstance(panel.body,QDialog);self.assertTrue(panel.body.isVisible())
        from PySide6.QtCore import QPoint
        self.assertLess(panel.mapTo(window,QPoint(0,0)).x(),230)
        self.assertGreater(panel.mapTo(window,QPoint(0,0)).y(),window.height()/2)
        self.assertEqual(window.notes_button.text(),'메모');self.assertFalse(hasattr(window,'chat_button'))
        self.assertIs(window.notes_button.parentWidget(),window.chat_header.parentWidget())
        self.assertGreater(window.notes_button.x(),window.chat_header.x())
        self.assertEqual(window.utility_row.count(),1)
        self.assertGreater(panel.width(),window.notes_button.width()*2)
        window.notes_button.click();self.assertTrue(window.notes.isVisible());window.notes.close()
        self.assertTrue(panel.body.isWindow());self.assertIn('오늘의 할 일',panel.heading.text())
        self.assertIn('화요일',panel.browser.toPlainText());self.assertTrue(panel.blink.isActive())
        panel.mark_all();self.assertFalse(panel.blink.isActive())
        self.day(9);panel.refresh()
        text=panel.browser.toPlainText();self.assertIn('수요일',text);self.assertNotIn('화요일',text)
        self.assertTrue(panel.blink.isActive())
        output=__import__('pathlib').Path('reports/coach_chat');output.mkdir(exist_ok=True)
        panel.body.grab().save(str(output/'today.png'))
        panel.body.close();self.assertFalse(panel.body.isVisible());panel.expand();self.assertTrue(panel.body.isVisible())
        self.assertEqual(self.rows('SELECT COUNT(*) FROM scheduled_matches'),[(585,)])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM draft_picks'),[(160,)])
    def test_announcements_empty_and_populated_and_panel_render(self):
        from idol_manager.game_clock import GameDate
        from idol_manager.ui.main_window import MainWindow
        import json
        app=QApplication.instance() or QApplication([])
        self.day(8)
        api=CoachService(self.db)
        
        # 1. 초기 상태: 결과 발표 없음
        initial_ann=api.announcements(GameDate(8))
        self.assertEqual(initial_ann, [])
        window=MainWindow(self.service);self.addCleanup(window.close)
        window.show()
        panel=window.coach_panel;panel.refresh();panel.expand()
        self.assertIn('결과 발표', panel.browser.toHtml())
        self.assertIn('오늘 전달할 결과 발표는 없습니다.', panel.browser.toPlainText())

        # 2. 결과 데이터 주입 (성장 결과, 부상)
        with closing(self.db.connect()) as c, c:
            sid = 'growth:999'
            c.execute("INSERT OR REPLACE INTO development_settlements VALUES (?, 1, 8, 'growth', 1, 8, 'seed', 'v1')", (sid,))
            agency = c.execute("SELECT agency_id FROM player_settings WHERE game_id=1").fetchone()[0]
            member = c.execute("SELECT person_id FROM roster_memberships WHERE agency_id=? LIMIT 1", (agency,)).fetchone()
            p_id = member[0] if member else c.execute("SELECT id FROM people LIMIT 1").fetchone()[0]

            c.execute("INSERT OR REPLACE INTO development_results VALUES (?, ?, ?, 'first_team', 19, 19, '[]', '[]', '[1,1,1]', 1, '[]', '[]')",
                      (sid, p_id, agency))
            c.execute("INSERT OR REPLACE INTO development_trials VALUES (?, ?, 1, ?)", 
                      (sid, p_id, json.dumps({'kind': 'additional', 'applied': 3})))
            c.execute("INSERT OR REPLACE INTO condition_events VALUES ('inj_test', 1, ?, 8, 'match', 0.1, 0.05, 1, '{}')", (p_id,))

        # 3. 주입 후 announcements 확인
        ann = api.announcements(GameDate(8))
        self.assertTrue(len(ann) >= 2)
        self.assertTrue(any('잠재력 추가 성장 주목' in item for item in ann))
        self.assertTrue(any('주간 성장 완료' in item for item in ann))
        self.assertTrue(any('부상 발생' in item for item in ann))

        # 4. 패널 렌더링 확인
        panel.refresh()
        rendered_text = panel.browser.toPlainText()
        self.assertIn('잠재력 추가 성장 주목', rendered_text)
        self.assertIn('주간 성장 완료', rendered_text)
        self.assertIn('부상 발생', rendered_text)
        self.assertNotIn('오늘 전달할 결과 발표는 없습니다.', rendered_text)

        # 5. 읽음 처리 후에도 결과 발표 유지 확인
        panel.mark_all()
        panel.refresh()
        self.assertIn('잠재력 추가 성장 주목', panel.browser.toPlainText())
        panel.body.close()

