from dataclasses import dataclass
from pathlib import Path
import unicodedata
import uuid

from .domain import Person

SUPPORTED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
NAMESPACE = uuid.UUID("480105dc-a86d-4d68-adc4-a2b6a5369e4e")


@dataclass(frozen=True)
class ScanResult:
    people: tuple[Person, ...]
    image_count: int
    duplicates: tuple[str, ...]


def scan_idols(root: Path,extra_folder:Path|None=None) -> ScanResult:
    folder = root / "assets" / "idols"
    if not folder.is_dir() and not (extra_folder and extra_folder.is_dir()):
        return ScanResult((), 0, ())
    files = sorted(
        (p for base in (folder,*((extra_folder,) if extra_folder else ())) for p in base.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS),
        key=lambda p:p.as_posix().casefold(),
    )
    people = {}
    duplicates = []
    for path in files:
        # Treat same names in different formats/subfolders as the same person.
        name = unicodedata.normalize("NFC", path.stem).strip()
        key = name.casefold()
        if not key:
            continue
        if key in people:
            duplicates.append(path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path.resolve()))
            continue
        photo=path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path.resolve())
        people[key] = Person(str(uuid.uuid5(NAMESPACE, key)), name, key, photo)
    return ScanResult(tuple(people.values()), len(files), tuple(duplicates))
