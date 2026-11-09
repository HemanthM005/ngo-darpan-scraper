"""Tests for the NGO Darpan cleaning + validation layer."""
from __future__ import annotations

import pandas as pd

from ngo_darpan_scraper.clean import _split_sectors, clean
from ngo_darpan_scraper.validate import validate


def test_split_sectors_dedupes_and_normalises():
    assert _split_sectors("Health, Education; Health") == "Health; Education"
    assert _split_sectors("  ") is None
    assert _split_sectors(None) is None


def test_clean_dedupes_on_unique_id():
    raw = [
        {"Unique Id": "TS/2019/001", "Name of NGO": "Helping Hands", "State": "Telangana",
         "Sectors working in": "Health, Education", "Address": "Hyderabad"},
        {"Unique Id": "TS/2019/001", "Name of NGO": "Helping Hands", "State": "Telangana",
         "Sectors working in": "Health", "Address": "Hyderabad"},   # dup id
        {"Unique Id": "KL/2020/045", "Name of NGO": "Green Kerala", "State": "Kerala",
         "Sectors working in": "Environment", "Address": "Kochi"},
    ]
    df = clean(raw)
    assert len(df) == 2
    assert set(df["unique_id"]) == {"TS/2019/001", "KL/2020/045"}


def test_clean_does_not_merge_rows_missing_unique_id():
    """Rows without an id must not collapse into one (NaN-equality trap)."""
    raw = [
        {"Name of NGO": "Alpha Trust", "State": "Goa", "Address": "Panaji"},
        {"Name of NGO": "Beta Society", "State": "Goa", "Address": "Margao"},
    ]
    df = clean(raw)
    assert len(df) == 2


def test_cleaned_frame_passes_validation():
    raw = [
        {"Unique Id": "MH/2018/900", "Name of NGO": "City Welfare", "State": "Maharashtra",
         "Sectors working in": "Health", "Address": "Mumbai"},
    ]
    out = validate(clean(raw))
    assert isinstance(out, pd.DataFrame) and len(out) == 1
