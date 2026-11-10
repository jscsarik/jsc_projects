"""Complete initial setup through real APIs, in temporary test databases only."""
import random
from idol_manager.draft import DraftEngine
from idol_manager.draft_session import DraftSession
from idol_manager.squads import SquadService


def complete_initial_setup(database):
    # Keep fixture values within the current health rule. Tests that require
    # zero injury probability must control their injury policy explicitly.
    from contextlib import closing
    with closing(database.connect()) as c,c:
        c.execute('UPDATE idols SET health=90')
    legacy_save(database)
    engine = DraftEngine(database)
    DraftSession(engine).select_agency('ador')
    engine.start(rng=random.Random(17))
    identities = [p.id for p in engine.available_candidates()[:160]]
    for number,identity in enumerate(identities,1):
        engine.pick(engine.state().next_turn.agency_id,identity,expected_pick_number=number)
    squads = SquadService(database)
    squads.confirm_initial(tuple(m.id for m in squads.snapshot().members[:5]))
    for squad in ('first_team','second_team'):
        state = squads.snapshot()
        identity = next(m.id for m in state.members if m.squad==squad)
        squads.set_leader(squad,identity,expected_revision=state.revision)


def legacy_save(database,*,schedule=False):
    """Explicit pre-v18 fixture, to retain existing-save regression coverage."""
    from contextlib import closing
    with closing(database.connect()) as c,c:
        c.execute('DELETE FROM founding_setup')
    from idol_manager.calendar_service import CalendarService
    if schedule:CalendarService(database).initialize()


def confirm_day(window):
    """Approve the new explicit Monday closure dialog in existing GUI scenarios."""
    from unittest.mock import patch
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QMessageBox
    with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):
        QTest.mouseClick(window.day_button,Qt.MouseButton.LeftButton)
