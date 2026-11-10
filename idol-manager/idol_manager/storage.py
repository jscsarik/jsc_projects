"""Read-only install resources and per-user data, with non-destructive import."""
from dataclasses import dataclass
from contextlib import closing
from pathlib import Path
import json,os,sqlite3,sys,tempfile,shutil

class StorageError(ValueError):pass

def resource_root():
    if getattr(sys,'frozen',False):return Path(getattr(sys,'_MEIPASS',Path(sys.executable).parent)).resolve()
    return Path(__file__).resolve().parents[1]

def install_root():
    return Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else resource_root()

@dataclass(frozen=True)
class UserPaths:
    root:Path
    @property
    def saves(self):return self.root/'saves'
    @property
    def save(self):return self.saves/'idol_manager.sqlite3'
    @property
    def config(self):return self.root/'config'
    @property
    def logs(self):return self.root/'logs'
    @property
    def cache(self):return self.root/'cache'
    @property
    def assets(self):return self.root/'user_assets'
    def ensure(self):
        for path in (self.saves,self.config,self.logs,self.cache,self.assets/'idols',self.assets/'audio/bgm/default',self.assets/'audio/bgm/battle',self.assets/'audio/bgm/title'):path.mkdir(parents=True,exist_ok=True)

    def slot(self,slot_id):
        if type(slot_id) is not int or slot_id not in (1,2):raise StorageError('슬롯은 1 또는 2만 사용할 수 있습니다.')
        return SlotPaths(self.root,self.saves/f'slot{slot_id}',slot_id)


@dataclass(frozen=True)
class SlotPaths(UserPaths):
    directory:Path
    slot_id:int
    @property
    def saves(self):return self.directory
    @property
    def save(self):return self.directory/'game.sqlite3'
    @property
    def config(self):return self.directory/'config'
    @property
    def cache(self):return self.root/'cache'/f'slot{self.slot_id}'
    def ensure(self):
        super().ensure()

def user_paths():
    override=os.environ.get('IDOL_MANAGER_USER_DATA')
    if override:return UserPaths(Path(override).expanduser().resolve())
    base=Path(os.environ['LOCALAPPDATA']) if os.environ.get('LOCALAPPDATA') else Path.home()/'AppData/Local'
    return UserPaths((base/'IDOL_Manager').resolve())

def validate_save(path):
    try:
        with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as c:
            if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or c.execute('PRAGMA foreign_key_check').fetchone():raise StorageError('저장 파일 무결성 검사에 실패했습니다.')
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='game' AND type='table'").fetchone():raise StorageError('IDOL Manager 저장 파일이 아닙니다.')
    except sqlite3.Error as e:raise StorageError('저장 파일을 읽을 수 없습니다: '+str(path)) from e

def import_save(source,paths):
    """Snapshot the source (including WAL), validate, then publish exclusively.

    No source deletion and no replacement of an existing destination. Staging
    occurs on the destination volume; a hard link publishes a completed copy
    atomically and fails if another app already created the destination.
    """
    source=Path(source).resolve();paths.ensure()
    if source==paths.save.resolve():raise StorageError('현재 사용자 저장 파일을 자기 자신으로 가져올 수 없습니다.')
    if paths.save.exists():raise StorageError('새 저장 위치에 세이브가 있습니다. 기존 파일을 덮어쓰지 않습니다: '+str(paths.save))
    validate_save(source)
    handle,name=tempfile.mkstemp(prefix='.import-',suffix='.sqlite3',dir=paths.saves);os.close(handle);staging=Path(name)
    try:
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(staging)) as dst:src.backup(dst)
        validate_save(staging)
        try:os.link(staging,paths.save)
        except FileExistsError as e:raise StorageError('다른 실행에서 세이브가 생성되었습니다. 가져오기를 중단하고 두 파일을 보존합니다.') from e
        manifest=dict(source=str(source),destination=str(paths.save),policy='SQLite backup; validated; exclusive publication; original retained')
        (paths.config/'legacy_import.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
        for name in ('bgm_settings.json','ui_layout.ini'):
            previous=source.parent/name;destination=paths.config/name
            if previous.is_file():
                try:
                    with destination.open('xb') as dst,previous.open('rb') as src:shutil.copyfileobj(src,dst)
                except FileExistsError:pass  # Existing user preferences win.
        return manifest
    finally:staging.unlink(missing_ok=True)

def prepare_storage(paths=None,legacy_root=None):
    paths=paths or user_paths();paths.ensure();legacy_root=Path(legacy_root or install_root())
    sources=[p for p in (legacy_root/'data/idol_manager.sqlite3',legacy_root/'saves/idol_manager.sqlite3') if p.is_file() and p.resolve()!=paths.save.resolve()]
    message=''
    if paths.save.exists():
        validate_save(paths.save)
        if sources and not (paths.config/'legacy_import.json').exists():
            message='새 사용자 저장 위치의 기존 게임을 사용합니다. 프로젝트의 이전 세이브는 덮어쓰거나 삭제하지 않습니다.\n저장 위치: '+str(paths.save)+'\n이전 파일: '+', '.join(map(str,sources))
        return paths,message
    if len(sources)>1:raise StorageError('이전 저장 파일이 여러 개입니다. 원본을 보존했습니다. 가져올 파일 하나를 명시해 주세요: '+', '.join(map(str,sources)))
    if sources:
        import_save(sources[0],paths)
        message='기존 세이브를 검증하여 새 사용자 저장 위치에 복사했습니다. 이전 원본은 그대로 보존했습니다.\n'+str(paths.save)
    return paths,message
