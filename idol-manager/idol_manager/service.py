from pathlib import Path
from contextlib import closing

from .catalog import scan_idols
from .config import load_settings
from .database import Database
from .draft import DraftEngine
from .draft_session import DraftSession
from .squads import SquadService
from .calendar_service import CalendarService
from .match_service import MatchService
from .special_service import SpecialService
from .finals_service import FinalsService
from .development_service import DevelopmentService
from .profile_service import ProfileService
from .finance_service import FinanceService
from .market_service import MarketService


class GameService:
    def __init__(self, root: Path, database_path: Path | None = None,*,storage=None):
        self.root = root
        self.image_root=root
        if database_path is None and storage is None:
            from .storage import resource_root,prepare_storage
            if root.resolve()==resource_root():storage,_=prepare_storage()
        if storage is not None:database_path=storage.save
        self.database = Database(database_path or root / "data" / "idol_manager.sqlite3")
        self.cache_dir=storage.cache if storage else self.database.path.parent
        self.settings_dir=storage.config if storage else self.database.path.parent
        self.user_asset_dir=storage.assets/'idols' if storage else None
        self.user_music_dir=storage.assets/'audio/bgm' if storage else None
        if storage:
            import json
            try:
                manifest=json.loads((storage.config/'legacy_import.json').read_text(encoding='utf8'))
                source=Path(manifest['source'])
                previous=Path(manifest['image_root']) if manifest.get('image_root') else source.parent.parent
                if (previous/'assets').is_dir():self.image_root=previous
            except (OSError,ValueError,KeyError):pass
        self.draft = DraftEngine(self.database)
        self.draft_session = DraftSession(self.draft)
        self.squads = SquadService(self.database)
        self.calendar = CalendarService(self.database,root=self.image_root,user_asset_dir=self.user_asset_dir)
        self.matches = MatchService(self.database)
        self.specials = SpecialService(self.database)
        self.finals = FinalsService(self.database)
        self.development = DevelopmentService(self.database)
        from .training_service import TrainingService
        self.training = TrainingService(self.database)
        self.profiles = ProfileService(self.database)
        from .records_service import RecordsService
        self.records = RecordsService(self.database)
        self.finance = FinanceService(self.database)
        self.market = MarketService(self.database)
        from .trainee_recruitment import RecruitmentService
        from .founding import FoundingService
        self.recruitment=RecruitmentService(self.database);self.founding=FoundingService(self.database)
        from .ai_trades import AITradeService
        self.ai_trades=AITradeService(self.database)
        from .awards import AwardsService
        self.awards= AwardsService(self.database)
        from .annual_draft import AnnualDraftService
        self.annual_draft=AnnualDraftService(self.database,self.image_root,self.market,user_asset_dir=self.user_asset_dir)
        self.scan = scan_idols(self.image_root,self.user_asset_dir)
        if self.database.has_game():
            from .annual_recruitment import scan_assets
            with closing(self.database.connect()) as c,c:scan_assets(c,self.image_root,self.user_asset_dir)
        self.database.register(self.scan.people)
        self.calendar.initialize()

    def new_game(self):
        scan = scan_idols(self.image_root,self.user_asset_dir)
        self.database.create_game(scan.people, load_settings())
        self.scan = scan
        from .annual_recruitment import scan_assets
        with closing(self.database.connect()) as c,c:scan_assets(c,self.image_root,self.user_asset_dir)
        self.calendar.initialize()

    def agencies(self):
        return self.database.agencies()

    def agency_roster(self, agency_id: str):
        return self.database.agency_roster(agency_id)

    def initial_draft_candidates(self):
        return self.database.initial_draft_candidates()
