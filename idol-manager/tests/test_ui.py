from contextlib import closing
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QImageReader
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from idol_manager.catalog import scan_idols
from idol_manager.config import ROOT
from idol_manager.service import GameService
from idol_manager.ui.main_window import MainWindow
from idol_manager.ui.thumbnails import ThumbnailCache


class UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="idol_ui_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "한글 경로"
        self.photos = self.root / "assets" / "idols"
        self.photos.mkdir(parents=True)

    def image(self, name, color="pink"):
        path = self.photos / name
        image = QImage(120, 160, QImage.Format.Format_RGB32)
        image.fill(QColor(color))
        self.assertTrue(image.save(str(path)))
        return path

    def wait_until(self, predicate, timeout=10000):
        start = time.monotonic()
        while not predicate() and (time.monotonic() - start) * 1000 < timeout:
            QTest.qWait(10)
            time.sleep(.005)
        self.assertTrue(predicate(), "비동기 작업 시간 초과")

    def test_new_game_button_search_sort_reopen_and_no_private_data(self):
        for name in ("가원.png", "나연.jpg", "아이돌.webp"):
            self.image(name)
        window = MainWindow(GameService(self.root))
        self.addCleanup(window.close)
        window.show()
        self.assertEqual(window.model.rowCount(), 0)
        QTest.mouseClick(window.new_button, Qt.MouseButton.LeftButton)
        self.wait_until(lambda: window.job is None)
        self.assertEqual(window.model.rowCount(), 3)
        self.assertEqual(window.model.columnCount(), 4)
        self.assertEqual(window.model.HEADERS, ("사진", "이름", "가상 나이", "상태"))
        window.search.setText("나연")
        self.assertEqual(window.proxy.rowCount(), 1)
        self.assertEqual(window.proxy.index(0, 1).data(), "나연")
        window.search.setText("없는 이름")
        self.assertEqual(window.proxy.rowCount(), 0)
        self.assertIn("검색 결과", window.empty.text())
        window.search.clear()
        window.table.sortByColumn(1, Qt.SortOrder.DescendingOrder)
        names = [window.proxy.index(i, 1).data() for i in range(3)]
        self.assertEqual(names, sorted(names, reverse=True))
        window.table.sortByColumn(2, Qt.SortOrder.AscendingOrder)
        ages = [window.proxy.index(i, 2).data() for i in range(3)]
        self.assertEqual(ages, sorted(ages))
        for column in range(4):
            for role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.UserRole):
                self.assertIsNone(window.model.index(0, column).data(role))
        self.assertEqual(window.model.rows, GameService(self.root).database.public_roster())
        self.wait_until(lambda: len(window.thumbnails.pending) == 0)

    def test_thumbnail_unicode_formats_cache_invalidation_missing_and_corrupt(self):
        cache = ThumbnailCache(self.root, self.root / "cache")
        self.addCleanup(cache.close)
        for name in ("한글.png", "한글.jpg", "한글.jpeg", "한글.webp"):
            path = self.image(name)
            relative = path.relative_to(self.root).as_posix()
            cache.get(relative)
            self.wait_until(lambda: not cache.pending)
            self.assertFalse(cache.get(relative).isNull())
        self.assertEqual(len(list((self.root / "cache").glob("*.png"))), 4)
        target = next((self.root / "cache").glob("*.png"))
        modified = target.stat().st_mtime_ns
        cache.memory.clear()
        for path in self.photos.iterdir():
            cache.get(path.relative_to(self.root).as_posix())
        self.wait_until(lambda: not cache.pending)
        self.assertEqual(target.stat().st_mtime_ns, modified)
        cache.get("assets/idols/없는 사진.png")
        corrupt = self.photos / "손상.png"
        corrupt.write_bytes(b"corrupted")
        cache.get(corrupt.relative_to(self.root).as_posix())
        self.wait_until(lambda: not cache.pending)
        previous = len(list((self.root / "cache").glob("*.png")))
        self.image("한글.png", "blue")
        cache.get("assets/idols/한글.png")
        self.wait_until(lambda: not cache.pending)
        self.assertEqual(len(list((self.root / "cache").glob("*.png"))), previous + 1)

    def test_application_entrypoint_restart_across_processes(self):
        self.image("재실행 확인.png")
        service = GameService(self.root)
        service.new_game()
        with closing(service.database.connect()) as connection:
            before = [tuple(row) for row in connection.execute("SELECT * FROM abilities ORDER BY skill")]
        script = """
import sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
import idol_manager.app as app
import os
os.environ['IDOL_MANAGER_USER_DATA']=str(Path(sys.argv[1])/'user_data')
app.ROOT = Path(sys.argv[1])
original_show = app.MainWindow.show
def show_and_quit(window):
    original_show(window)
    assert window.model.rowCount() == 1
    QTimer.singleShot(200, QApplication.instance().quit)
app.MainWindow.show = show_and_quit
from tests.start_menu_fixtures import enter_legacy_game
enter_legacy_game(app)
raise SystemExit(app.run())
"""
        for _ in range(2):
            result = subprocess.run([sys.executable, "-c", script, str(self.root)], cwd=ROOT,
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        with closing(service.database.connect()) as connection:
            self.assertEqual(before, [tuple(row) for row in connection.execute("SELECT * FROM abilities ORDER BY skill")])

    def test_agency_selector_roster_labels_search_and_blind_candidates(self):
        for number in range(8):
            self.image(f"가상 인물{number}.png")
        service = GameService(self.root)
        service.new_game()
        candidates = service.initial_draft_candidates()
        with closing(service.database.connect()) as connection, connection:
            for person, status in zip(candidates[:3], ("first_team", "second_team", "trainee")):
                connection.execute("UPDATE roster_memberships SET agency_id='ador',career_status=? WHERE person_id=?", (status, person.id))
            connection.execute("UPDATE roster_memberships SET agency_id='sm',career_status='first_team' WHERE person_id=?", (candidates[3].id,))
        window = MainWindow(service)
        self.addCleanup(window.close)
        window.show()
        self.assertEqual(window.roster_selector.count(), 11)
        self.assertEqual(window.model.rowCount(), 4)
        window.roster_selector.setCurrentIndex(window.roster_selector.findData("ador"))
        self.assertEqual(window.model.rowCount(), 3)
        self.assertIn("1,000,000,000원", window.summary.text())
        self.assertEqual({window.model.index(i, 3).data() for i in range(3)}, {"1군", "2군", "연습생"})
        window.search.setText(candidates[0].name)
        self.assertEqual(window.proxy.rowCount(), 1)
        window.search.clear()
        window.roster_selector.setCurrentIndex(window.roster_selector.findData("sm"))
        self.assertEqual([person.id for person in window.model.rows], [candidates[3].id])
        window.roster_selector.setCurrentIndex(window.roster_selector.findData("yg"))
        self.assertEqual(window.model.rowCount(), 0)
        self.assertIn("등록된 선수가 없습니다", window.empty.text())
        window.roster_selector.setCurrentIndex(0)
        self.assertEqual(window.model.rowCount(), 4)
        self.assertEqual(window.model.columnCount(), 4)
        for person in window.model.rows:
            self.assertEqual(person.status, "candidate")
            self.assertEqual(set(vars(person)), {"id", "name", "photo_path", "age", "status"})
        for column in range(4):
            for role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.UserRole,
                         Qt.ItemDataRole.AccessibleTextRole, Qt.ItemDataRole.WhatsThisRole):
                self.assertIsNone(window.model.index(0, column).data(role))
        window.reload()
        self.assertEqual(window.roster_selector.currentIndex(), 0)
        self.wait_until(lambda: not window.thumbnails.pending)

    def test_real_photos_decode_and_real_roster_window(self):
        scan = scan_idols(ROOT)
        for person in scan.people:
            reader = QImageReader(str(ROOT / person.photo_path))
            reader.setAutoTransform(True)
            reader.setScaledSize(reader.size().scaled(44, 52, Qt.AspectRatioMode.KeepAspectRatio))
            self.assertFalse(reader.read().isNull(), person.photo_path)
        service = GameService(ROOT, self.root / "data" / "game.sqlite3")
        service.new_game()
        window = MainWindow(service)
        self.addCleanup(window.close)
        window.show()
        QTest.qWait(300)
        self.assertEqual(window.model.rowCount(), 200)
        self.assertEqual(service.database.counts(), (len(scan.people), 200))
        window.search.setText(window.model.rows[0].name)
        self.assertGreaterEqual(window.proxy.rowCount(), 1)
        window.search.clear()
        self.wait_until(lambda: not window.thumbnails.pending)
        screenshot = ROOT / ".test-artifacts" / "roster.png"
        screenshot.parent.mkdir(exist_ok=True)
        self.assertTrue(window.grab().save(str(screenshot)))
        with closing(service.database.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM abilities").fetchone()[0], len(scan.people) * 8)


if __name__ == "__main__":
    unittest.main()
