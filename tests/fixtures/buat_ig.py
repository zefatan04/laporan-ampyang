"""Membuat CSV Instagram Insights buatan dengan format persis ekspor asli
(UTF-16 LE + BOM, `sep=,`, judul metrik, `"Tanggal","Primary"`)."""
from datetime import date
from pathlib import Path


def buat_ig(path: Path, judul: str, nilai: dict[date, int], header=("Tanggal", "Primary"), akhiran_waktu="T00:00:00") -> Path:
    baris = ["sep=,", f'"{judul}"', ",".join(f'"{h}"' for h in header)]
    baris += [f'"{t.isoformat()}{akhiran_waktu}","{v}"' for t, v in nilai.items()]
    path.write_bytes(b"\xff\xfe" + ("\n".join(baris) + "\n\n").encode("utf-16-le"))
    return path
