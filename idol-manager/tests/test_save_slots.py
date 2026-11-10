"""Independent slots and crash-safe publication, using disposable user folders."""
from contextlib import closing
from pathlib import Path
import hashlib,json,os,shutil,sqlite3,tempfile,time,unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtGui import QImage,QColor
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from idol_manager.storage import UserPaths,StorageError
from idol_manager.save_slots import SlotManager,atomic_json,read_json
from idol_manager.save_preview import inspect_save,render_thumbnail
from idol_manager.service import GameService
from idol_manager.start_controller import StartController


def digest(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as c:
        h=hashlib.sha256()
        for line in c.iterdump():h.update(line.encode('utf8'))
        return h.hexdigest()


def copy_db(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True)) as c,closing(sqlite3.connect(target)) as d:c.backup(d)


class SlotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.folder=tempfile.TemporaryDirectory(prefix='idol_start_template_');cls.addClassCleanup(cls.folder.cleanup)
        cls.resources=Path(cls.folder.name)/'게임 리소스';photos=cls.resources/'assets/idols';photos.mkdir(parents=True)
        image=QImage(80,120,QImage.Format.Format_RGB32)
        for n in range(310):image.fill(QColor.fromHsv(n%360,100,210));image.save(str(photos/f'가상 아이돌 {n:03}.png'))
        cls.base=UserPaths(Path(cls.folder.name)/'template');manager=SlotManager(cls.base,cls.resources);manager.create(1)
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='idol_start_한글_');self.addCleanup(self.temp.cleanup)
        self.paths=UserPaths(Path(self.temp.name)/'사용자 데이터');self.manager=SlotManager(self.paths,self.resources)
    def seed(self,identity=1):
        shutil.copytree(self.base.slot(1).directory,self.paths.slot(identity).directory)
        # A new identity for independent, copied synthetic fixtures.
        atomic_json(self.paths.slot(identity).directory/'identity.json',{'save_id':f'test-{identity}-{time.monotonic_ns()}'})
        self.manager.refresh(identity,saved=True)
        return self.paths.slot(identity)
    def test_empty_title_scan_creates_no_game_database(self):
        self.assertEqual([s['state'] for s in self.manager.scan()],['empty','empty'])
        self.assertEqual(list(self.paths.root.rglob('*.sqlite3')),[])
        self.assertIsNone(self.manager.latest(self.manager.scan()))
    def test_only_two_ids_and_no_third_slot(self):
        for bad in (0,3,-1,True,'1'):
            with self.assertRaises(StorageError):self.manager.create(bad)
        self.assertFalse((self.paths.saves/'slot3').exists())
    def test_two_new_games_isolated_abilities_draft_and_agency(self):
        self.manager.create(1);self.manager.create(2)
        services=[GameService(self.resources,self.paths.slot(i).save,storage=self.paths.slot(i)) for i in (1,2)]
        services[0].draft_session.select_agency('ador');services[1].draft_session.select_agency('jyp')
        protected=digest(services[1].database.path)
        services[0].draft.start();turn=services[0].draft.state().next_turn
        services[0].draft.pick(turn.agency_id,services[0].draft.available_candidates()[0].id,expected_pick_number=1)
        self.assertEqual(protected,digest(services[1].database.path))
        self.assertEqual(services[1].draft.state().picks_made,0)
        self.assertEqual(services[0].draft_session.player_agency(),'ador');self.assertEqual(services[1].draft_session.player_agency(),'jyp')
        self.assertNotEqual(digest(services[0].database.path),digest(services[1].database.path))
        protected_first=digest(services[0].database.path)
        services[1].draft.start();turn=services[1].draft.state().next_turn
        services[1].draft.pick(turn.agency_id,services[1].draft.available_candidates()[0].id,expected_pick_number=1)
        self.assertEqual(protected_first,digest(services[0].database.path))
    def test_overwrite_requires_approval_and_keeps_backup(self):
        slot=self.seed();before=digest(slot.save)
        with self.assertRaises(StorageError):self.manager.create(1)
        self.assertEqual(before,digest(slot.save));self.manager.create(1,approved=True)
        backups=list((self.paths.saves/'slot_backups/slot1').glob('*.sqlite3'));self.assertEqual(len(backups),1)
        self.assertEqual(before,digest(backups[0]));self.assertTrue(list((self.paths.saves/'.archives').glob('slot1-*')))
    def test_new_game_failure_retains_old_db_and_other_slot(self):
        a=self.seed();b=self.seed(2);before=[digest(a.save),digest(b.save)]
        with patch.object(GameService,'new_game',side_effect=RuntimeError('injected creation failure')):
            with self.assertRaises(RuntimeError):self.manager.create(1,approved=True)
        self.assertEqual(before,[digest(a.save),digest(b.save)])
        self.assertFalse(list(self.paths.saves.glob('.staging-*')))
    def test_publish_failure_restores_old_folder(self):
        slot=self.seed();before=digest(slot.save);rename=Path.rename
        def fail(path,target):
            if path.name.startswith('.staging-slot'):raise OSError('injected rename failure')
            return rename(path,target)
        with patch.object(Path,'rename',fail):
            with self.assertRaises(OSError):self.manager.create(1,approved=True)
        self.assertEqual(before,digest(slot.save))
    def test_crash_between_renames_restores_old_save(self):
        slot=self.seed();before=digest(slot.save)
        archive=self.paths.saves/'.archives/slot1-interrupted';archive.parent.mkdir();slot.directory.rename(archive)
        stage=self.paths.saves/'.staging-slot1-interrupted';stage.mkdir();copy_db(self.base.slot(1).save,stage/'game.sqlite3')
        atomic_json(self.manager._journal(1),dict(archive=str(archive),stage=str(stage)))
        self.assertEqual(self.manager.scan()[0]['state'],'ready');self.assertEqual(before,digest(slot.save))
    def test_forged_recovery_cannot_move_other_slot(self):
        slot=self.seed(2);before=digest(slot.save)
        atomic_json(self.manager._journal(1),dict(archive=str(slot.directory),stage=None))
        self.assertEqual(self.manager.scan()[0]['state'],'error');self.assertEqual(before,digest(slot.save))
    def test_delete_cancel_and_approved_protect_other_slot(self):
        a=self.seed();b=self.seed(2);before=digest(b.save)
        with self.assertRaises(StorageError):self.manager.delete(1)
        self.assertTrue(a.save.exists());self.manager.delete(1,approved=True)
        self.assertFalse(a.directory.exists());self.assertEqual(before,digest(b.save))
        self.assertEqual(self.manager.scan()[0]['state'],'empty')
    def test_active_slot_cannot_delete_replace_import_or_duplicate_open(self):
        slot=self.seed();self.seed(2)
        with self.manager.lease(1,active=True):
            for fn in (lambda:self.manager.delete(1,approved=True),lambda:self.manager.create(1,approved=True),lambda:self.manager.import_legacy(self.base.slot(1).save,1,approved=True),lambda:self.manager.lease(1,active=True),lambda:self.manager.lease(2,active=True)):
                with self.assertRaises(StorageError):fn()
        self.assertTrue(slot.save.exists())
    def test_metadata_corrupt_or_stale_rebuilt_from_db(self):
        slot=self.seed();before=digest(slot.save)
        (slot.directory/'meta.json').write_text('{bad',encoding='utf8')
        self.assertEqual(self.manager.scan()[0]['state'],'ready')
        meta=read_json(slot.directory/'meta.json');meta.update(season=999,agency_name='incorrect',last_played_at=[])
        atomic_json(slot.directory/'meta.json',meta)
        actual=self.manager.scan()[0]['meta'];self.assertEqual(actual['season'],1);self.assertNotEqual(actual['agency_name'],'incorrect')
        self.assertEqual(before,digest(slot.save))
    def test_missing_thumbnail_rebuild_and_render_failure_not_save_failure(self):
        slot=self.seed();thumb=slot.directory/'thumbnail.png';thumb.unlink();before=digest(slot.save)
        self.manager.scan();self.assertTrue(thumb.exists());self.assertEqual(before,digest(slot.save))
        thumb.unlink()
        with patch('idol_manager.save_slots.render_thumbnail',side_effect=OSError('disk full')):self.manager.save_active(1,playtime=2)
        self.assertEqual(before,digest(slot.save));self.assertEqual(self.manager.scan()[0]['state'],'ready')
    def test_metadata_write_error_does_not_turn_valid_db_into_corruption(self):
        slot=self.seed();before=digest(slot.save)
        with patch('idol_manager.save_slots.atomic_json',side_effect=OSError('metadata denied')):
            self.assertEqual(self.manager.scan()[0]['state'],'ready');self.manager.save_active(1,playtime=7)
        self.assertEqual(before,digest(slot.save))
    def test_thumbnail_not_rerendered_without_visual_changes(self):
        self.seed()
        with patch('idol_manager.save_slots.render_thumbnail') as render:self.manager.refresh(1,saved=True);render.assert_not_called()
    def test_latest_played_distinct_from_saved_and_corrupt_latest_not_fallback(self):
        self.seed();slot=self.seed(2)
        self.manager.refresh(1,played=True);self.manager.refresh(2,saved=True)
        self.assertEqual(self.manager.latest(self.manager.scan()),1)
        self.manager.refresh(2,played=True);slot.save.write_bytes(b'broken database')
        state=self.manager.scan();self.assertEqual(state[1]['state'],'error');self.assertEqual(self.manager.latest(state),2)
        self.assertEqual(slot.save.read_bytes(),b'broken database')
    def test_import_wal_consistent_and_source_retained(self):
        source=Path(self.temp.name)/'legacy.sqlite3';copy_db(self.base.slot(1).save,source)
        with closing(sqlite3.connect(source)) as c:
            c.execute('PRAGMA journal_mode=WAL');c.execute('PRAGMA wal_autocheckpoint=0');c.execute('UPDATE idols SET health=42');c.commit()
            self.assertTrue(Path(str(source)+'-wal').exists());before=digest(source)
            self.manager.import_legacy(source,1)
            self.assertEqual(before,digest(source));self.assertEqual(before,digest(self.paths.slot(1).save))
    def test_import_failure_or_occupied_does_not_remove_source(self):
        slot=self.seed();before=digest(slot.save)
        with self.assertRaises(StorageError):self.manager.import_legacy(self.base.slot(1).save,1)
        with patch('idol_manager.save_slots.os.replace',side_effect=OSError('injected publication failure')):
            with self.assertRaises(OSError):self.manager.import_legacy(self.base.slot(1).save,1,approved=True)
        self.assertEqual(before,digest(slot.save));self.assertTrue(self.base.slot(1).save.exists())
    def test_multiple_legacy_sources_not_automatically_imported(self):
        copy_db(self.base.slot(1).save,self.paths.save)
        install=Path(self.temp.name)/'old install';copy_db(self.base.slot(1).save,install/'data/idol_manager.sqlite3')
        manager=SlotManager(self.paths,self.resources,legacy_root=install)
        self.assertEqual(len(manager.legacy_sources()),2);self.assertEqual([s['state'] for s in manager.scan()],['empty','empty'])
        self.assertTrue(self.paths.save.exists());self.assertFalse(self.paths.slot(1).save.exists())
    def test_selected_slot_only_migrated(self):
        from tests.migration_fixtures import drop_founding
        from idol_manager.database import Database
        a=self.seed();b=self.seed(2)
        for slot in (a,b):
            with closing(sqlite3.connect(slot.save)) as c:drop_founding(c);c.execute('PRAGMA user_version=17');c.commit()
        self.manager.scan()
        with closing(sqlite3.connect(a.save)) as c:self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],17)
        Database(a.save)
        with closing(sqlite3.connect(b.save)) as c:self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],17)
        self.assertTrue(list((a.directory/'backups').glob('*.sqlite3')))
    def test_thumbnail_primary_leader_then_ca_and_secondary_no_duplicates(self):
        slot=self.seed()
        with closing(sqlite3.connect(slot.save)) as c:
            c.execute("INSERT INTO player_settings(game_id,agency_id) VALUES (1,'ador')")
            ids=[r[0] for r in c.execute('SELECT person_id FROM idols ORDER BY person_id LIMIT 3')]
            for person in ids:c.execute("UPDATE roster_memberships SET agency_id='ador',career_status='first_team' WHERE person_id=?",(person,))
            c.execute('INSERT INTO squad_leaders VALUES (?,?,?)',('ador','first_team',ids[2]));c.commit()
        info=inspect_save(slot.save);self.assertEqual(info['representatives'][0]['id'],ids[2]);self.assertEqual(len({p['id'] for p in info['representatives']}),2)
    def test_thumbnail_no_players_one_player_photos_missing_and_phases(self):
        slot=self.seed();info=inspect_save(slot.save)
        for phase in ('founding','regular','postseason','offseason'):
            info['phase']=phase;render_thumbnail(info,self.resources,slot.directory/'thumbnail.png')
            image=QImage(str(slot.directory/'thumbnail.png'));self.assertEqual((image.width(),image.height()),(400,225))
        info['representatives']=[dict(id='x',name='한 명',photo_path='missing.png')]
        render_thumbnail(info,self.resources,slot.directory/'thumbnail.png');self.assertFalse(QImage(str(slot.directory/'thumbnail.png')).isNull())
    def test_killed_writer_sqlite_rollback_and_stale_lock_selected_only(self):
        import subprocess,sys
        a=self.seed();b=self.seed(2);before=[digest(a.save),digest(b.save)]
        code="""import os,sys,sqlite3
from pathlib import Path
from idol_manager.storage import UserPaths
from idol_manager.save_slots import SlotManager
m=SlotManager(UserPaths(Path(sys.argv[1])),Path(sys.argv[2]));lease=m.lease(1,active=True)
c=sqlite3.connect(m.slot(1).save);c.execute('BEGIN IMMEDIATE');c.execute('UPDATE idols SET health=1');c.execute('PRAGMA cache_size=5');c.execute('UPDATE abilities SET value=0');os._exit(17)
"""
        result=subprocess.run([sys.executable,'-c',code,str(self.paths.root),str(self.resources)],capture_output=True,timeout=15)
        self.assertEqual(result.returncode,17,result.stderr)
        with self.manager.lease(1,active=True):self.manager.prepare_open(1)
        self.assertEqual(before,[digest(a.save),digest(b.save)])

    def test_preview_no_pa_or_secret_reads(self):
        slot=self.seed();from idol_manager.save_preview import readonly
        def connect(path):
            c=readonly(path);c.set_authorizer(lambda a,t,col,*_:sqlite3.SQLITE_DENY if a==sqlite3.SQLITE_READ and (col in ('potential','archetype') or t=='annual_secrets') else sqlite3.SQLITE_OK);return c
        with patch('idol_manager.save_preview.readonly',side_effect=connect):inspect_save(slot.save)


class StartMenuTests(SlotTests):
    # The inherited safety suite also runs with a controller-owned window.
    def controller(self):
        c=StartController(self.paths,self.resources);c.exit_decision=lambda:'save';self.addCleanup(self.cleanup_controller,c);c.show();self.app.processEvents();return c
    def cleanup_controller(self,c):
        deadline=time.monotonic()+20
        while c.job and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
        if c.game:
            c.game.before_close=None;c.game.returning_to_menu=True;c.game.close()
        c.title.close();c.bgm.shutdown();c.pool.waitForDone();self.app.processEvents()
    def test_title_zero_one_two_slots_and_no_db_creation(self):
        c=self.controller();self.assertFalse(c.title.continue_button.isEnabled());self.assertFalse(self.paths.slot(1).save.exists())
        self.seed();c.title.reload();self.assertTrue(c.title.continue_button.isEnabled())
        self.seed(2);c.title.reload();self.assertEqual(sum(s['state']=='ready' for s in c.title.slots),2)
    def test_select_continue_return_and_switch_fresh_services(self):
        self.seed();self.seed(2);c=self.controller();c.open_game(1);first=c.game.service
        self.assertEqual(c.active,1);c.return_to_menu();self.assertIsNone(c.active);self.assertTrue(c.title.isVisible())
        c.open_game(2);self.assertEqual(c.active,2);self.assertIsNot(first,c.game.service)
        self.assertEqual(c.game.service.database.path,self.paths.slot(2).save)
        c.return_to_menu();c.continue_game();self.assertEqual(c.active,2)
    def test_new_game_and_delete_cancel_two_confirmations_preserve(self):
        slot=self.seed();c=self.controller();before=digest(slot.save)
        with patch('idol_manager.ui.start_menu.confirm_action',side_effect=[True,False]):c.new_game(1)
        self.assertIsNone(c.job);self.assertEqual(before,digest(slot.save))
        with patch('idol_manager.ui.start_menu.confirm_action',return_value=False):c.delete_game(1)
        self.assertEqual(before,digest(slot.save))
    def test_normal_save_failure_keeps_game_open_then_retry(self):
        self.seed();c=self.controller();c.open_game(1)
        with patch.object(c.manager,'save_active',side_effect=sqlite3.OperationalError('injected')),patch.object(QMessageBox,'warning',return_value=QMessageBox.StandardButton.Cancel):c.return_to_menu()
        self.assertIsNotNone(c.game);self.assertTrue(c.game.isVisible());self.assertEqual(c.active,1)
        c.return_to_menu();self.assertIsNone(c.game)
    def test_auto_save_metadata_tracks_commit_on_active_slot_only(self):
        a=self.seed();b=self.seed(2);c=self.controller();c.open_game(1);other=(b.directory/'meta.json').read_bytes()
        with closing(c.game.service.database.connect()) as db,db:db.execute('UPDATE idols SET health=43')
        c.poll_save();self.assertIsNotNone(read_json(a.directory/'meta.json')['last_saved_at']);self.assertEqual(other,(b.directory/'meta.json').read_bytes())
    def test_main_menu_does_not_run_inplace_new_game(self):
        slot=self.seed();c=self.controller();c.open_game(1);before=digest(slot.save)
        QTest.mouseClick(c.game.new_button,Qt.MouseButton.LeftButton)
        self.assertIsNone(c.game);self.assertEqual(before,digest(slot.save))
    def test_gui_new_game_worker_and_slot_selection(self):
        c=self.controller();c.title.new_button.click();self.assertEqual(c.title.mode,'new');c.title.cards[1].heading.click();c.title.chosen.click()
        deadline=time.monotonic()+15
        while c.job and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
        self.assertIsNone(c.job);self.assertEqual(c.active,2);self.assertFalse(self.paths.slot(1).save.exists())
    def test_real_delete_dialog_cancel_leaves_save_unchanged(self):
        from PySide6.QtCore import QTimer
        slot=self.seed();c=self.controller();before=digest(slot.save);seen=[]
        def cancel():
            dialog=QApplication.activeModalWidget()
            if isinstance(dialog,QMessageBox):
                labels=[b.text() for b in dialog.buttons()];seen.extend(labels)
                next(b for b in dialog.buttons() if b.text()=='취소').click()
            else:QTimer.singleShot(10,cancel)
        QTimer.singleShot(0,cancel);c.delete_game(1)
        self.assertIn('삭제 확인',seen);self.assertEqual(before,digest(slot.save))

    def test_title_screenshots_and_layout_900_portrait(self):
        self.seed();self.seed(2);c=self.controller();c.title.resize(900,1400);QTest.qWait(100)
        for card in c.title.cards:
            self.assertTrue(c.title.centralWidget().rect().contains(card.geometry()));self.assertTrue(card.rect().contains(card.remove.geometry().topLeft()))
        if os.environ.get('IDOL_START_CAPTURE'):
            out=Path(__file__).resolve().parents[1]/'reports/start_menu';c.title.grab().save(str(out/'start_screen.png'))
            c.title.select_mode('load');c.title.cards[1].heading.click();c.title.grab().save(str(out/'slot_selection.png'))

if __name__=='__main__':unittest.main()
