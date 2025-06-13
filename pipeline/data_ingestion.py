"""Data ingestion utilities for heterogeneous sources."""

from pathlib import Path
from typing import Dict, List
import io
import zipfile
import requests

import pandas as pd


def _read_from_bytes(data: bytes, suffix: str) -> pd.DataFrame:
    """Read a CSV or Excel file from raw bytes."""
    if suffix == ".csv":
        return pd.read_csv(io.BytesIO(data))
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(io.BytesIO(data))
    raise ValueError(f"Unsupported file type: {suffix}")


def _download(url: str) -> bytes:
    """Download a URL and return the raw bytes."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.content


def load_dataset(path: str) -> pd.DataFrame:
    """Load a dataset from CSV, Excel, or a zipped archive."""
    # Allow HTTP(S) URLs in addition to local files
    if path.startswith("http://") or path.startswith("https://"):
        raw = _download(path)
        suffix = Path(path).suffix.lower()
        if suffix == ".zip":
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                name = zf.namelist()[0]
                with zf.open(name) as f:
                    return _read_from_bytes(f.read(), Path(name).suffix.lower())
        return _read_from_bytes(raw, suffix)

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    if file_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(file_path) as zf:
            name = zf.namelist()[0]
            with zf.open(name) as f:
                return _read_from_bytes(f.read(), Path(name).suffix.lower())
    return _read_from_bytes(file_path.read_bytes(), file_path.suffix.lower())


def load_sources(sources: List[str]) -> Dict[str, pd.DataFrame]:
    """Load multiple datasets and return them keyed by basename."""
    data = {}
    for src in sources:
        df = load_dataset(src)
        data[Path(src).stem] = df
    return data
