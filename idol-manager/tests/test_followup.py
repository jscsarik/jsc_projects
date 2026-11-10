"""Follow-up: resource/user separation and RC09 reachable controls."""
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import json,os,sqlite3,tempfile,unittest
from idol_manager.storage import UserPaths,user_paths,prepare_storage,import_save,StorageError,resource_root,install_root
from idol_manager.database import Database
from idol_manager.service import GameService
from idol_manager.config import ROOT

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='idol_followup_');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.install=self.root/'읽기 전용 프로그램';self.install.mkdir();self.paths=UserPaths(self.root/'한글 사용자 데이터')
    def legacy(self):
        p=self.install/'data/idol_manager.sqlite3';Database(p);return p
    def test_localappdata_unicode_and_frozen_resources(self):
        with patch.dict(os.environ,{'LOCALAPPDATA':str(self.root/'한글 이름'),'IDOL_MANAGER_USER_DATA':''}):self.assertEqual(user_paths().root,self.root/'한글 이름/IDOL_Manager')
        with patch('sys.frozen',True,create=True),patch('sys._MEIPASS',str(self.root/'임시 번들'),create=True),patch('sys.executable',str(self.install/'IDOL.exe')):
            self.assertEqual(resource_root(),self.root/'임시 번들');self.assertEqual(install_root(),self.install)
    def test_safe_import_preserves_original_preferences_and_reopen(self):
        source=self.legacy();before=source.read_bytes();(source.parent/'bgm_settings.json').write_text('{"volume":23}',encoding='utf8')
        paths,notice=prepare_storage(self.paths,self.install)
        self.assertTrue(paths.save.exists());self.assertTrue(notice);self.assertEqual(before,source.read_bytes())
        self.assertEqual((paths.config/'bgm_settings.json').read_text(encoding='utf8'),'{"volume":23}')
        self.assertFalse(prepare_storage(self.paths,self.install)[1])
        self.assertEqual(before,source.read_bytes())
    def test_conflict_and_ambiguous_sources_never_overwrite(self):
        source=self.legacy();self.paths.ensure();Database(self.paths.save)
        before=self.paths.save.read_bytes();_,notice=prepare_storage(self.paths,self.install)
        self.assertIn('덮어쓰거나 삭제하지',notice)
        with self.assertRaises(StorageError):import_save(source,self.paths)
        self.assertEqual(before,self.paths.save.read_bytes())
        second=self.install/'saves/idol_manager.sqlite3';Database(second)
        with self.assertRaises(StorageError):prepare_storage(UserPaths(self.root/'other'),self.install)
    def test_wal_snapshot_and_failed_import_keep_source(self):
        source=self.legacy()
        with closing(sqlite3.connect(source)) as writer:
            writer.execute('PRAGMA journal_mode=WAL');writer.execute("UPDATE agencies SET funds_krw=7654321 WHERE id='ador'");writer.commit()
            import_save(source,self.paths)
        with closing(sqlite3.connect(self.paths.save)) as c:self.assertEqual(c.execute("SELECT funds_krw FROM agencies WHERE id='ador'").fetchone()[0],7654321)
        bad=self.root/'bad.sqlite3';bad.write_bytes(b'not sqlite')
        with self.assertRaises(StorageError):import_save(bad,UserPaths(self.root/'bad target'))
        self.assertFalse((self.root/'bad target/saves/idol_manager.sqlite3').exists());self.assertTrue(source.exists())
    def test_resource_folder_has_no_writes_and_user_images_are_recognized(self):
        from tests.test_annual_draft import png
        self.paths.ensure();png(self.paths.assets/'idols/사용자 사진.png',8)
        resources=self.install/'resources';resources.mkdir()
        before=list(resources.rglob('*'));s=GameService(resources,self.paths.save,storage=self.paths)
        self.assertEqual(s.scan.image_count,1);s.new_game()
        self.assertEqual(s.cache_dir,self.paths.cache);self.assertEqual(s.settings_dir,self.paths.config)
        self.assertEqual(before,list(resources.rglob('*')))
        self.assertTrue(Path(s.scan.people[0].photo_path).is_absolute())
        s2=GameService(resources,self.paths.save,storage=self.paths);self.assertEqual(s2.database.counts(),(1,1))
    def test_import_failure_does_not_publish_partial_database(self):
        source=self.legacy()
        with patch('idol_manager.storage.os.link',side_effect=OSError('injected')):
            with self.assertRaises(OSError):import_save(source,self.paths)
        self.assertFalse(self.paths.save.exists());self.assertFalse(list(self.paths.saves.glob('.import-*')));self.assertTrue(source.exists())
    def test_v16_user_copy_migrates_without_changing_original_rows(self):
        source=ROOT/'reports/release_qa/followup/user_before.sqlite3'
        if not source.exists():self.skipTest('QA 전용 기존 세이브 복사본이 없음')
        def rows(path):
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as c:
                tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
                return {t:sorted(c.execute('SELECT * FROM '+t).fetchall(),key=repr) for t in tables}
        before=rows(source);import_save(source,self.paths);db=Database(self.paths.save)
        after=rows(self.paths.save)
        self.assertTrue(all(before[t]==after[t] for t in before))
        self.assertEqual(before,rows(source));self.assertIsNotNone(db.last_backup_path)
        self.assertIsNone(Database(self.paths.save).last_backup_path)
    def test_music_reads_resources_and_user_folder_without_resource_creation(self):
        from idol_manager.bgm_catalog import scan_music
        self.paths.ensure();track=self.paths.assets/'audio/bgm/default/사용자 음악.wav';track.write_bytes(b'test')
        before=list(self.install.rglob('*'));values=scan_music(self.install,extra_folder=self.paths.assets/'audio/bgm')
        self.assertEqual(len(values['default']),1);self.assertEqual(before,list(self.install.rglob('*')))

class CompactAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def test_rc09_scroll_and_hidden_columns_all_requested_sizes(self):
        from PySide6.QtCore import QPoint,Qt
        from PySide6.QtTest import QTest
        from idol_manager.ui.main_window import MainWindow
        source=ROOT/'reports/release_qa/followup/user_before.sqlite3'
        if not source.exists():self.skipTest('QA 전용 기존 세이브 복사본이 없음')
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'qa.sqlite3'
            with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as a,closing(sqlite3.connect(target)) as b:a.backup(b)
            w=MainWindow(GameService(ROOT,target));w.show();self.addCleanup(w.close);w.show_squads()
            for width,height in ((800,700),(900,1560),(1280,720),(1920,1080),(800,700)):
                w.resize(width,height);QTest.qWait(100);p=w.squad_page;pager=w.portrait_layout.tables.get(p.table)
                widgets=[p.confirm_button,p.swap_button,p.promote_button,p.demote_button,p.first_leader_button,p.second_leader_button]
                if pager and pager.enabled:widgets.extend([pager.previous,pager.next,pager.fields,pager.details])
                for widget in widgets:
                    p.page_scroll.ensureWidgetVisible(widget);QTest.qWait(10)
                    point=widget.mapTo(p.page_scroll.viewport(),QPoint(0,0))
                    self.assertTrue(p.page_scroll.viewport().rect().contains(point),f'{width}x{height} {widget.objectName() or type(widget).__name__}')
                self.assertTrue(p.table.isColumnHidden(0))
            w.close();self.app.processEvents()

class SyntheticSupplyTests(unittest.TestCase):
    def test_qa_supply_is_contained_unique_and_repeatable(self):
        import hashlib
        from tools.followup_long_run import make_world
        from idol_manager.catalog import scan_idols
        with tempfile.TemporaryDirectory(dir=ROOT/'diagnostics',prefix='followup_supply_') as folder:
            world=make_world(Path(folder),12);people=scan_idols(world).people
            self.assertEqual(len(people),12)
            self.assertEqual(len({p.id for p in people}),12)
            self.assertEqual(len({hashlib.sha256(p.read_bytes()).digest() for p in (world/'assets/idols').iterdir()}),12)
            self.assertEqual(world,make_world(world,12))
            with self.assertRaises(ValueError):make_world(world,13)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):make_world(Path(folder),1)
        with self.assertRaises(ValueError):make_world(ROOT,1)

    def test_original_generation_and_photo_shortage_stay_in_force(self):
        from idol_manager.annual_recruitment import intake
        from tools.followup_long_run import make_world
        from tools.simulate_game import seeded_entropy
        import random
        with tempfile.TemporaryDirectory(dir=ROOT/'diagnostics',prefix='followup_intake_') as folder:
            world=make_world(Path(folder),300);s=GameService(world);s.new_game()
            with closing(s.database.connect()) as c,c,seeded_entropy(random.Random(61),random.Random(62)):
                c.execute('UPDATE game_clock SET absolute_day=189')
                self.assertEqual(intake(c,world)['status'],'completed')
                self.assertEqual(c.execute('SELECT COUNT(*) FROM annual_entries').fetchone()[0],70)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM annual_entries WHERE initial_age BETWEEN 14 AND 16').fetchone()[0],60)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM annual_entries WHERE initial_age>=17').fetchone()[0],10)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM annual_secrets').fetchone()[0],2)
                self.assertFalse(c.execute('SELECT 1 FROM idols WHERE health>90 OR health<0').fetchone())
                self.assertFalse(c.execute('SELECT 1 FROM abilities WHERE value>potential OR value<0 OR potential>100').fetchone())
                c.execute('UPDATE game_clock SET absolute_day=406')
                self.assertEqual(intake(c,world)['status'],'shortage')
                self.assertEqual(c.execute('SELECT COUNT(*) FROM annual_entries').fetchone()[0],70)

if __name__=='__main__':unittest.main()
