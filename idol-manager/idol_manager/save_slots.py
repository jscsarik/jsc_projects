"""Two isolated saves, explicit import, exclusive leases and recoverable replacement."""
from contextlib import closing,contextmanager
from datetime import datetime,timezone
from pathlib import Path
import json,logging,os,shutil,sqlite3,tempfile,uuid
from PySide6.QtCore import QLockFile
from .storage import UserPaths,SlotPaths,StorageError
from .save_preview import readonly,inspect_save,preview_signature,render_thumbnail

logger=logging.getLogger(__name__)


def now():return datetime.now(timezone.utc).isoformat()

def valid_time(value):
    try:
        datetime.fromisoformat(value)
        return value
    except (TypeError,ValueError):return None


def read_json(path):
    try:
        value=json.loads(Path(path).read_text(encoding='utf8'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    descriptor,name=tempfile.mkstemp(prefix='.'+path.name+'-',dir=path.parent)
    try:
        with os.fdopen(descriptor,'w',encoding='utf8') as out:
            json.dump(value,out,ensure_ascii=False,indent=2);out.flush();os.fsync(out.fileno())
        os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)


class Lease:
    def __init__(self,*paths):
        self.locks=[]
        try:
            for path in paths:
                lock=QLockFile(str(path))
                if not lock.tryLock(0):raise StorageError('이 슬롯 또는 다른 게임이 실행·저장 중입니다. 먼저 기존 게임을 종료해 주세요.')
                self.locks.append(lock)
        except Exception:self.close();raise
    def close(self):
        for lock in reversed(self.locks):lock.unlock()
        self.locks=[]
    def __enter__(self):return self
    def __exit__(self,*_):self.close()


class SlotManager:
    def __init__(self,paths,resource_root,*,legacy_root=None):
        self.paths=paths;self.root=Path(resource_root);self.legacy_root=Path(legacy_root or resource_root)
        paths.ensure()
    def slot(self,identity):return self.paths.slot(identity)
    def lock_path(self,identity):self.slot(identity);return self.paths.saves/f'.slot{identity}.lock'
    def lease(self,identity,*,active=False):
        paths=([self.paths.saves/'.active-game.lock'] if active else [])+[self.lock_path(identity)]
        return Lease(*paths)
    def _journal(self,identity):return self.paths.saves/f'.slot{identity}.transaction.json'
    def _safe_child(self,path):
        p=Path(path)
        if not p.resolve().is_relative_to(self.paths.saves.resolve()) or p.is_symlink():raise StorageError('저장 폴더 밖의 경로는 변경하지 않습니다.')
        return p
    def _recover(self,identity):
        journal=self._journal(identity);data=read_json(journal)
        if journal.exists() and not data:raise StorageError('슬롯 복구 기록을 읽을 수 없습니다. 원본과 백업을 보존했습니다.')
        if not data:return
        destination=self.slot(identity).directory
        archive=self._safe_child(data['archive'])
        stage=self._safe_child(data['stage']) if data.get('stage') else None
        if archive.parent!=self.paths.saves/'.archives' or not archive.name.startswith(f'slot{identity}-'):
            raise StorageError('다른 슬롯을 가리키는 복구 기록은 적용하지 않습니다.')
        if stage and (stage.parent!=self.paths.saves or not stage.name.startswith(f'.staging-slot{identity}-')):
            raise StorageError('슬롯 임시 경로가 일치하지 않습니다.')
        if not destination.exists() and archive.exists():
            # A crash between the two renames restores the old complete save.
            archive.rename(destination)
        elif not destination.exists() and stage and stage.exists():
            # An empty-slot publish interrupted before rename is safe to finish.
            inspect_save(stage/'game.sqlite3');stage.rename(destination)
        journal.unlink()
    def recover(self,identity):
        with self.lease(identity):self._recover(identity)
    def prepare_open(self,identity):
        """Caller holds the active lease. Let SQLite recover only this save."""
        self._recover(identity)
        path=self.slot(identity).save
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=rw',uri=True,timeout=3)) as c:
            c.execute('SELECT COUNT(*) FROM sqlite_master').fetchone()
        return inspect_save(path)
    def legacy_sources(self):
        choices=[self.paths.save,self.legacy_root/'data/idol_manager.sqlite3',self.legacy_root/'saves/idol_manager.sqlite3']
        return tuple(dict.fromkeys(p.resolve() for p in choices if p.is_file() and p.resolve() not in [self.slot(i).save.resolve() for i in (1,2)]))
    def image_root(self,slot):
        manifest=read_json(slot.config/'legacy_import.json')
        if manifest.get('image_root'):return Path(manifest['image_root'])
        return self.root
    def _identity(self,slot):
        path=slot.directory/'identity.json';data=read_json(path)
        if not isinstance(data.get('save_id'),str):
            data={'save_id':uuid.uuid4().hex};atomic_json(path,data)
        return data['save_id']
    def refresh(self,identity,*,saved=False,played=False,playtime=None,check=True):
        slot=self.slot(identity);info=inspect_save(slot.save,check=check)
        old=read_json(slot.directory/'meta.json')
        try:save_id=self._identity(slot)
        except OSError:
            logger.warning('Slot identity cache unavailable',exc_info=True)
            save_id=old.get('save_id') or f'unconfirmed-slot-{identity}'
        registry=read_json(self.paths.config/'slot_activity.json')
        activity=registry.get(save_id,{})
        if not isinstance(activity,dict):activity={}
        if played:activity['last_played_at']=now()
        if saved:activity['last_saved_at']=now()
        if playtime is not None:activity['playtime_seconds']=max(0,int(playtime))
        if saved or played or playtime is not None:
            # Separate activity records survive a corrupt/missing display cache.
            registry[save_id]=activity
            try:
                with Lease(self.paths.saves/'.activity.lock'):
                    latest=read_json(self.paths.config/'slot_activity.json');latest[save_id]=activity
                    atomic_json(self.paths.config/'slot_activity.json',latest)
            except (OSError,StorageError):logger.warning('Activity cache update deferred',exc_info=True)
        try:measured=max(0,int(activity.get('playtime_seconds',old.get('playtime_seconds',0))))
        except (TypeError,ValueError):measured=0
        meta=dict(info,schema_version=1,slot_id=identity,save_id=save_id,
            last_saved_at=valid_time(activity.get('last_saved_at')) or valid_time(old.get('last_saved_at')),
            last_played_at=valid_time(activity.get('last_played_at')) or valid_time(old.get('last_played_at')),
            playtime_seconds=measured,
            thumbnail='thumbnail.png')
        meta['thumbnail_signature']=preview_signature(info,self.image_root(slot))
        try:
            if old.get('thumbnail_signature')!=meta['thumbnail_signature'] or not (slot.directory/'thumbnail.png').is_file():
                render_thumbnail(info,self.image_root(slot),slot.directory/'thumbnail.png')
        except Exception:
            # This is a cache failure, not a failed SQLite save.
            logger.warning('Slot %s thumbnail refresh failed',identity,exc_info=True)
            meta['thumbnail_signature']=None
        try:atomic_json(slot.directory/'meta.json',meta)
        except OSError:logger.warning('Slot %s metadata refresh failed; SQLite retained',identity,exc_info=True)
        return meta
    def scan(self):
        results=[]
        for identity in (1,2):
            slot=self.slot(identity);meta=read_json(slot.directory/'meta.json')
            try:
                with self.lease(identity):
                    self._recover(identity)
                    if not slot.save.exists():
                        if slot.directory.exists() and any(slot.directory.iterdir()):raise StorageError('슬롯 DB가 없습니다. 남아 있는 파일과 백업을 보존했습니다.')
                        results.append(dict(slot_id=identity,state='empty',meta={}));continue
                    meta=self.refresh(identity);state='ready'
                results.append(dict(slot_id=identity,state=state,meta=meta))
            except Exception as error:
                logger.warning('Slot %s unavailable: %s',identity,error)
                save_id=read_json(slot.directory/'identity.json').get('save_id')
                activity=read_json(self.paths.config/'slot_activity.json').get(save_id,{})
                if isinstance(activity,dict):meta.update(activity)
                recoverable=Path(str(slot.save)+'-journal').exists() and isinstance(error,sqlite3.OperationalError) and 'readonly' in str(error).lower()
                message='비정상 종료된 SQLite 트랜잭션입니다. 이어하기를 선택하면 이 슬롯만 복구·검증합니다.' if recoverable else str(error)
                results.append(dict(slot_id=identity,state='recoverable' if recoverable else 'error',meta=meta,error=message,
                    backups=[str(p) for folder in (self.paths.saves/'slot_backups'/f'slot{identity}',slot.directory/'backups') for p in folder.glob('*.sqlite3')]))
        return results
    @staticmethod
    def latest(slots):
        occupied=[s for s in slots if s['state']!='empty']
        if not occupied:return None
        # Deliberately keep a corrupt most-recent slot as the continue target.
        # A user must explicitly choose another slot instead of silent fallback.
        return max(occupied,key=lambda s:(bool(valid_time(s['meta'].get('last_played_at'))),
            valid_time(s['meta'].get('last_played_at')) or valid_time(s['meta'].get('last_saved_at')) or '',-s['slot_id']))['slot_id']
    def _backup(self,identity):
        slot=self.slot(identity);folder=self.paths.saves/'slot_backups'/f'slot{identity}'
        folder.mkdir(parents=True,exist_ok=True);target=folder/(uuid.uuid4().hex+'.sqlite3')
        with closing(readonly(slot.save)) as src,closing(sqlite3.connect(target)) as dst:src.backup(dst)
        inspect_save(target)
        return target
    def _publish(self,identity,stage=None):
        slot=self.slot(identity);destination=self._safe_child(slot.directory)
        archive=self._safe_child(self.paths.saves/'.archives'/f'slot{identity}-{uuid.uuid4().hex}')
        archive.parent.mkdir(exist_ok=True)
        atomic_json(self._journal(identity),dict(archive=str(archive),stage=str(stage) if stage else None))
        try:
            if destination.exists():destination.rename(archive)
            if stage:Path(stage).rename(destination)
        except Exception:
            if not destination.exists() and archive.exists():archive.rename(destination)
            self._journal(identity).unlink(missing_ok=True)
            raise
        try:self._journal(identity).unlink()
        except OSError:logger.warning('Publish completed; journal will be reconciled on next scan',exc_info=True)
    def _replace(self,identity,builder,*,approved=False):
        with self.lease(identity):
            self._recover(identity);slot=self.slot(identity)
            occupied=slot.directory.exists() and any(slot.directory.iterdir())
            if occupied and not approved:raise StorageError('사용 중인 슬롯은 명시적으로 덮어쓰기를 승인해야 합니다.')
            if slot.save.exists():
                # Corrupt originals can still be preserved as an entire archive;
                # they are never destroyed to make way for a new game.
                try:self._backup(identity)
                except (ValueError,sqlite3.Error):logger.warning('Original DB corrupt; preserving complete slot archive',exc_info=True)
            stage=Path(tempfile.mkdtemp(prefix=f'.staging-slot{identity}-',dir=self.paths.saves))
            staged=SlotPaths(self.paths.root,stage,identity)
            try:
                builder(staged);inspect_save(staged.save)
                # Generate derived files against the staged DB before publishing.
                self._stage_metadata(staged)
                self._publish(identity,stage)
            finally:
                if stage.exists():
                    self._safe_child(stage)
                    if not stage.name.startswith('.staging-slot'):raise StorageError('임시 경로 검증 실패')
                    shutil.rmtree(stage)
            return self.refresh(identity,saved=True)
    def _stage_metadata(self,slot):
        info=inspect_save(slot.save);atomic_json(slot.directory/'identity.json',dict(save_id=uuid.uuid4().hex))
        # A failed thumbnail never aborts DB creation/import.
        signature=None
        try:
            render_thumbnail(info,self.image_root(slot),slot.directory/'thumbnail.png')
            signature=preview_signature(info,self.image_root(slot))
        except Exception:logger.warning('Staged preview unavailable',exc_info=True)
        try:atomic_json(slot.directory/'meta.json',dict(info,thumbnail_signature=signature))
        except OSError:logger.warning('Staged metadata cache unavailable',exc_info=True)
    def create(self,identity,*,approved=False):
        def build(slot):
            from .service import GameService
            service=GameService(self.root,slot.save,storage=slot)
            service.new_game()
        return self._replace(identity,build,approved=approved)
    def import_legacy(self,source,identity,*,approved=False):
        source=Path(source).resolve()
        if source in [self.slot(i).save.resolve() for i in (1,2)]:raise StorageError('현재 슬롯은 이전 단일 저장 가져오기 대상이 아닙니다.')
        # Reject sources held by another slot operation, too.
        inspect_save(source)
        def build(slot):
            slot.ensure()
            with closing(readonly(source)) as src,closing(sqlite3.connect(slot.save)) as dst:src.backup(dst)
            inspect_save(slot.save)
            from .database import Database
            Database(slot.save)  # Only the explicitly selected copy is migrated.
            roots=[source.parent.parent,source.parent]
            previous=read_json(self.paths.config/'legacy_import.json')
            if previous.get('source'):roots.append(Path(previous['source']).parent.parent)
            image_root=next((p for p in roots if (p/'assets').is_dir()),self.root)
            atomic_json(slot.config/'legacy_import.json',dict(source=str(source),image_root=str(image_root),policy='SQLite backup; original retained'))
        return self._replace(identity,build,approved=approved)
    def delete(self,identity,*,approved=False):
        if not approved:raise StorageError('슬롯 삭제에 명시적 승인이 필요합니다.')
        with self.lease(identity):
            self._recover(identity);slot=self.slot(identity)
            if not slot.directory.exists():return
            if slot.save.exists():
                try:self._backup(identity)
                except (ValueError,sqlite3.Error):logger.warning('Deleting corrupt slot to recoverable archive',exc_info=True)
            self._publish(identity)
    def save_active(self,identity,*,playtime):
        slot=self.slot(identity)
        with closing(sqlite3.connect(slot.save.resolve().as_uri()+'?mode=rw',uri=True,timeout=3)) as c:
            c.execute('PRAGMA wal_checkpoint(PASSIVE)')
        # SQL failures are fatal to closing; auxiliary file failures are logged.
        inspect_save(slot.save)
        try:return self.refresh(identity,saved=True,playtime=playtime,check=False)
        except OSError:
            logger.warning('Save committed but preview/activity cache could not be updated',exc_info=True)
            return inspect_save(slot.save,check=False)
