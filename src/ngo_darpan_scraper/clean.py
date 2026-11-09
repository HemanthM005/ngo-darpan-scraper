"""Normalise raw NGO Darpan rows into a tidy, de-duplicated DataFrame."""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

_COLUMN_ALIASES = {
    "unique id": "unique_id",
    "unique_id": "unique_id",
    "ngo unique id": "unique_id",
    "name of ngo": "ngo_name",
    "name of vo/ngo": "ngo_name",
    "ngo_name": "ngo_name",
    "name": "ngo_name",
    "state": "state",
    "address": "address",
    "sectors working in": "sectors",
    "sector": "sectors",
    "sectors": "sectors",
}

_WS = re.compile(r"\s+")


def _canon_key(key: str) -> str:
    return _COLUMN_ALIASES.get(_WS.sub(" ", str(key).strip().lower()), _WS.sub(" ", str(key).strip().lower()))


def _tidy(val: Any) -> str | None:
    if val is None:
        return None
    s = _WS.sub(" ", str(val)).strip()
    return s or None


def _split_sectors(val: Any) -> str | None:
    """Sectors come as a comma/semicolon blob; normalise to 'A; B; C'."""
    s = _tidy(val)
    if not s:
        return None
    parts = [p.strip() for p in re.split(r"[,;|]", s) if p.strip()]
    return "; ".join(dict.fromkeys(parts)) or None   # dedupe, keep order


def clean(raw_rows: list[dict[str, Any]]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for row in raw_rows:
        rec = {_canon_key(k): v for k, v in row.items()}
        uid = _tidy(rec.get("unique_id"))
        name = _tidy(rec.get("ngo_name"))
        if not uid and not name:
            continue                      # skip header/garbage rows
        records.append(
            {
                "unique_id": uid,
                "ngo_name": name,
                "state": _tidy(rec.get("state")),
                "sectors": _split_sectors(rec.get("sectors")),
                "address": _tidy(rec.get("address")),
            }
        )

    df = pd.DataFrame(records, columns=["unique_id", "ngo_name", "state", "sectors", "address"])

    # Build a single identity key: unique_id when present, else name|state.
    # (A plain drop_duplicates on unique_id would wrongly merge every row whose
    # id is missing, since pandas treats all NaNs as equal.)
    key = df["unique_id"].fillna("").astype(str)
    fallback = df["ngo_name"].fillna("").astype(str) + "|" + df["state"].fillna("").astype(str)
    df["_key"] = key.where(key != "", fallback)
    df = df[df["_key"] != "|"]                       # no identity at all -> drop
    df = df.drop_duplicates(subset=["_key"]).drop(columns="_key")

    df = df.sort_values(["state", "ngo_name"], na_position="last").reset_index(drop=True)
    return df
