import zipfile
from pathlib import Path

MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024  # 500MB
MAX_FILE_COUNT = 20_000


class ExtractionError(Exception):
    pass


def safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    """Extract a zip file while guarding against zip-slip and oversized archives.

    Untrusted repos are ingested via this path, so every member's resolved
    target must stay inside `dest` before anything is written to disk.
    """
    dest = dest.resolve()
    infos = zf.infolist()

    if len(infos) > MAX_FILE_COUNT:
        raise ExtractionError(f"zip contains too many files ({len(infos)} > {MAX_FILE_COUNT})")

    total = sum(info.file_size for info in infos)
    if total > MAX_UNCOMPRESSED_BYTES:
        raise ExtractionError(f"zip uncompressed size too large ({total} bytes)")

    for info in infos:
        target = (dest / info.filename).resolve()
        if target != dest and dest not in target.parents:
            raise ExtractionError(f"unsafe path in zip entry: {info.filename}")

    zf.extractall(dest)
