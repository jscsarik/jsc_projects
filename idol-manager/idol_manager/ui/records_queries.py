"""Per-page bounded, revision-aware query cache and detached worker requests."""
from collections import OrderedDict
from copy import deepcopy
import json,threading,inspect
from pathlib import Path
from PySide6.QtCore import QObject,QRunnable,Signal

class QueryCache:
    def __init__(self,api):self.api=api;self.values=OrderedDict();self.lock=threading.RLock()
    def revision(self):
        path=self.api.database.path
        values=[str(path.resolve())]
        for p in (path,Path(str(path)+'-wal')):
            try:s=p.stat();values.append((s.st_ino,s.st_mtime_ns,s.st_size))
            except FileNotFoundError:
                if p==path:raise FileNotFoundError('저장 파일을 찾을 수 없습니다: '+str(path))
                values.append(None)
        return tuple(values)
    def has_cached(self,name,args,kwargs):
        key=self.key(name,args,kwargs)
        with self.lock:return key in self.values
    def key(self,name,args,kwargs):
        bound=inspect.signature(getattr(self.api,name)).bind(*args,**kwargs);bound.apply_defaults()
        return (name,json.dumps(bound.arguments,sort_keys=True),self.revision())
    def __getattr__(self,name):
        method=getattr(self.api,name)
        if name not in ('player_choices','players','content_players','contents','compare_players','compare_agencies','leaders','league','champions','agencies'):return method
        def query(*args,**kwargs):
            filters={k:kwargs.pop(k) for k in ('name','minimum','role') if k in kwargs} if name=='players' else {}
            key=self.key(name,args,kwargs)
            with self.lock:
                value=self.values.get(key)
                if value is not None:self.values.move_to_end(key)
            if value is None:
                value=method(*args,**kwargs)
                if key[2]==self.revision():
                    with self.lock:
                        self.values[key]=value
                        while len(self.values)>64:self.values.popitem(last=False)
                        heavy=[k for k in self.values if k[0]=='players']
                        for expired in heavy[:-8]:self.values.pop(expired,None)
            result=deepcopy(value)
            if name=='players':result=[r for r in result if filters.get('name','').casefold() in r['name'].casefold() and r['attempts']>=filters.get('minimum',0) and (not filters.get('role') or r['career_status']==filters['role'])]
            return result
        return query

class QuerySignals(QObject):
    finished=Signal(int,object,object)
    preview=Signal(int,object,object)
class QueryJob(QRunnable):
    def __init__(self,api,generation,requests,signals):
        super().__init__();self.api=api;self.generation=generation;self.requests=requests;self.signals=signals
        self.cancelled=threading.Event()
    def run(self):
        revision=None;error=None
        try:
            from ..records_read import cancellation_scope
            with cancellation_scope(self.cancelled):
                revision=self.api.revision()
                for name,args,kwargs in self.requests:
                    if self.cancelled.is_set():break
                    if name=='players' and kwargs.get('season') is None and not self.api.has_cached(name,args,kwargs):
                        ids=[p['id'] for p in self.api.player_choices()[:20]]
                        self.signals.preview.emit(self.generation,revision,self.api.players(person_ids=ids,**kwargs))
                    if self.cancelled.is_set():break
                    getattr(self.api,name)(*args,**kwargs)
        except Exception as e:
            if not self.cancelled.is_set():error=str(e)
        self.signals.finished.emit(self.generation,revision,error)
