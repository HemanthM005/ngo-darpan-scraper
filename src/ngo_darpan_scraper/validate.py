"""Schema + quality checks for scraped NGO records."""
from __future__ import annotations

from pandera.pandas import Check, Column, DataFrameSchema

# NGO Darpan unique ids look like "AP/2019/0123456" (state/year/serial), though
# older records vary, so we keep the check permissive but non-empty.
ngo_schema = DataFrameSchema(
    {
        "unique_id": Column(
            str,
            checks=Check.str_length(min_value=3),
            nullable=True,
        ),
        "ngo_name": Column(
            str,
            checks=Check.str_length(min_value=2),
            nullable=False,
        ),
        "state": Column(str, nullable=True),
        "sectors": Column(str, nullable=True),
        "address": Column(str, nullable=True),
    },
    strict=True,
    coerce=True,
)


def validate(df):
    """Validate; raises pandera SchemaErrors on any violation."""
    return ngo_schema.validate(df, lazy=True)
