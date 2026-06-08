"""Pure numpy area math for the sea-level change readout. No file IO."""
from __future__ import annotations

import numpy as np

PRESENT_LEVEL_M = 0.0


def exposed_area_km2_by_level(
    elev: np.ndarray,
    cell_area_m2: np.ndarray,
    valid: np.ndarray,
    levels: list[float],
) -> list[dict]:
    """For each sea level, total subaerial land area and area exposed vs present.

    `land_km2` = area of valid cells with elevation strictly above the level.
    `exposed_vs_present_km2` = land at this level minus present-day land (level 0),
    i.e. how much extra ground is dry compared with today. Clamped at 0.
    """
    masked_area = np.where(valid, cell_area_m2, 0.0)
    present_land_m2 = float(masked_area[valid & (elev > PRESENT_LEVEL_M)].sum())

    rows: list[dict] = []
    for level in levels:
        land_m2 = float(masked_area[valid & (elev > level)].sum())
        exposed = max(0.0, land_m2 - present_land_m2)
        rows.append({
            "meters": level,
            "land_km2": round(land_m2 / 1_000_000.0, 1),
            "exposed_vs_present_km2": round(exposed / 1_000_000.0, 1),
        })
    return rows
