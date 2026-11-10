from pathlib import Path
import tempfile,unittest,zipfile
from unittest.mock import patch
from tools.publish_latest import publish,publish_release

class PublishLatestTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.releases=self.root/'releases';self.releases.mkdir()
        self.latest=self.releases/'IDOL_Manager_Latest.zip';self.latest.write_bytes(b'previous-good-release')
        self.archive=self.root/'release.zip'
        with zipfile.ZipFile(self.archive,'w') as z:
            for name,content in (('IDOL_Manager.exe',b'MZ-test'),('VERSION.txt',b'0.31.1'),('_internal/config/generation.json',b'{}'),('_internal/config/season_schedule.json',b'{}')):
                z.writestr('IDOL_Manager/'+name,content)
    def test_valid_zip_atomic_publication(self):
        result=publish(self.archive,self.releases)
        self.assertEqual(result['version'],'0.31.1')
        self.assertEqual(self.latest.read_bytes(),self.archive.read_bytes())
        self.assertEqual(list(self.releases.glob('*.tmp')),[])
    def configure_drive(self):
        import json
        (self.root/'packaging').mkdir()
        drive=self.root/'drive'/'IDOL_Manager';drive.mkdir(parents=True)
        (self.root/'packaging'/'publish_destination.json').write_text(json.dumps({'google_drive_directory':str(drive/'releases')}),encoding='utf-8')
        return drive/'releases'
    def test_build_publication_also_copies_into_drive(self):
        drive=self.configure_drive();result=publish_release(self.archive,root=self.root)
        self.assertEqual((drive/'IDOL_Manager_Latest.zip').read_bytes(),self.archive.read_bytes())
        self.assertEqual(result['sha256'],result['google_drive']['sha256'])
    def test_missing_drive_fails_without_touching_good_release(self):
        drive=self.configure_drive();drive.parent.rmdir()
        with self.assertRaises(OSError):publish_release(self.archive,root=self.root)
        self.assertEqual(self.latest.read_bytes(),b'previous-good-release')
    def test_readonly_generated_staging_can_be_removed(self):
        import os,stat
        from tools import package_friend_release as packager
        staging=self.root/'build/friend_release_test';nested=staging/'_internal/assets/audio/bgm'
        nested.mkdir(parents=True);(nested/'test.txt').write_text('generated')
        os.chmod(nested,stat.S_IREAD)
        with patch.object(packager,'ROOT',self.root):packager.remove_staging(staging)
        self.assertFalse(staging.exists())
    def test_staging_cleanup_rejects_unrelated_directory(self):
        from tools import package_friend_release as packager
        folder=self.root/'assets';folder.mkdir();(folder/'keep').write_text('original')
        with patch.object(packager,'ROOT',self.root):
            with self.assertRaises(ValueError):packager.remove_staging(folder)
        self.assertTrue((folder/'keep').is_file())
    def test_failed_copy_preserves_previous_release(self):
        def fail(source,target):
            Path(target).write_bytes(b'incomplete');raise OSError('copy interrupted')
        with patch('tools.publish_latest.shutil.copyfile',side_effect=fail):
            with self.assertRaises(OSError):publish(self.archive,self.releases)
        self.assertEqual(self.latest.read_bytes(),b'previous-good-release')
        self.assertEqual(list(self.releases.glob('*.tmp')),[])
    def test_private_save_or_broken_zip_never_replace_latest(self):
        with zipfile.ZipFile(self.archive,'a') as z:z.writestr('IDOL_Manager/data/save.sqlite3',b'private')
        with self.assertRaises(ValueError):publish(self.archive,self.releases)
        self.assertEqual(self.latest.read_bytes(),b'previous-good-release')
        self.archive.write_bytes(b'broken')
        with self.assertRaises(zipfile.BadZipFile):publish(self.archive,self.releases)
        self.assertEqual(self.latest.read_bytes(),b'previous-good-release')
