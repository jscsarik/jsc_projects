"""One 70-person intake and one full 30-turn draft, reused via DB copies."""
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import os,json,random,sqlite3,tempfile,unittest,zlib,struct,hashlib
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from idol_manager.service import GameService
from idol_manager.database import Database
from idol_manager.annual_draft import AnnualDraftService,AnnualDraftError
from idol_manager.annual_recruitment import scan_assets,intake
from idol_manager.market_service import active_contract,_close
from idol_manager.development_service import settle_birthday
from idol_manager.config import SKILLS
from tests.game_fixtures import complete_initial_setup

def png(path,n):
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    path.parent.mkdir(parents=True,exist_ok=True);rgb=bytes((n%256,(n//256)%256,(n//65536)%256))
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',4,4,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+rgb*4)*4))+chunk(b'IEND',b''))

def copy_db(source,target):
    with closing(sqlite3.connect(Path(source).as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(target)) as dst:src.backup(dst)

class AnnualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.folder=tempfile.TemporaryDirectory(prefix='idol_annual21_');cls.addClassCleanup(cls.folder.cleanup)
        cls.root=Path(cls.folder.name)
        for n in range(310):png(cls.root/'assets/idols'/f'아이돌 {n:03}.png',n)
        cls.base=cls.root/'annual_base.sqlite3';s=GameService(cls.root,cls.base);s.new_game();complete_initial_setup(s.database)
        cls.ranks=[a.id for a in s.agencies()]
        with closing(s.database.connect()) as c,c:
            c.execute('UPDATE game_clock SET absolute_day=189');runtime=c.execute('SELECT * FROM development_runtime').fetchone()
            settle_birthday(c,189,runtime,json.loads(runtime['rules_json']))
            cls.visible_before=[tuple(r) for r in c.execute('SELECT i.* FROM idols i JOIN initial_draft_candidates d ON d.person_id=i.person_id ORDER BY i.person_id')]
            cls.skills_before=[tuple(r) for r in c.execute('SELECT a.* FROM abilities a JOIN initial_draft_candidates d ON d.person_id=a.person_id ORDER BY a.person_id,a.skill')]
            cls.founding=[tuple(r) for r in c.execute('SELECT * FROM draft_picks ORDER BY pick_number')]
            c.execute("INSERT INTO season_finals(season,status,frozen_json,standings_json,final_order_json,champion_id) VALUES (1,'completed','{}','[]',?,?)",(json.dumps(cls.ranks),cls.ranks[-1]))
        cls.before=cls.root/'before_intake.sqlite3';copy_db(cls.base,cls.before)
        s.annual_draft.rescan()  # The only 70-person generation in this suite.

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='idol_annual_case_');self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'game.sqlite3';copy_db(self.base,self.path)
        self.service=GameService(self.root,self.path);self.db=self.service.database;self.api=self.service.annual_draft
        self.service.market.seed_factory=lambda:0
    def rows(self,sql,args=()):
        with closing(self.db.connect()) as c:return [tuple(r) for r in c.execute(sql,args)]
    def dump(self):
        with closing(self.db.connect()) as c:return list(c.iterdump())
    def day(self,n):
        with closing(self.db.connect()) as c,c:c.execute('UPDATE game_clock SET absolute_day=?',(n,))
    def start(self):self.day(196);self.api.start();return self.api.state()
    def minors(self,state):return [p for p in state['candidates'] if p['age']<17]
    def free(self,agency):
        with closing(self.db.connect()) as c,c:
            p=c.execute("SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='second_team' LIMIT 1",(agency,)).fetchone()[0]
            c.execute('DELETE FROM squad_leaders WHERE person_id=?',(p,));_close(c,active_contract(c,p),196)
            c.execute("UPDATE roster_memberships SET agency_id=NULL,career_status='fa' WHERE person_id=?",(p,))
            return p

    def test_01_exactly_seventy_and_one_event_reopen_no_regeneration(self):
        before=self.dump();self.api.rescan();self.api.rescan();self.api.state()
        self.assertEqual(self.rows('SELECT COUNT(*) FROM annual_entries'),[(70,)]);self.assertEqual(self.rows("SELECT status FROM annual_intakes"),[('completed',)])
        self.assertEqual(before,self.dump())
    def test_02_sixty_youth_ten_adults_existing_adult_range(self):
        self.assertEqual(self.rows('SELECT SUM(initial_age BETWEEN 14 AND 16),SUM(initial_age>=17),MAX(initial_age) FROM annual_entries')[0][:2],(60,10))
        self.assertLessEqual(self.rows('SELECT MAX(initial_age) FROM annual_entries')[0][0],26)
    def test_03_two_hidden_specials_under_twenty_one(self):
        self.assertEqual(self.rows('SELECT COUNT(*) FROM annual_secrets'),[(2,)])
        self.assertFalse(self.rows('SELECT 1 FROM annual_secrets s JOIN idols i ON i.person_id=s.person_id WHERE i.age>21'))
        for p in self.api.state()['candidates']:
            self.assertFalse(any(key in p for key in ('potential','potentials','pa','special','archetype')))
    def test_04_no_previous_identity_or_copied_photo_reuse_and_names_can_match(self):
        self.assertFalse(self.rows('SELECT 1 FROM annual_entries a JOIN initial_draft_candidates d ON d.person_id=a.person_id'))
        self.assertEqual(self.rows('SELECT COUNT(DISTINCT person_id) FROM annual_entries'),[(70,)])
        # Distinct bytes with a duplicate display name use another persistent UUID.
        original=self.root/'assets/idols/아이돌 000.png';path=self.root/'assets/idols/동명이인/아이돌 000.png';png(path,999)
        clone=self.root/'assets/idols/복사본.png';clone.write_bytes(original.read_bytes())
        with closing(self.db.connect()) as c,c:
            scan_assets(c,self.root)
            old=c.execute('SELECT person_id FROM annual_assets WHERE photo_path=?',('assets/idols/아이돌 000.png',)).fetchone()[0]
            new=c.execute('SELECT person_id FROM annual_assets WHERE photo_path=?',('assets/idols/동명이인/아이돌 000.png',)).fetchone()[0]
            copied=c.execute('SELECT person_id FROM annual_assets WHERE photo_path=?',('assets/idols/복사본.png',)).fetchone()[0]
            self.assertNotEqual(old,new);self.assertEqual(old,copied)
        count=self.rows('SELECT COUNT(*) FROM people');GameService(self.root,self.path)
        self.assertEqual(count,self.rows('SELECT COUNT(*) FROM people'))
    def test_05_health_cap_no_existing_birthday_or_ca_regeneration(self):
        self.assertFalse(self.rows('SELECT 1 FROM idols i JOIN annual_entries a ON a.person_id=i.person_id WHERE health>90 OR health<0'))
        self.assertEqual(self.visible_before,self.rows('SELECT i.* FROM idols i JOIN initial_draft_candidates d ON d.person_id=i.person_id ORDER BY i.person_id'))
        self.assertEqual(self.skills_before,self.rows('SELECT a.* FROM abilities a JOIN initial_draft_candidates d ON d.person_id=a.person_id ORDER BY a.person_id,a.skill'))
        self.assertEqual(self.rows("SELECT COUNT(*) FROM development_settlements WHERE kind='birthday'"),[(1,)])
    def test_06_five_integer_ranges_match_profile_and_current_value(self):
        state=self.api.state();new=set(p[0] for p in self.rows('SELECT person_id FROM annual_entries'))
        with closing(self.db.connect()) as c:
            for p in state['candidates']:
                if p['id'] not in new:continue
                self.assertFalse(p['exact']);profile=self.service.profiles.get(p['id']);self.assertEqual(tuple(map(tuple,p['ranges'])),profile['bounds'])
                actual=dict(c.execute('SELECT skill,value FROM abilities WHERE person_id=?',(p['id'],)))
                for skill,(low,high) in zip(SKILLS,p['ranges']):self.assertEqual(high-low,4);self.assertTrue(low<=actual[skill]<=high)
        before=self.rows('SELECT * FROM draft_estimates ORDER BY person_id,skill');self.api.state();self.assertEqual(before,self.rows('SELECT * FROM draft_estimates ORDER BY person_id,skill'))
    def test_07_reverse_regular_rank_snake_not_champion(self):
        state=self.start();expected=list(reversed(self.ranks))+self.ranks+list(reversed(self.ranks))
        self.assertEqual([r['agency_id'] for r in state['turns']],expected)
        self.assertTrue(all(r['person_id'] is None for r in state['turns']));self.assertEqual(len(state['turns']),30)
    def test_08_turn_reuse_duplicate_person_and_market_bypass_blocked(self):
        state=self.start();turn=state['turn'];p=self.minors(state)[0]
        self.api.pick(turn['agency_id'],p['id'],expected_pick=1)
        with self.assertRaises(ValueError):self.api.pick(turn['agency_id'],self.minors(self.api.state())[0]['id'],expected_pick=1)
        next_=self.api.state()['turn']
        with self.assertRaises(ValueError):self.api.pick(next_['agency_id'],p['id'],expected_pick=2)
        with self.assertRaises(ValueError):self.service.market.connect_draft_pick(next_['agency_id'],p['id'],1,pick_id='bypass')
        self.assertEqual(self.rows('SELECT COUNT(*) FROM annual_turns WHERE person_id IS NOT NULL'),[(1,)])
    def test_09_one_full_thirty_turns_trainee_and_professional_contracts(self):
        self.day(196);order=list(reversed(self.ranks));old_fa=[self.free(a) for a in order[:3]];self.api.start()
        first_adult=None;failed=None
        for number in range(1,31):
            state=self.api.state();t=state['turn'];self.assertEqual(t['pick_number'],number)
            if number in (1,3):p=next(p for p in state['candidates'] if p['new'] and p['age']>=17)
            elif number==2:p=next(p for p in state['candidates'] if p['id']==old_fa[1])
            else:p=self.minors(state)[0]
            self.api.pick(t['agency_id'],p['id'],expected_pick=number)
            if number in (1,2):
                if number==1:
                    first_adult=p['id'];restored=AnnualDraftService(Database(self.path),self.root,self.service.market)
                    self.assertEqual(restored.state()['turn']['person_id'],p['id']);self.assertTrue(restored.person(p['id'])['exact'])
                self.api.offer(t['agency_id'],66000000,1,expected_pick=number,request_id=f'success:{number}')
            elif number==3:
                failed=p['id']
                for i,amount in enumerate((10000,20000,30000)):
                    self.api.offer(t['agency_id'],amount,1,expected_pick=number,request_id=f'failed:{i}')
        end=self.api.state();self.assertEqual(end['session']['status'],'completed');self.assertIsNone(end['turn'])
        self.assertEqual(self.rows('SELECT COUNT(DISTINCT person_id) FROM annual_turns'),[(30,)])
        self.assertTrue(all(r[0]==3 for r in self.rows('SELECT COUNT(*) FROM annual_turns GROUP BY agency_id')))
        self.assertEqual(self.rows("SELECT COUNT(*),MIN(annual_krw),MAX(annual_krw) FROM finance_contracts WHERE kind='draft_trainee'"),[(27,10000000,10000000)])
        self.assertEqual(self.rows('SELECT debut_season FROM market_careers WHERE person_id=?',(first_adult,)),[(2,)])
        self.assertEqual(self.rows('SELECT debut_season FROM market_careers WHERE person_id=?',(old_fa[1],)),[(1,)])
        self.assertEqual(self.rows('SELECT career_status,agency_id FROM roster_memberships WHERE person_id=?',(failed,)),[('fa',None)])
        self.assertTrue(self.api.person(failed)['exact']);self.assertNotIn(failed,[p['id'] for p in end['candidates']])
        self.assertEqual(self.founding,self.rows('SELECT * FROM draft_picks ORDER BY pick_number'))
        # Next-phase shared FA and youth free-contract services work unchanged.
        self.day(203);self.service.market.bid(order[2],failed,30000000,1,request_id='after-draft-bid')
        youth=self.minors(self.api.state())[0]
        self.service.market.sign_trainee(order[2],youth['id'],request_id='after-draft-youth')
        self.assertEqual(self.rows('SELECT career_status FROM roster_memberships WHERE person_id=?',(youth['id'],)),[('unassigned',)])
        from idol_manager.trainee_recruitment import finalize
        with self.service.market.write() as c:finalize(c,203,policy=lambda candidates,rng:())
        self.assertEqual(self.rows('SELECT COUNT(*) FROM market_bids'),[(1,)])
        self.assertEqual(self.rows('SELECT career_status FROM roster_memberships WHERE person_id=?',(youth['id'],)),[('trainee',)])
    def test_10_adult_pick_needs_pro_and_second_team_vacancy(self):
        state=self.start();t=state['turn'];p=next(p for p in state['candidates'] if p['new'] and p['age']>=17)
        before=self.dump()
        with self.assertRaises(ValueError):self.api.pick(t['agency_id'],p['id'],expected_pick=1)
        self.assertEqual(before,self.dump())
    def test_11_failed_negotiation_preserves_ca_and_current_publication(self):
        self.day(196);agency=self.ranks[-1];self.free(agency);self.api.start();p=next(p for p in self.api.state()['candidates'] if p['new'] and p['age']>=17)
        before=self.rows('SELECT * FROM abilities WHERE person_id=? ORDER BY skill',(p['id'],));self.api.pick(agency,p['id'],expected_pick=1)
        for i,amount in enumerate((10000,20000,30000)):self.api.offer(agency,amount,1,expected_pick=1,request_id=f'reject:{i}')
        self.assertEqual(before,self.rows('SELECT * FROM abilities WHERE person_id=? ORDER BY skill',(p['id'],)))
        self.assertTrue(self.service.profiles.get(p['id'])['exact']);self.assertEqual(self.rows('SELECT status FROM annual_turns WHERE pick_number=1'),[('failed',)])
        self.assertEqual(self.rows('SELECT consumed FROM market_draft_rights WHERE person_id=?',(p['id'],)),[(1,)])
    def test_12_ai_public_only_and_financial_pause_keeps_pick(self):
        self.start();original=self.db.connect;forbidden=[]
        new_ids={r[0] for r in self.rows('SELECT person_id FROM annual_entries')}
        def connect():
            c=original()
            c.set_authorizer(lambda action,table,column,*_:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_READ and (table=='annual_secrets' or column in ('potential','archetype')) else sqlite3.SQLITE_OK)
            c.set_trace_callback(lambda q:forbidden.append(q) if 'SELECT skill,value FROM abilities' in q and any(p in q for p in new_ids) else None)
            return c
        with patch.object(self.db,'connect',side_effect=connect):self.assertTrue(self.api.ai_step())
        self.assertFalse(forbidden)
        state=self.api.state();agency=state['turn']['agency_id']
        with closing(self.db.connect()) as c,c:c.execute('UPDATE agencies SET funds_krw=0 WHERE id=?',(agency,))
        before=self.rows('SELECT * FROM annual_turns ORDER BY pick_number')
        with self.assertRaises(AnnualDraftError):self.api.ai_step()
        self.assertEqual(before,self.rows('SELECT * FROM annual_turns ORDER BY pick_number'))
        pick_number=state['turn']['pick_number']
        with closing(self.db.connect()) as c,c:c.execute('UPDATE agencies SET funds_krw=1000000000 WHERE id=?',(agency,))
        self.assertTrue(self.api.ai_step())
        self.assertEqual(self.rows('SELECT status FROM annual_turns WHERE pick_number=?',(pick_number,)),[('signed',)])
    def test_13_market_phase_guard_and_week_three_gate(self):
        self.start();self.day(202);before=self.dump()
        with self.assertRaises(ValueError):self.service.calendar.advance_day(expected_absolute_day=202)
        self.assertEqual(before,self.dump());self.day(203)
        with self.assertRaises(ValueError):self.service.market.sign_trainee(self.ranks[0],self.minors(self.api.state())[0]['id'],request_id='early-market')
    def test_14_intake_shortage_is_atomic_and_blocks_week_two(self):
        copy_db(self.before,self.path);self.db=Database(self.path);self.api=AnnualDraftService(self.db,self.root,self.service.market)
        with closing(self.db.connect()) as c,c:c.execute("UPDATE idols SET status='candidate' WHERE status='unseen'")
        state=self.api.rescan();self.assertEqual(state['status'],'shortage');self.assertIn('부족',state['issue'])
        self.assertEqual(self.rows('SELECT COUNT(*) FROM annual_entries'),[(0,)])
        self.day(195)
        with self.assertRaises(ValueError):self.service.calendar.advance_day(expected_absolute_day=195)
        self.assertEqual(self.rows('SELECT absolute_day FROM game_clock'),[(195,)])
    def test_15_reopen_immutability_founding_and_database_integrity(self):
        state=self.start();before=self.dump();self.api.start();restored=AnnualDraftService(Database(self.path),self.root,self.service.market)
        self.assertEqual(restored.state()['turns'],state['turns']);self.assertEqual(before,self.dump())
        self.assertEqual(self.founding,self.rows('SELECT * FROM draft_picks ORDER BY pick_number'))
        self.assertEqual(self.rows('PRAGMA integrity_check'),[('ok',)]);self.assertFalse(self.rows('PRAGMA foreign_key_check'))
