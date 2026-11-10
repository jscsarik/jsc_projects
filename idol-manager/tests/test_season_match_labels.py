"""Fixed saved results only: seasonal rows and main/support presentation."""
from contextlib import closing
from collections import Counter
from pathlib import Path
from unittest.mock import patch
import unittest
from PySide6.QtTest import QTest
from idol_manager.service import GameService
from idol_manager.match_types import Judgment,MatchResult,MatchFixture,MatchSelection
from idol_manager.match_replay import replay_frames
from idol_manager.ui.main_window import MainWindow
from idol_manager.ui.match_page import MatchPage
from idol_manager.ui.thumbnails import ThumbnailCache
from tests import test_records as fixture


class SeasonLabelsTests(unittest.TestCase):
    setUpClass=classmethod(fixture.RecordsTests.setUpClass.__func__)
    dump=fixture.RecordsTests.dump
    def setUp(self):fixture.RecordsTests.setUp(self)
    def test_season_rows_and_weighted_career_separate_phases(self):
        before=self.dump();rows=self.api.player_seasons('p0');self.assertEqual(len(rows),3)
        self.assertEqual([(r['main_successes'],r['support_successes']) for r in rows],[(30,24),(270,108),(300,132)])
        self.assertEqual(rows[-1]['appearances'],10);self.assertAlmostEqual(rows[-1]['rate'],.72)
        self.assertEqual(rows[-1]['leader_successes'],10);self.assertEqual(rows[-1]['deathmatch_successes'],50)
        self.assertEqual(self.dump(),before)
    def test_transfer_season_subtotal_not_added_to_career_twice(self):
        with closing(self.db.connect()) as c,c:
            c.execute("UPDATE match_player_stats SET agency_id=? WHERE match_id='fixed-2-0'",(self.a,))
            c.execute("UPDATE match_events SET agency_id=? WHERE match_id='fixed-2-0'",(self.a,))
        rows=self.api.player_seasons('p0');sub=next(r for r in rows if r['row_type']=='subtotal')
        self.assertEqual(sub['appearances'],9);self.assertEqual(sub['main_successes'],270)
        self.assertEqual(rows[-1]['appearances'],10);self.assertEqual(rows[-1]['successes'],432)
    def test_legacy_missing_phase_does_not_guess_split(self):
        with closing(self.db.connect()) as c,c:c.execute('DELETE FROM match_events WHERE match_id=?',(self.first,))
        rows=self.api.player_seasons('p0');self.assertIsNone(rows[0]['main_successes']);self.assertIsNone(rows[0]['support_successes'])
        self.assertEqual(rows[0]['successes'],54);self.assertIsNone(rows[-1]['main_successes'])
    def test_profile_season_table_and_private_candidate(self):
        service=GameService(self.root,self.path);before=self.dump();w=MainWindow(service);self.addCleanup(w.close);w.show();QTest.qWait(90);w.profiles.open('p0')
        d=w.profiles.dialog;panel=d.panels[0];panel.tabs.setCurrentIndex(3);QTest.qWait(100)
        t=panel.season_history_table;self.assertEqual(t.rowCount(),3);self.assertIn('통산',t.item(2,0).text())
        self.assertTrue(panel.tabs.isVisible());self.assertTrue(t.isVisible());self.assertGreater(t.height(),30)
        self.assertEqual(t.horizontalHeaderItem(3).text(),'주요 능력치 성공');self.assertEqual(t.item(2,3).data(0),300);self.assertEqual(t.item(2,4).data(0),132)
        d.grab().save(str(Path(__file__).resolve().parents[1]/'.test-artifacts/profile_seasons_windows.png'))
        d.close();w.profiles.open('p2');self.assertEqual(w.profiles.dialog.panels[0].season_history_table.rowCount(),0);w.profiles.dialog.close()
        self.assertEqual(before,self.dump())
    def test_live_and_skip_use_identical_saved_phase_counts(self):
        service=GameService(self.root,self.path);before=self.dump()
        with closing(self.db.connect()) as c:
            players=tuple(dict(r) for r in c.execute('SELECT * FROM match_player_stats WHERE match_id=?',(self.first,)))
            teams=tuple(dict(r) for r in c.execute('SELECT * FROM match_team_stats WHERE match_id=?',(self.first,)))
            events=tuple(Judgment(**{k:r[k] for k in ('sequence','agency_id','person_id','phase','skill','tick','round_number','attempt','probability','roll','success')}) for r in c.execute('SELECT * FROM match_events WHERE match_id=? ORDER BY sequence',(self.first,)))
        result=MatchResult(self.first,'normal',self.a,self.b,teams,players,events)
        photos=ThumbnailCache(self.root,Path(self.temp.name)/'photos');self.addCleanup(photos.close)
        fixture_row=MatchFixture(self.first,1,1,2,1,'고정 콘텐츠',('vocal','dance'),1,'completed',((self.a,'A'),(self.b,'B')),None,None,'')
        snapshots=[]
        with patch.object(MatchPage,'reload'),patch.object(service.matches,'result_names',return_value={'p0':'고정 선수'}),patch.object(service.matches,'play',side_effect=AssertionError('No simulation')):
            for skip in (True,False):
                page=MatchPage(service,photos);self.addCleanup(page.shutdown);self.addCleanup(page.close)
                page.selection=MatchSelection(fixture_row,(),0,());page.current_result=result;page.names={'p0':'고정 선수'}
                page.frames=replay_frames(result);page.frame_index=0;page.live_counts=Counter();page.live_scores=Counter();page.judgments_shown=0;page.replaying=True
                page._configure_battle(result)
                if skip:page.skip()
                else:
                    while page.replaying:page.advance_frame()
                snapshots.append(dict(page.live_counts))
                self.assertEqual(page.records_table.item(0,5).data(0),30);self.assertEqual(page.records_table.item(0,6).data(0),24)
                self.assertIn('주요 능력치 성공 30회',page.battle.cards['p0'].score.text());self.assertIn('일반 능력치 성공 24회',page.battle.cards['p0'].score.text())
        self.assertEqual(snapshots[0],snapshots[1]);self.assertEqual(before,self.dump())
