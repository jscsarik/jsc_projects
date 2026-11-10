from contextlib import closing
from pathlib import Path
import tempfile,unittest
from idol_manager.database import Database
from idol_manager.special_service import SpecialService
from idol_manager.profile_service import ProfileService
from tests import test_special_service as fixture


class SpecialProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.SpecialServiceTests.setUpClass.__func__(cls)
    def test_real_special_judgments_and_second_team_excluded_from_growth(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'profile.sqlite3';fixture.fixture.copy_db(self.template,path)
            db=Database(path);special=SpecialService(db,seed_factory=lambda:1827)
            event=special.events()[0]['id'];special.start(event)
            for stage in ('upper','lower','final'):special.play(next(r['id'] for r in special.state(event)['rounds'] if r['stage']==stage))
            with closing(db.connect()) as c:
                people=[r[0] for r in c.execute('SELECT DISTINCT person_id FROM special_player_stats')];before=list(c.iterdump())
            profiles=ProfileService(db)
            for person in people:
                data=profiles.get(person);records=[r for r in data['matches'] if r['kind']=='special']
                self.assertTrue(records)
                with closing(db.connect()) as c:
                    count=c.execute("SELECT COUNT(*) FROM special_judgments WHERE person_id=? AND phase IN ('main','support')",(person,)).fetchone()[0]
                self.assertEqual(sum(e['attempts'] for r in records for e in r['judgments'] if e['phase'] in ('main','support')),count)
                for r in records:
                    if not r['growth_eligible']:
                        self.assertEqual(sum(e['growth_attempts'] for e in profiles.statistics([r])['abilities']),0)
            with closing(db.connect()) as c:self.assertEqual(before,list(c.iterdump()))
