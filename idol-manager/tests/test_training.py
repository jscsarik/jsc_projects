"""Targeted Tuesday training checks using disposable saves, never user slots."""
import os,json,unittest
os.environ.setdefault('QT_QPA_PLATFORM','windows')
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtTest import QTest
from idol_manager.development_rules import Development,second_probabilities
from idol_manager.development_service import capture_day
from idol_manager.training_service import TrainingService,close_tuesday
from idol_manager.finance_service import settle_week
from tests.test_development import Fixed
from tests import test_market as fixture

class TrainingRuleTests(unittest.TestCase):
    def test_high_attribute_probabilities(self):
        for value,up,down in ((89,.22,.445),(90,.30,.20),(95,.15,.10),(99,.03,.02),(100,0,0)):
            actual=second_probabilities(value)
            self.assertAlmostEqual(actual[0],up);self.assertAlmostEqual(actual[1],down)
    def test_three_independent_skills_and_focus_down_protection(self):
        m=Development([90]*8,[100]*8,Fixed());m.second(focus='vocal',hinted=True)
        self.assertEqual(m.values,[92,90,90,90,90,90,90,90])
        self.assertEqual(len([t for t in m.trials if t['kind']=='second_up']),3)
        self.assertTrue(next(t for t in m.trials if t['kind']=='second_net')['down_prevented'])
        self.assertAlmostEqual(next(t for t in m.trials if t['kind']=='focus' and 'probability' in t)['probability'],.27)
        capped=Development([90]*8,[90]*8,Fixed());capped.second(focus='vocal')
        self.assertEqual(capped.values,[90]*8)

class TrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The shared match fixture advances through Tuesday before copying the
        # save. Training tests need an untouched training week to test decisions.
        with patch('idol_manager.ai_training.plan'):
            fixture.MarketTests.setUpClass.__func__(cls)
    setUp=fixture.MarketTests.setUp
    day=fixture.MarketTests.day;rows=fixture.MarketTests.rows;dump=fixture.MarketTests.dump
    def selected(self):return self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='second_team' ORDER BY person_id LIMIT 1")[0][0]
    def save_focus(self):
        self.day(1);p=self.selected();self.service.training.save('ador',{p:'vocal'},expected_revision=0)
        return p,self.service.training.save('ador',{p:'vocal'},confirm=True,expected_revision=1)
    def settle(self):
        with closing(self.db.connect()) as c,c:
            for day in range(7):capture_day(c,day)
        self.day(7);self.service.development.settle_current()
        with closing(self.db.connect()) as c,c:settle_week(c,6)

    def test_tuesday_edit_confirm_cost_once_and_day_guard(self):
        p=self.selected();before=self.rows("SELECT funds_krw FROM agencies WHERE id='ador'")[0][0]
        with self.assertRaises(ValueError):self.service.training.save('ador',{p:'vocal'},expected_revision=0)
        self.day(1);state=self.service.training.save('ador',{p:'dance'},expected_revision=0)
        with closing(self.db.connect()) as c:self.assertRaises(ValueError,close_tuesday,c,1)
        state=self.service.training.save('ador',{p:'vocal'},confirm=True,expected_revision=state['revision'])
        self.assertTrue(state['confirmed']);self.assertEqual(before-self.rows("SELECT funds_krw FROM agencies WHERE id='ador'")[0][0],150000)
        self.service.training.save('ador',{p:'vocal'},confirm=True,expected_revision=state['revision'])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM finance_ledger WHERE kind='focus_training'"),[(1,)])
        with self.assertRaises(ValueError):self.service.training.save('ador',{p:'rap'},confirm=True,expected_revision=state['revision'])
        self.day(2)
        with self.assertRaises(ValueError):self.service.training.save('ador',{p:'rap'},expected_revision=state['revision'])
        self.assertEqual(self.service.training.state('ador')['players'][0]['skills'].__len__(),8)

    def test_no_focus_first_team_rejection_funds_and_debt_guards(self):
        self.day(1);p=self.selected()
        first=self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='first_team' LIMIT 1")[0][0]
        with self.assertRaises(ValueError):self.service.training.save('ador',{first:'vocal'},expected_revision=0)
        with closing(self.db.connect()) as c,c:c.execute("UPDATE agencies SET funds_krw=0 WHERE id='ador'")
        before=self.dump()
        with self.assertRaises(ValueError):self.service.training.save('ador',{p:'vocal'},confirm=True,expected_revision=0)
        self.assertEqual(before,self.dump())
        with closing(self.db.connect()) as c,c:c.execute("UPDATE agencies SET funds_krw=1000000 WHERE id='ador'")
        with patch('idol_manager.finance_service.debt',return_value=1):
            with self.assertRaises(ValueError):self.service.training.save('ador',{p:'vocal'},confirm=True,expected_revision=0)
        state=self.service.training.save('ador',{p:None},confirm=True,expected_revision=0);self.assertTrue(state['confirmed'])
        self.assertFalse(self.rows("SELECT 1 FROM finance_ledger WHERE kind='focus_training'"))

    def test_monday_saved_results_basic_cost_no_duplicate_and_load_privacy(self):
        p,state=self.save_focus();self.assertEqual(self.service.training.details('ador',p),[])
        self.settle();records=self.service.training.details('ador',p)
        self.assertTrue(any(r['kind']=='집중 훈련' for r in records))
        self.assertEqual(sum(r['kind']=='기본 성장' for r in records),3)
        self.assertTrue(all(r['day']==7 for r in records))
        self.assertEqual(self.rows("SELECT amount FROM finance_ledger WHERE person_id=? AND kind='second_training'",(p,)),[(100000,)])
        self.assertEqual(self.rows("SELECT amount FROM finance_ledger WHERE person_id=? AND kind='focus_training'",(p,)),[(150000,)])
        before=self.dump();self.service.development.settle_current()
        with closing(self.db.connect()) as c,c:settle_week(c,6)
        self.assertEqual(before,self.dump())
        from idol_manager.database import Database
        loaded=TrainingService(Database(self.path));self.assertEqual(records,loaded.details('ador',p))
        with closing(self.db.connect()) as c:
            c.set_authorizer(lambda a,t,col,*_:__import__('sqlite3').SQLITE_DENY if col in ('potential','archetype') else __import__('sqlite3').SQLITE_OK)
            from idol_manager.training_service import public_trials
            # Public detail uses only saved CA/trials and never reads abilities.PA.
            with patch.object(loaded.database,'connect',return_value=c):self.assertEqual(records,loaded.details('ador',p))
        for r in records:
            self.assertNotIn('potential',r);self.assertNotIn('roll',r)
            if r['kind']=='PA 격차 추가 성장':self.assertIsNone(r['up'])

    def test_v21_backup_migration_keeps_saved_data_and_other_growth_rules(self):
        from idol_manager.database import Database
        tables=('abilities','game_clock','agencies','roster_memberships','draft_picks','finance_ledger','scheduled_matches')
        with closing(self.db.connect()) as c,c:
            c.execute('DROP TABLE training_choices');c.execute('DROP TABLE training_sheets')
            c.execute("UPDATE development_runtime SET rules_json=json_set(rules_json,'$.weekly_basic.second_team_skills',2)")
            old=json.loads(c.execute('SELECT rules_json FROM development_runtime').fetchone()[0])
            before={t:[tuple(r) for r in c.execute('SELECT * FROM '+t)] for t in tables}
            c.execute('PRAGMA user_version=21')
        db=Database(self.path);self.assertTrue(db.last_backup_path.is_file())
        with closing(db.connect()) as c:
            new=json.loads(c.execute('SELECT rules_json FROM development_runtime').fetchone()[0])
            self.assertEqual(new['weekly_basic']['second_team_skills'],3)
            for key in ('first_team_up_multipliers','first_team_down_multipliers','trainee_skills','trainee_up_multiplier'):
                self.assertEqual(old['weekly_basic'][key],new['weekly_basic'][key])
            self.assertEqual(old['gap_chances'],new['gap_chances']);self.assertEqual(old['aging_thresholds'],new['aging_thresholds'])
            for t in tables:self.assertEqual(before[t],[tuple(r) for r in c.execute('SELECT * FROM '+t)])

    def test_training_gui_double_click_sort_and_theme(self):
        p,state=self.save_focus();self.settle();self.day(8)
        from idol_manager.ui.main_window import MainWindow
        from idol_manager.ui.theme_manager import ThemeManager
        manager=ThemeManager(QApplication.instance(),self.base/'training-appearance.ini')
        self.addCleanup(lambda:QApplication.instance().removeEventFilter(manager))
        self.addCleanup(lambda:manager.set_mode('light',persist=False))
        w=MainWindow(self.service);self.addCleanup(w.close);w.resize(1300,900);w.show();w.show_training();QTest.qWait(160)
        page=w.training_page;self.assertTrue(page.isVisible())
        expected_second={x['id'] for x in page.snapshot['players'] if x['career_status']=='second_team'}
        self.assertEqual({page.table.item(r,0).data(Qt.ItemDataRole.UserRole) for r in range(page.table.rowCount())},expected_second)
        self.assertTrue(all(page.table.item(r,2).text()=='2군' for r in range(page.table.rowCount())))
        for row in range(page.table.rowCount()):
            person=next(x for x in page.snapshot['players'] if x['id']==page.table.item(row,0).data(Qt.ItemDataRole.UserRole))
            self.assertEqual(page.table.item(row,3).data(Qt.ItemDataRole.DisplayRole),round(sum(person['skills'])/8,1))
        self.assertIs(w.pages.currentWidget(),w.development_hub)
        self.assertEqual(w.development_tabs.count(),2)
        self.assertNotIn(w.training_menu,[button for button,_ in w.navigation_pages])
        self.assertTrue(w.training_menu.isHidden())
        w.show_development();self.assertTrue(w.development_page.isVisible());w.show_training()
        manager.set_mode('dark');QTest.qWait(80)
        page.table.sortItems(1,Qt.SortOrder.DescendingOrder)
        row=next(i for i in range(page.table.rowCount()) if page.table.item(i,0).data(Qt.ItemDataRole.UserRole)==p)
        pager=getattr(page.table,'_portrait_pager',None)
        if pager and page.table.isRowHidden(row):
            pager.row_page=row//pager.page_size;pager.signature=None;pager.refresh()
        page.table.selectRow(row);page.table.scrollToItem(page.table.item(row,1));QTest.qWait(40)
        self.assertTrue(page.apply.isEnabled());page.focus.setCurrentIndex(page.focus.findData('dance'))
        QTest.mouseClick(page.apply,Qt.MouseButton.LeftButton);QTest.qWait(40)
        self.assertEqual(next(x for x in self.service.training.state('ador')['players'] if x['id']==p)['focus'],'dance')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):QTest.mouseClick(page.confirm,Qt.MouseButton.LeftButton)
        self.assertTrue(self.service.training.state('ador')['confirmed'])
        row=next(i for i in range(page.table.rowCount()) if page.table.item(i,0).data(Qt.ItemDataRole.UserRole)==p)
        page.table.selectRow(row);page.table.scrollToItem(page.table.item(row,1));QTest.qWait(40)
        rect=page.table.visualItemRect(page.table.item(row,0))
        self.assertEqual(page.current_person(),p)
        expected=next(x for x in page.snapshot['players'] if x['id']==p)
        self.assertEqual(page.table.item(row,1).text(),expected['name'])
        self.assertFalse(page.table.item(row,0).icon().isNull())
        self.assertTrue(page.table.viewport().rect().contains(rect.center()),(row,rect,page.table.viewport().rect()))
        QTest.mouseClick(page.table.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,rect.center())
        QTest.mouseDClick(page.table.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,rect.center());QTest.qWait(120)
        self.assertIsNotNone(page.detail_dialog);self.assertTrue(page.detail_dialog.isVisible())
        self.assertGreater(page.detail_dialog.table.rowCount(),0)
        self.assertFalse(page.table.horizontalScrollBar().isVisible())
        self.assertTrue(all(not page.table.isColumnHidden(c) for c in range(page.table.columnCount())))
        self.assertTrue(all(not page.detail_dialog.table.isColumnHidden(c) for c in range(page.detail_dialog.table.columnCount())))
        out=Path(__file__).resolve().parents[1]/'reports/training';out.mkdir(exist_ok=True)
        page.detail_dialog.grab().save(str(out/'details_dark.png'));page.detail_dialog.close()
        manager.set_mode('light');w.resize(900,1600);QTest.qWait(250)
        self.assertFalse(page.table.horizontalScrollBar().isVisible())
        self.assertTrue(all(not page.table.isColumnHidden(c) for c in range(page.table.columnCount())))
        self.assertTrue(all(not page.table.isRowHidden(r) for r in range(page.table.rowCount())))
        w.grab().save(str(out/'training_light.png'))
        w.resize(1600,900);w.show_development();QTest.qWait(120)
        w.grab().save(str(out/'combined_records.png'))
        w.show_training();QTest.qWait(120);w.grab().save(str(out/'combined_training.png'))
        for show,table in ((w.show_schedule,w.schedule_page.table),(w.show_explorer,w.explorer_page.table)):
            show();QTest.qWait(160)
            from idol_manager.ui.agency_table_layout import agency_columns
            company=agency_columns(table)[0]
            self.assertLess(table.columnWidth(company),table.viewport().width()*.35)
            self.assertLessEqual(sum(table.columnWidth(c) for c in range(table.model().columnCount()) if not table.isColumnHidden(c)),table.viewport().width())

    def test_theme_toggle_preserves_table_sizes_and_manual_proportions(self):
        from idol_manager.ui.main_window import MainWindow
        from idol_manager.ui.theme_manager import ThemeManager
        manager=ThemeManager(QApplication.instance(),self.base/'stable-appearance.ini')
        self.addCleanup(lambda:QApplication.instance().removeEventFilter(manager))
        self.addCleanup(lambda:manager.set_mode('light',persist=False))
        self.settle();self.day(8)
        w=MainWindow(self.service);self.addCleanup(w.close);w.show()
        def signature(table):
            return (table.size().width(),table.size().height(),table.verticalHeader().defaultSectionSize(),
                tuple((table.columnWidth(c),table.isColumnHidden(c)) for c in range(table.columnCount())),
                tuple((table.rowHeight(r),table.isRowHidden(r)) for r in range(table.rowCount())))
        for width,height in ((1300,900),(900,1060)):
            w.resize(width,height);QTest.qWait(150)
            for show,table in ((w.show_training,w.training_page.table),(w.show_development,w.development_page.table)):
                show();QTest.qWait(180)
                if width==1300 and table is w.development_page.table:
                    header=table.horizontalHeader();header.resizeSection(1,table.columnWidth(1)+10);header.resizeSection(2,table.columnWidth(2)-10);QTest.qWait(80)
                before=signature(table)
                for mode in ('dark','light'):
                    manager.set_mode(mode);QTest.qWait(180)
                    self.assertEqual(signature(table),before,(width,mode,table is w.training_page.table))
                manager.set_mode('dark');manager.set_mode('light');QTest.qWait(180)
                self.assertEqual(signature(table),before)

    def test_click_skills_bulk_apply_by_id_and_confirm_once(self):
        from idol_manager.ui.main_window import MainWindow
        self.day(1)
        w=MainWindow(self.service);self.addCleanup(w.close);w.resize(1600,1000);w.show();w.show_training();QTest.qWait(120)
        page=w.training_page
        ids=[p['id'] for p in page.snapshot['players'] if p['career_status']=='second_team'][:2]
        def click(person,column):
            row=next(r for r in range(page.table.rowCount()) if page.table.item(r,0).data(Qt.ItemDataRole.UserRole)==person)
            page.table.scrollToItem(page.table.item(row,column));QTest.qWait(25)
            rect=page.table.visualItemRect(page.table.item(row,column))
            QTest.mouseClick(page.table.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,rect.center())
        before=self.dump()
        click(ids[0],4);page.table.sortItems(1,Qt.SortOrder.DescendingOrder);click(ids[1],5)
        self.assertEqual(page.pending,{ids[0]:'vocal',ids[1]:'dance'})
        self.assertEqual(before,self.dump())
        # Same value toggles off; selecting it again restores this player's choice only.
        click(ids[0],4);self.assertIsNone(page.pending[ids[0]])
        click(ids[0],4)
        with patch.object(self.service.training,'save',wraps=self.service.training.save) as saved:
            QTest.mouseClick(page.apply,Qt.MouseButton.LeftButton);QTest.qWait(30)
            self.assertEqual(saved.call_count,1)
        self.assertFalse(page.pending)
        state=self.service.training.state('ador')
        for person,skill in zip(ids,('vocal','dance')):
            self.assertEqual(next(p['focus'] for p in state['players'] if p['id']==person),skill)
        self.assertFalse(state['confirmed'])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM finance_ledger WHERE kind='focus_training'"),[(0,)])
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):
            QTest.mouseClick(page.confirm,Qt.MouseButton.LeftButton)
        self.assertTrue(self.service.training.state('ador')['confirmed'])
        self.assertEqual(self.rows("SELECT SUM(amount) FROM finance_ledger WHERE kind='focus_training'"),[(300000,)])
        final=self.dump();click(ids[0],6);self.assertFalse(page.pending);self.assertEqual(final,self.dump())
        page.reload()
        self.assertEqual(next(p['focus'] for p in page.snapshot['players'] if p['id']==ids[0]),'vocal')
