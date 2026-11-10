"""Fresh-cache imports for investigating the one native first-launch failure."""
from pathlib import Path
import argparse,json,shutil,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from release27_exe import run,OUT,EXE
parser=argparse.ArgumentParser();parser.add_argument('--prefix',default='cold_fixed_import');args=parser.parse_args()
if Path(args.prefix).name!=args.prefix:raise ValueError('Plain prefix only')
install=OUT/'최종 설치 위치 제한 테스트';values=[]
shutil.copytree(EXE.parent,install,dirs_exist_ok=True)
for n in range(5):
    user=OUT/f'{args.prefix}_{n}'
    if user.exists():raise ValueError('Do not overwrite earlier evidence')
    value=run(install/'IDOL_Manager.exe',user);values.append(value)
    (OUT/(args.prefix+'_repeats.json')).write_text(json.dumps(values,ensure_ascii=False,indent=2),encoding='utf8')
    print(n,value['success'],value['exit_code'],flush=True)
    if not value['success'] or value['exit_code']!=0:raise SystemExit(2)
