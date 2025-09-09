from __future__ import annotations

from typing import Literal, Tuple


DebtCategory = Literal["SHORT", "NB", "TIPS", "OTHER"]
BUCKETS_ISSUANCE: Tuple[DebtCategory, DebtCategory, DebtCategory] = ("SHORT", "NB", "TIPS")
BUCKETS_ALL: Tuple[DebtCategory, DebtCategory, DebtCategory, DebtCategory] = (
    "SHORT",
    "NB",
    "TIPS",
    "OTHER",
)


