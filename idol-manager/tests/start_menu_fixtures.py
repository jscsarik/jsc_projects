"""Explicit title/import/selection for older entrypoint regression scenarios."""
def enter_legacy_game(app):
    from idol_manager.start_controller import StartController
    show=StartController.show
    def title_then_game(controller):
        controller.exit_decision=lambda:'save'
        show(controller)
        if not controller.paths.slot(1).save.exists():
            controller.manager.import_legacy(app.ROOT/'data/idol_manager.sqlite3',1)
        controller.open_game(1)
    StartController.show=title_then_game
