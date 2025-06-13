"""Data ingestion utilities for heterogeneous sources."""

from pathlib import Path
from typing import Dict, List

import pandas as pd


def load_dataset(path: str) -> pd.DataFrame:
    """Load a dataset from CSV or Excel based on file extension."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    if file_path.suffix.lower() in {".csv"}:
        return pd.read_csv(file_path)
    if file_path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(file_path)
    raise ValueError(f"Unsupported file type: {file_path.suffix}")


def load_sources(sources: List[str]) -> Dict[str, pd.DataFrame]:
    """Load multiple datasets and return them keyed by basename."""
    data = {}
    for src in sources:
        df = load_dataset(src)
        data[Path(src).stem] = df
    return data
