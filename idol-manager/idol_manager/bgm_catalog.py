"""Local MP3/WAV discovery and independent shuffle bags; no game DB access."""
from dataclasses import dataclass
from pathlib import Path
import logging
import random
import re

CATEGORIES=('default','battle','title')
EXTENSIONS=frozenset(('.mp3','.wav'))
logger=logging.getLogger(__name__)


def song_title(path):
    """Replaceable filename resolver; a future metadata provider can override it."""
    path=Path(path)
    parts=re.split(r'\s+[-–—]\s+',path.stem.strip(),maxsplit=1)
    if len(parts)==2 and all(p.strip() for p in parts):
        return ' — '.join(p.strip() for p in parts)
    return path.name


@dataclass(frozen=True)
class BgmTrack:
    path: Path
    title: str
    signature: tuple[int,int]


def scan_music(root, title_resolver=song_title,*,extra_folder=None):
    result={category:[] for category in CATEGORIES}
    root=Path(root).resolve()
    for category in CATEGORIES:
        folders=[root/'assets/audio/bgm'/category]
        if extra_folder is not None:folders.append(Path(extra_folder)/category)
        for folder in folders:
            try:
                # Installed resources are read-only when a user music directory
                # is supplied. Standalone/test callers retain folder setup.
                if extra_folder is None or folder.parent==Path(extra_folder):folder.mkdir(parents=True,exist_ok=True)
                if not folder.is_dir():continue
                for path in folder.iterdir():
                    try:
                        if path.suffix.casefold() not in EXTENSIONS or not path.is_file():continue
                        stat=path.stat()
                        try:title=str(title_resolver(path))
                        except Exception:
                            logger.exception('BGM metadata failed: %s',path);title=path.name
                        result[category].append(BgmTrack(path.resolve(),title,(stat.st_size,stat.st_mtime_ns)))
                    except OSError as error:logger.warning('BGM file scan failed: %s: %s',path,error)
            except OSError as error:logger.warning('BGM folder scan failed: %s: %s',folder,error)
        result[category].sort(key=lambda t:(t.path.name.casefold(),str(t.path)))
    return {key:tuple(value) for key,value in result.items()}


class ShuffleBag:
    def __init__(self,rng=None):
        self.rng=rng or random.SystemRandom()
        self.tracks={};self.remaining=[];self.last=None

    def update(self,tracks):
        current={t.path:t for t in tracks}
        added=[p for p in current if p not in self.tracks]
        self.remaining=[p for p in self.remaining if p in current]
        if added:
            self.remaining.extend(added)
            self.rng.shuffle(self.remaining)
        self.tracks=current

    def next(self,excluded=()):
        allowed=set(self.tracks)-set(excluded)
        self.remaining=[p for p in self.remaining if p in allowed]
        if not allowed:return None
        if not self.remaining:
            self.remaining=sorted(allowed,key=str);self.rng.shuffle(self.remaining)
        if len(self.remaining)>1 and self.remaining[-1]==self.last:
            self.remaining[-1],self.remaining[0]=self.remaining[0],self.remaining[-1]
        path=self.remaining.pop();self.last=path
        return self.tracks[path]
