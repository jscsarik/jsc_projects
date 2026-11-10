"""Release audit runner. All game writes are confined to test databases."""
from pathlib import Path
from contextlib import closing
import argparse,ast,ctypes,hashlib,importlib,json,os,platform,sqlite3,subprocess,sys,time,unittest,faulthandler,statistics,threading
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
OUT=Path(os.environ.get('IDOL_MANAGER_QA_REPORT_DIR',ROOT/'reports/release_qa')).resolve();OUT.mkdir(parents=True,exist_ok=True)

def save(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf8')

def rss():
    if os.name!='nt':return None
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ('peak','working','pp','p','npp','np','page','peakpage')]
    p=Counters();p.cb=ctypes.sizeof(p)
    ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(-1),ctypes.byref(p),p.cb)
    return p.working

class Monitor:
    def __init__(self):self.samples=[];self.done=threading.Event()
    def __enter__(self):
        self.start=time.perf_counter();self.cpu=time.process_time();self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start();return self
    def loop(self):
        last=(time.perf_counter(),time.process_time())
        while not self.done.wait(.2):
            now=(time.perf_counter(),time.process_time());self.samples.append(dict(elapsed=now[0]-self.start,rss=rss(),cpu_one_core_percent=100*(now[1]-last[1])/(now[0]-last[0])));last=now
    def __exit__(self,*_):self.done.set();self.thread.join()
    def result(self):
        return dict(elapsed=time.perf_counter()-self.start,cpu_seconds=time.process_time()-self.cpu,samples=self.samples,peak_rss=max([s['rss'] or 0 for s in self.samples]+[rss() or 0]))

def protect_connections():
    original=sqlite3.connect
    live={(ROOT/'data/idol_manager.sqlite3').resolve(),(ROOT/'saves/idol_manager.sqlite3').resolve()}
    # Also protect the production per-user save regardless of a QA override.
    base=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))
    live.add((base/'IDOL_Manager/saves/idol_manager.sqlite3').resolve())
    def connect(path,*a,**kw):
        raw=str(path)
        if raw!=':memory:':
            from urllib.parse import unquote,urlparse
            target=unquote(urlparse(raw).path).lstrip('/') if raw.startswith('file:') else raw
            if Path(target).resolve() in live and not (kw.get('uri') and 'mode=ro' in raw):raise RuntimeError('QA refuses a writable connection to the real save')
        return original(path,*a,**kw)
    sqlite3.connect=connect

def inventory():
    files=[p for folder in ('idol_manager','tests','tools','config') for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    assets={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'assets').rglob('*') if p.is_file()}
    static=[]
    for p in files:
        if p.suffix!='.py':continue
        try:
            tree=ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p));compile(tree,str(p),'exec')
            for n in ast.walk(tree):
                if isinstance(n,ast.ExceptHandler) and any(isinstance(t,ast.Pass) for t in n.body):static.append(dict(file=str(p.relative_to(ROOT)),line=n.lineno,review='except/pass; inspect whether fallback is intentional'))
        except Exception as e:static.append(dict(file=str(p.relative_to(ROOT)),error=repr(e)))
    import PySide6
    save('environment.json',dict(python=sys.version,pyside=PySide6.__version__,sqlite=sqlite3.sqlite_version,windows=platform.platform(),cpu_count=os.cpu_count(),git='No .git repository in project',source=manifest,static_findings=static))
    save('protected_assets_before.json',assets)
    source=ROOT/'data/idol_manager.sqlite3'
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as c,closing(sqlite3.connect(OUT/'user_save_snapshot.sqlite3')) as dst:
        c.backup(dst);save('user_save_before.json',dict(version=c.execute('PRAGMA user_version').fetchone()[0],absolute_day=c.execute('SELECT absolute_day FROM game_clock').fetchone()[0],integrity=c.execute('PRAGMA integrity_check').fetchone()[0],foreign_keys=c.execute('PRAGMA foreign_key_check').fetchall(),backup=str(OUT/'user_save_snapshot.sqlite3')))

class Result(unittest.TextTestResult):
    def __init__(self,*a,**kw):super().__init__(*a,**kw);self.details=[]
    def startTest(self,t):super().startTest(t);self.begin=time.perf_counter();self.status='PASS'
    def addFailure(self,t,e):self.status='FAIL';super().addFailure(t,e)
    def addError(self,t,e):self.status='ERROR';super().addError(t,e)
    def addSkip(self,t,r):self.status='SKIP';super().addSkip(t,r)
    def stopTest(self,t):self.details.append(dict(test=t.id(),status=self.status,seconds=time.perf_counter()-self.begin));super().stopTest(t)

def child(module):
    protect_connections();faulthandler.enable();faulthandler.dump_traceback_later(45,repeat=True)
    suite=unittest.defaultTestLoader.loadTestsFromName(module)
    with Monitor() as mon:result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(suite)
    save('test_'+module.replace('.','_')+'.json',dict(tests=result.testsRun,success=result.wasSuccessful(),failures=[(str(t),e) for t,e in result.failures],errors=[(str(t),e) for t,e in result.errors],skipped=[(str(t),r) for t,r in result.skipped],details=result.details,resources=mon.result()))
    faulthandler.cancel_dump_traceback_later();return 0 if result.wasSuccessful() else 1

def tests(modules):
    results=[]
    for module in modules:
        start=time.perf_counter();print(module,flush=True)
        log=OUT/(module.replace('.','_')+'.log')
        with log.open('w',encoding='utf8') as f:
            try:r=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child',module],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,env=dict(os.environ,QT_QPA_PLATFORM=os.environ.get('QA_QT_PLATFORM','offscreen')),timeout=240);code=r.returncode
            except subprocess.TimeoutExpired:code='TIMEOUT'
        results.append(dict(module=module,exit_code=code,seconds=time.perf_counter()-start,log=str(log)))
        save('test_modules.json',results)
    return int(any(r['exit_code']!=0 for r in results))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--inventory',action='store_true');p.add_argument('--child');p.add_argument('--tests',nargs='*');a=p.parse_args()
    if a.inventory:inventory()
    elif a.child:raise SystemExit(child(a.child))
    else:raise SystemExit(tests(a.tests or ['tests.'+p.stem for p in sorted((ROOT/'tests').glob('test_*.py'))]))
