"""Record parity, nonblocking/stale UI queries, and cache invalidation."""
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json,sqlite3,tempfile,unittest,time
from tests import test_records as fixture
from idol_manager.records_service import RecordsService
from idol_manager.ui.records_queries import QueryCache

class Release27Tests(unittest.TestCase):
    setUpClass=classmethod(fixture.RecordsTests.setUpClass.__func__)
    setUp=fixture.RecordsTests.setUp
    dump=fixture.RecordsTests.dump
    def test_imported_legacy_photos_remain_available_to_future_intake(self):
        import hashlib
        from idol_manager.service import GameService
        from idol_manager.storage import UserPaths,import_save
        from idol_manager.annual_recruitment import scan_assets
        from tests.test_annual_draft import png
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);legacy=base/'old install';resources=base/'bundle';resources.mkdir()
            png(legacy/'assets/idols/경로 검증.png',1)
            original=GameService(legacy);source=original.database.path
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            paths=UserPaths(base/'user');import_save(source,paths)
            current=GameService(resources,storage=paths)
            self.assertEqual(current.root,resources)
            self.assertEqual(current.image_root,legacy)
            self.assertEqual(current.calendar.root,legacy)
            self.assertEqual(current.scan.image_count,1)
            with closing(current.database.connect()) as c:self.assertEqual(len(scan_assets(c,current.calendar.root)),1)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),digest)
    def test_closed_dialog_cleanup_never_dereferences_layout_parents(self):
        from PySide6.QtCore import QObject
        from idol_manager.ui.portrait_layout import PortraitLayout
        class ParentMustNotBeRead(QObject):
            def parent(self):raise AssertionError('Closing layouts may have stale native parents')
        dialog=QObject();owned=ParentMustNotBeRead();unrelated=QObject()
        layout=SimpleNamespace(tables={},boxes={owned:1,unrelated:2},tab_pickers={},text_pages={},dock_features={},dialog_objects={dialog:{owned}},dialogs=[dialog])
        layout.prune_deleted=lambda scope:PortraitLayout.prune_deleted(layout,scope)
        PortraitLayout.release_dialog(layout,dialog)
        self.assertEqual(layout.boxes,{unrelated:2});self.assertEqual(layout.dialog_objects,{})
        self.assertEqual(layout.dialogs,[])
    def test_raw_event_priority_fallback_all_filters_match_original_sql(self):
        import idol_manager.records_service as module
        old=Path(__file__).resolve().parents[1]/'reports/release27/records_service_before.py.txt'
        self.assertTrue(old.exists(),'Oracle preserved before optimization')
        namespace={'__package__':'idol_manager'};exec(compile(old.read_text(encoding='utf8'),str(old),'exec'),namespace)
        for season,kind in ((None,None),(1,'regular'),(2,'regular'),(None,'special'),(None,'postseason'),(None,'tiebreak')):
            with self.subTest(season=season,kind=kind):
                expected=namespace['RecordsService'](self.db).players(season=season,kind=kind)
                actual=RecordsService(self.db).players(season=season,kind=kind)
                self.assertEqual(actual,expected)
    def test_cache_search_sort_inputs_and_returned_objects_are_isolated(self):
        api=RecordsService(self.db);cache=QueryCache(api)
        with patch.object(api,'players',wraps=api.players) as count:
            first=cache.players(season=1);first[0]['name']='modified'
            second=cache.players(season=1,name='선수',minimum=0,role=None)
            self.assertNotEqual(second[0]['name'],'modified');self.assertEqual(count.call_count,1)
    def test_cache_invalidates_external_commit_and_save_change(self):
        api=RecordsService(self.db);cache=QueryCache(api);before=cache.players()
        with closing(self.db.connect()) as c,c:c.execute("UPDATE people SET name='새 이름' WHERE id='p0'")
        self.assertNotEqual(before,cache.players())
        with tempfile.TemporaryDirectory() as folder:
            other=Path(folder)/'other.sqlite3'
            with closing(self.db.connect()) as a,closing(sqlite3.connect(other)) as b:a.backup(b)
            from idol_manager.database import Database
            api.database=Database(other);self.assertEqual(cache.revision()[0],str(other.resolve()))
    def test_slow_worker_does_not_block_ui_and_hidden_page_drops_result(self):
        from idol_manager.service import GameService
        from idol_manager.ui.main_window import MainWindow
        from PySide6.QtCore import QTimer
        from PySide6.QtTest import QTest
        w=MainWindow(GameService(self.root,self.path));self.addCleanup(w.close);w.show();w.show_records()
        page=w.records_page;beats=[];timer=QTimer(w);timer.timeout.connect(lambda:beats.append(1));timer.start(5)
        original=page.service.records.players
        def slow(**kwargs):time.sleep(.2);return original(**kwargs)
        with patch.object(page.service.records,'players',side_effect=slow):
            page.tabs.setCurrentIndex(1)
            for _ in range(10):QTest.qWait(10);time.sleep(.005)
            w.show_squads();generation=page.query_generation
            for _ in range(30):QTest.qWait(10);time.sleep(.005)
            self.assertGreater(len(beats),5);self.assertEqual(page.query_generation,generation)
            self.assertNotEqual(page.rendered_generation,generation)
        timer.stop();w.close()
    def test_hidden_photo_receivers_do_not_scan_all_players(self):
        from idol_manager.service import GameService
        from idol_manager.ui.main_window import MainWindow
        from PySide6.QtWidgets import QTableWidgetItem
        w=MainWindow(GameService(self.root,self.path));self.addCleanup(w.close);w.show();w.show_records()
        page=w.explorer_page;growth=w.development_page
        growth.rows=[dict(person_id=f'virtual-{i}',photo_path=f'virtual/{i}.png') for i in range(650)]
        growth.table.setColumnCount(1);growth.table.setRowCount(650)
        from PySide6.QtCore import Qt
        for i in range(650):
            item=QTableWidgetItem();item.setData(Qt.ItemDataRole.UserRole,f'virtual-{i}');growth.table.setItem(i,0,item)
        with patch.object(w.thumbnails,'get',return_value=w.thumbnails.placeholder) as called:
            page.refresh_photos();growth.photos();w.finance_page.photos()
            self.assertEqual(called.call_count,0)
        w.close()
    def test_preview_is_exact_subset_of_full_records(self):
        api=RecordsService(self.db);full=api.players();ids=[p['id'] for p in full[:3]]
        self.assertEqual(api.players(person_ids=ids),[p for p in full if p['id'] in ids])
        self.assertEqual(api.players(person_ids=[]),[])

if __name__=='__main__':unittest.main()
