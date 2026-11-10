"""Opt-in packaged title/slot QA; requires an explicit disposable-profile marker."""
from pathlib import Path
import json,sys,traceback
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from .save_slots import atomic_json


def attach(controller,paths):
    marker=paths.root/'start-menu-qa.json'
    options=json.loads(marker.read_text(encoding='utf8')) if marker.is_file() else {}
    if options.get('qa_only') is not True:raise ValueError('--self-check에는 임시 QA 사용자 폴더의 start-menu-qa.json 승인이 필요합니다.')
    controller.exit_decision=lambda:'save'
    result=dict(success=False,frozen=bool(getattr(sys,'frozen',False)),executable=sys.executable,
        resource_root=str(controller.root),user_root=str(paths.root),steps=[])
    timer=QTimer(controller);timer.setInterval(80)
    def steps():
        yield 'title_visible'
        initial=controller.manager.scan();result['initial']=initial
        if options.get('expect_empty'):
            assert all(s['state']=='empty' for s in initial)
            assert not paths.slot(1).save.exists() and not paths.slot(2).save.exists()
        controller.title.grab().save(str(paths.logs/'title_empty.png'))
        if options.get('create'):
            assert all(s['state']=='empty' for s in initial)
            controller.manager.create(1);controller.title.reload();controller.open_game(1)
            assert controller.active==1
            service=controller.game.service;service.draft_session.select_agency('ador');service.draft.start()
            for number,p in enumerate(service.draft.available_candidates()[:160],1):
                service.draft.pick(service.draft.state().next_turn.agency_id,p.id,expected_pick_number=number)
            assert service.calendar.state().date.absolute_day==-7
            controller.poll_save();controller.return_to_menu();assert controller.game is None
            yield 'slot1_draft_saved'
            controller.manager.create(2);controller.open_game(2)
            service=controller.game.service;service.draft_session.select_agency('jyp');service.draft.start()
            turn=service.draft.state().next_turn
            service.draft.pick(turn.agency_id,service.draft.available_candidates()[0].id,expected_pick_number=1)
            controller.return_to_menu();assert controller.game is None
            yield 'slot2_separate_saved'
        if options.get('import_source'):
            controller.manager.import_legacy(Path(options['import_source']),options.get('import_slot',1),approved=bool(options.get('replace')))
            controller.title.reload();yield 'legacy_imported'
        if any(s['state']=='ready' for s in controller.manager.scan()):
            controller.title.reload();recent=controller.manager.latest(controller.title.slots)
            controller.continue_game();assert controller.active==recent
            result['continued_slot']=recent
            result['continued_agency']=controller.game.service.draft_session.player_agency()
            controller.game.grab().save(str(paths.logs/'active_game.png'))
            yield 'continue_open'
            controller.return_to_menu();assert controller.game is None
            yield 'returned_to_title'
        controller.title.reload();controller.title.grab().save(str(paths.logs/'start_screen.png'))
        controller.title.select_mode('load');controller.title.select(2)
        yield 'slot_selection'
        controller.title.grab().save(str(paths.logs/'slot_selection.png'))
        result['final']=controller.manager.scan()
        result['thumbnail_sizes']=[]
        from PySide6.QtGui import QImage
        for identity in (1,2):
            image=QImage(str(paths.slot(identity).directory/'thumbnail.png'))
            if not image.isNull():result['thumbnail_sizes'].append([image.width(),image.height()])
        assert all(size==[400,225] for size in result['thumbnail_sizes'])
        result['success']=True
    flow=steps()
    def tick():
        try:
            value=next(flow)
            if value:result['steps'].append(value)
        except StopIteration:
            timer.stop();atomic_json(paths.logs/'start-menu-check.json',result)
            controller.title.close();QApplication.instance().exit(0)
        except Exception:
            timer.stop();result['error']=traceback.format_exc()
            atomic_json(paths.logs/'start-menu-check.json',result)
            if controller.game:
                controller.game.before_close=None;controller.return_to_menu()
            controller.title.close();QApplication.instance().exit(2)
    timer.timeout.connect(tick);timer.start()
