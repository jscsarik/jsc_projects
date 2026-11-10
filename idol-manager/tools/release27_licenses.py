"""Fetch standard license texts only, from their official publisher."""
from pathlib import Path
import urllib.request
folder=Path(__file__).resolve().parents[1]/'packaging/licenses';folder.mkdir(exist_ok=True)
for label,url in (
    ('LGPL-3.0.txt','https://www.gnu.org/licenses/lgpl-3.0.txt'),
    ('LGPL-2.1.txt','https://www.gnu.org/licenses/old-licenses/lgpl-2.1.txt'),
    ('GPL-3.0.txt','https://www.gnu.org/licenses/gpl-3.0.txt')):
    if (folder/label).exists():continue
    try:
        with urllib.request.urlopen(url,timeout=10) as response:content=response.read()
    except OSError:
        # The official FFmpeg source also distributes these standard licenses.
        name={'LGPL-2.1.txt':'COPYING.LGPLv2.1','GPL-3.0.txt':'COPYING.GPLv3'}[label]
        with urllib.request.urlopen('https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/'+name,timeout=10) as response:content=response.read()
    (folder/label).write_bytes(content);print(label,len(content))
