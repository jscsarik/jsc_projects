from pathlib import Path
import pefile,json
root=Path(__file__).resolve().parents[1]/'dist/IDOL_Manager/_internal'
files={p.name.lower():p for p in root.rglob('*') if p.suffix.lower() in ('.dll','.pyd')}
result=[];cache={}
for name in ('qtwidgets.pyd','qt6widgets.dll','qt6gui.dll','qt6core.dll','pyside6.abi3.dll','shiboken6.abi3.dll'):
    if name not in files:continue
    p=files[name];pe=pefile.PE(str(p),max_symbol_exports=100000)
    for dep in getattr(pe,'DIRECTORY_ENTRY_IMPORT',[]):
        n=dep.dll.decode().lower()
        if n not in files:continue
        if n not in cache:cache[n]=pefile.PE(str(files[n]),max_symbol_exports=100000)
        symbols=getattr(cache[n],'DIRECTORY_ENTRY_EXPORT',None)
        exports={e.name for e in symbols.symbols} if symbols else set()
        missing=[s.name.decode(errors='replace') for s in dep.imports if s.name and s.name not in exports]
        if missing:result.append(dict(file=str(p),dependency=str(files[n]),missing=missing))
print(json.dumps(result,indent=2))
