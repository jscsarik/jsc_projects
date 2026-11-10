"""QA-only synthetic photo supply; real services; staged 3/5/10/20 seasons."""
from pathlib import Path
from types import SimpleNamespace
from contextlib import closing
from collections import Counter
import argparse,hashlib,json,os,sqlite3,struct,sys,time,zlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.setdefault('IDOL_MANAGER_QA_REPORT_DIR',str(ROOT/'reports/release_qa/followup'))
from tools.simulate_game import Simulation,dump,csvfile,quick_audit
from tools.release_qa import Monitor,OUT,rss,protect_connections,save

def make_world(folder,count=1600):
    folder=folder.resolve()
    if not folder.is_relative_to(ROOT/'diagnostics') or folder==ROOT/'diagnostics':raise ValueError('QA resources must be a dedicated diagnostics subfolder')
    marker=folder/'qa_world.json'
    if marker.exists():
        if json.loads(marker.read_text(encoding='utf8'))!=dict(qa_only=True,count=count,format='unique-4px-png-v1'):raise ValueError('Existing QA world parameters differ')
        return folder
    if folder.exists() and any(folder.iterdir()):raise ValueError('Will not overwrite a nonempty resource folder')
    photos=folder/'assets/idols';photos.mkdir(parents=True)
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    for n in range(count):
        rgb=bytes((n%256,(n//256)%256,(n//65536)%256))
        png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',4,4,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+rgb*4)*4))+chunk(b'IEND',b'')
        (photos/f'QA 가상 인물 {n:04}.png').write_bytes(png)
    dump(marker,dict(qa_only=True,count=count,format='unique-4px-png-v1'));return folder

class LongSimulation(Simulation):
    def __init__(self,args):
        super().__init__(args);self.season_started=time.perf_counter();self.season_cpu=time.process_time();self.resources=[]
        report=self.output/'season_resources.json'
        if args.resume and report.exists():self.resources=json.loads(report.read_text(encoding='utf8'))
        if args.resume:
            for issue in self.issues:
                if 'PermissionError' in issue.get('error','') and 'checkpoint.json' in issue.get('traceback',''):
                    issue.update(fixed=True,resolution='Bounded atomic-rename retry; monitoring no longer reads the checkpoint; committed DB and final RNG checkpoint preserved')
    def budget(self):
        # Save full state once per committed day (base loop) and at graceful
        # stops, rather than serializing all historical metrics before each pick.
        if time.monotonic()>=self.deadline:
            self.save();raise TimeoutError('QA checkpoint at last committed action')
    def export(self,status):
        super().export(status)
        path=self.output/'simulation_summary.json';summary=json.loads(path.read_text(encoding='utf8'))
        summary['qa_synthetic_supply']=True
        summary['not_tested']=[f'{n} seasons' for n in (5,10,20) if summary['completed_seasons']<n]+['physical GUI','all possible seeds','forced OS shutdown during every action']
        dump(path,summary)
    def finish_season(self,season):
        super().finish_season(season)
        with closing(self.service.database.connect()) as c:
            exposure=c.execute('SELECT COUNT(*) FROM annual_entries WHERE intake_season=?',(season,)).fetchone()[0]
            minors=c.execute('SELECT COUNT(*) FROM annual_entries WHERE intake_season=? AND initial_age BETWEEN 14 AND 16',(season,)).fetchone()[0]
            special=c.execute('SELECT COUNT(*) FROM annual_secrets s JOIN annual_entries e ON e.person_id=s.person_id WHERE e.intake_season=?',(season,)).fetchone()[0]
            retired_repick=c.execute('SELECT COUNT(*) FROM annual_turns t JOIN market_careers m ON m.person_id=t.person_id WHERE m.retired_day IS NOT NULL AND t.picked_day>m.retired_day').fetchone()[0]
            if (exposure,minors,special,retired_repick)!=(70,60,2,0):raise AssertionError('Annual supply/retirement invariant violated')
            history=[dict(r) for r in c.execute('SELECT kind,COUNT(*) count FROM market_history WHERE absolute_day>=? AND absolute_day<? GROUP BY kind',((season-1)*217,season*217))]
            t=time.perf_counter();self.service.records.agencies(season=season);lookup=time.perf_counter()-t
        elapsed=time.perf_counter()-self.season_started
        self.resources.append(dict(season=season,elapsed_seconds=elapsed,cpu_seconds=time.process_time()-self.season_cpu,rss=rss(),db_bytes=self.path.stat().st_size,agency_records_seconds=lookup,newcomers=exposure,minors=minors,specials=special,history=history,status=self.seasons[-1]['status']))
        dump(self.output/'season_resources.json',self.resources);self.season_started=time.perf_counter();self.season_cpu=time.process_time()

def compare(a,b):
    ignored={'created_at','picked_at','initialized_at','started_at','selected_at','completed_at'};checks=[]
    with closing(sqlite3.connect(a.as_uri()+'?mode=ro',uri=True)) as ca,closing(sqlite3.connect(b.as_uri()+'?mode=ro',uri=True)) as cb:
        for table, in ca.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            columns=[r[1] for r in ca.execute('PRAGMA table_info('+table+')') if r[1] not in ignored]
            primary=[r[1] for r in sorted(ca.execute('PRAGMA table_info('+table+')'),key=lambda r:r[5]) if r[5]]
            q='SELECT '+','.join(columns)+' FROM '+table+' ORDER BY '+','.join(primary or columns)
            hashes=[]
            for c in (ca,cb):
                h=hashlib.sha256()
                for row in c.execute(q):h.update(json.dumps(row,ensure_ascii=False,separators=(',',':')).encode())
                hashes.append(h.hexdigest())
            checks.append(dict(table=table,equal=hashes[0]==hashes[1]))
    return dict(ignored_wall_clock_columns=sorted(ignored),checks=checks,pass_all=all(r['equal'] for r in checks))

def stage(name,seasons,seed,world):
    folder=ROOT/'diagnostics'/name;resume=(folder/'simulation.sqlite3').exists()
    args=SimpleNamespace(output=folder,seed=seed,seasons=seasons,budget_seconds=86400,resume=resume,allow_long_run=True,resource_root=world)
    started=time.perf_counter()
    with Monitor() as monitor:status=LongSimulation(args).run()
    summary=json.loads((folder/'simulation_summary.json').read_text(encoding='utf8'))
    resource=monitor.result();save(f'{name}_to{seasons}_resources.json',resource)
    return dict(name=name,target=seasons,status=status,completed=summary['completed_seasons'],elapsed=time.perf_counter()-started,db_bytes=(folder/'simulation.sqlite3').stat().st_size,peak_rss=resource['peak_rss'],issues=summary['issues'])

def main():
    p=argparse.ArgumentParser();p.add_argument('--max-seasons',type=int,choices=(3,5,10,20),default=20);p.add_argument('--seed',type=int,default=261029);a=p.parse_args()
    protect_connections();world=make_world(ROOT/'diagnostics/followup_world');stages=[]
    journal=OUT/'long_stages.json'
    if journal.exists():stages=json.loads(journal.read_text(encoding='utf8'))
    for name in ('followup_a','followup_b'):
        done=next((s for s in stages if s['name']==name and s['target']==3 and s['status']=='completed'),None)
        if done:continue
        result=stage(name,3,a.seed,world);stages.append(result);dump(journal,stages)
        if result['status']!='completed' or result['completed']<3:return 2
    proof=OUT/'three_season_reproducibility.json'
    equality=json.loads(proof.read_text(encoding='utf8')) if proof.exists() else compare(ROOT/'diagnostics/followup_a/simulation.sqlite3',ROOT/'diagnostics/followup_b/simulation.sqlite3')
    save('three_season_reproducibility.json',equality)
    if not equality['pass_all']:return 3
    for target in (5,10,20):
        if target>a.max_seasons:break
        done=next((s for s in stages if s['name']=='followup_a' and s['target']==target and s['status']=='completed'),None)
        if done:continue
        result=stage('followup_a',target,a.seed,world);stages.append(result);dump(journal,stages)
        if result['status']!='completed' or result['completed']<target:return 2
    return 0
if __name__=='__main__':raise SystemExit(main())
