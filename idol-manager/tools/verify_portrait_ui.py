"""Render every page at 900x1600 against a disposable game, no live save writes."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from contextlib import closing
import sys,json,sqlite3
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QRect
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractScrollArea,QWidget
from tests.test_market import MarketTests
from idol_manager.ui.main_window import MainWindow

def audit(window):
    issues=[]
    for child in window.findChildren(QWidget):
        if child.window() is not window or not child.isVisible() or child.visibleRegion().isEmpty():continue
        if isinstance(child,QAbstractScrollArea):
            for orientation,bar in [('horizontal',child.horizontalScrollBar()),('vertical',child.verticalScrollBar())]:
                if bar.isVisible() or bar.maximum()>0:issues.append([child.__class__.__name__,'scrollbar',orientation,bar.maximum()])
        if child.isWindow():continue
        # Containers may contain intentionally inactive tab pages. Check controls/text.
        if child.__class__.__name__ in ('QPushButton','QLabel','QComboBox','QSpinBox','QLineEdit','QTabBar'):
            rect=QRect(child.mapTo(window,child.rect().topLeft()),child.size())
            if rect.left()<0 or rect.top()<0 or rect.right()>=window.width()+2 or rect.bottom()>=window.height()+2:
                issues.append([child.__class__.__name__,getattr(child,'text',lambda:'' )()[:100],list((rect.x(),rect.y(),rect.width(),rect.height()))])
    return issues

def main():
    fixture=MarketTests('test_public_candidate_ca_health_salary_not_leaked_no_pa_sql')
    MarketTests.setUpClass();fixture.setUp()
    if fixture.app.platformName()=='offscreen':QFontDatabase.addApplicationFont('C:/Windows/Fonts/malgun.ttf')
    window=None
    try:
        if '--save-copy' in sys.argv:
            from idol_manager.service import GameService
            with closing(sqlite3.connect((ROOT/'data/idol_manager.sqlite3').resolve().as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(fixture.path)) as dst:src.backup(dst)
            fixture.service=GameService(ROOT,fixture.path)
        before=fixture.dump();window=MainWindow(fixture.service);window.resize(900,1560);window.show();window.resize(900,1560);QTest.qWait(200)
        report={}
        methods=('show_roster','show_draft','show_squads','show_schedule','show_matches','show_specials','show_finals','show_development','show_explorer','show_finance','show_market')
        out=ROOT/('.test-artifacts/portrait_windows' if fixture.app.platformName()=='windows' else '.test-artifacts/portrait');out.mkdir(exist_ok=True)
        for method in methods:
            getattr(window,method)();QTest.qWait(180)
            page=window.pages.currentWidget();tabs=getattr(page,'tabs',None)
            indexes=range(tabs.count()) if tabs is not None else [None]
            for index in indexes:
                if index is not None:tabs.setCurrentIndex(index)
                QTest.qWait(120);window.portrait_layout.refresh();QTest.qWait(70)
                key=method+('' if index is None else '_'+str(index))
                report[key]={'size':[window.width(),window.height()],'issues':audit(window)}
                window.grab().save(str(out/(key+'.png')))
        window.show_matches();page=window.match_page
        page.battle.configure('레이아웃 검사 · 5명 대 5명', [('a','검사 기획사 A'),('b','검사 기획사 B')],
            [dict(id=f'{team}{i}',agency_id=team,name=f'검사 선수 {i+1}',leader=i==0,photo_path='') for team in ('a','b') for i in range(5)])
        page.tabs.setCurrentIndex(1);QTest.qWait(250)
        report['battle_5v5']={'size':[window.width(),window.height()],'issues':audit(window)}
        window.grab().save(str(out/'battle_5v5.png'))
        page.details_button.click();QTest.qWait(200)
        report['battle_details']={'size':[window.width(),window.height()],'issues':audit(window)}
        window.grab().save(str(out/'battle_details.png'))
        page.details_button.click()
        for compare in (False,True):
            people=[p.id for p in fixture.service.agency_roster(fixture.service.draft_session.player_agency())][:2 if compare else 1]
            window.profiles.compare(people);dialog=window.profiles.dialog
            QTest.qWait(150)
            for p,panel in enumerate(dialog.panels):
                for i in range(panel.tabs.count()):
                    # Parent comparison selector uses one profile at a time.
                    parent=panel.parentWidget()
                    if parent and hasattr(parent,'setCurrentWidget'):parent.setCurrentWidget(panel)
                    if parent and parent.parentWidget() and hasattr(parent.parentWidget(),'setCurrentWidget'):parent.parentWidget().setCurrentWidget(panel)
                    panel.tabs.setCurrentIndex(i);QTest.qWait(100);window.portrait_layout.refresh();QTest.qWait(70)
                    key=f'profile_{int(compare)}_{p}_{i}'
                    report[key]={'size':[dialog.width(),dialog.height()],'issues':audit(dialog)}
                    dialog.grab().save(str(out/(key+'.png')))
            dialog.close();QTest.qWait(60)
        report['save_unchanged']=before==fixture.dump()
        (out/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
        assert report['save_unchanged'],'Opening UI changed the disposable save'
        assert not any(r['issues'] for r in report.values() if isinstance(r,dict)), 'Scroll/overflow audit failed'
    finally:
        if window:window.close()
        fixture.doCleanups()

if __name__=='__main__':main()

