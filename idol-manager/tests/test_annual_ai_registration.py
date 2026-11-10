"""Legacy debut metadata must not turn a professional FA back into a trainee."""
import unittest
from contextlib import closing
from unittest.mock import patch
from tests import test_season32 as fixture

class AnnualAIRegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.Season32Tests.setUpClass.__func__(cls)
    setUp=fixture.Season32Tests.setUp
    day=fixture.Season32Tests.day;rows=fixture.Season32Tests.rows

    def prepare(self):
        self.day(203)
        person=self.rows("SELECT person_id FROM roster_memberships WHERE agency_id='ador' AND career_status='second_team' LIMIT 1")[0][0]
        self.service.market.release('ador',person,'immediate',request_id='regression:fa')
        with closing(self.db.connect()) as c,c:c.execute('UPDATE market_careers SET debut_season=NULL WHERE person_id=?',(person,))
        self.assertTrue(self.rows('SELECT 1 FROM professional_history WHERE person_id=?',(person,)))
        state=fixture.Season32Tests.prepare_annual(self)
        self.assertNotEqual(state['turn']['agency_id'],'ador')
        self.assertIn(person,{p['id'] for p in state['candidates']})
        return person,state

    def test_full_ai_excludes_professional_fa_and_selects_legal_trainee(self):
        person,state=self.prepare();seen=[]
        def decide(candidates,*args,**kwargs):
            seen.extend(p['id'] for p in candidates);self.assertNotIn(person,seen)
            return candidates[0],{}
        with patch('idol_manager.recruitment_policy.decide',side_effect=decide):self.assertTrue(self.service.annual_draft.ai_step())
        row=self.rows('SELECT registration,person_id FROM annual_turns WHERE season=1 AND pick_number=?',(state['turn']['pick_number'],))[0]
        self.assertTrue(seen);self.assertEqual(row[0],'trainee');self.assertNotEqual(row[1],person)

    def test_open_slot_development_ai_registers_professional_fa_as_pro(self):
        person,state=self.prepare();agency=state['turn']['agency_id'];self.day(203)
        outgoing=self.rows("SELECT person_id FROM roster_memberships WHERE agency_id=? AND career_status='second_team' LIMIT 1",(agency,))[0][0]
        self.service.market.release(agency,outgoing,'immediate',request_id='regression:room');self.day(210)
        with closing(self.db.connect()) as c,c:c.execute('UPDATE idols SET age=18 WHERE person_id=?',(person,))
        from idol_manager.recruitment_philosophy import ensure
        def development(c):
            result=ensure(c);result[agency]['philosophy']='development';return result
        def decide(candidates,*args,**kwargs):return next(p for p in candidates if p['id']==person),{}
        with patch('idol_manager.recruitment_policy.decide',side_effect=decide),patch('idol_manager.recruitment_philosophy.ensure',side_effect=development):self.service.annual_draft.ai_step()
        self.assertEqual(self.rows('SELECT registration,person_id FROM annual_turns WHERE season=1 AND pick_number=?',(state['turn']['pick_number'],))[0],('pro',person))
