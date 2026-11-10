"""Render the requested five-player arrangement using a read-only snapshot."""
from pathlib import Path
from contextlib import closing
from collections import Counter
import sqlite3,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSize
from PySide6.QtTest import QTest
from idol_manager.ui.battle_view import BattleView
from idol_manager.ui.thumbnails import ThumbnailCache
OUT=ROOT/'reports/release28';app=QApplication([])
photos=ThumbnailCache(ROOT,OUT/'scene_cache',image_size=QSize(360,480));view=BattleView(photos)
with closing(sqlite3.connect((OUT/'original_0.sqlite3').as_uri()+'?mode=ro',uri=True)) as c:
    agencies=c.execute('SELECT id,name FROM agencies WHERE id IN ("jyp","yg") ORDER BY id').fetchall();people=[]
    for agency,name in agencies:
        for identity,name,path in c.execute('SELECT p.id,p.name,p.photo_path FROM roster_memberships r JOIN people p ON p.id=r.person_id WHERE r.agency_id=? AND r.career_status="first_team" ORDER BY p.name',(agency,)):
            people.append(dict(id=identity,name=name,photo_path=path,agency_id=agency,leader=not any(p['agency_id']==agency for p in people)))
view.configure('음악방송 · 출전자 전원 표시',agencies,people)
counts=Counter({p['id']:32+i for i,p in enumerate(people)});phases={p['id']:dict(main=18+i%4,support=14+i//4) for i,p in enumerate(people)}
view.final_counts(counts,phases);view.show()
for width,height in ((1700,650),(1100,550),(800,550)):
    view.resize(width,height);QTest.qWait(250)
    for _ in range(40):
        if not photos.pending:break
        QTest.qWait(10)
    view.grab().save(str(OUT/f'battle_5v5_{width}x{height}.png'))
view.close();photos.close()
