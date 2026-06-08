"""Standalone tests. Run: python3 scripts/test_sealevel_stats.py"""
import numpy as np

from sealevel_stats import exposed_area_km2_by_level


def test_exposed_area_counts_cells_above_level():
    # 4 cells with elevations -10, -5, 0, 5. Each cell = 1,000,000 m^2 = 1 km^2.
    elev = np.array([[-10.0, -5.0], [0.0, 5.0]], dtype=np.float32)
    cell_area_m2 = np.full((2, 2), 1_000_000.0)
    valid = np.ones((2, 2), dtype=bool)

    rows = exposed_area_km2_by_level(elev, cell_area_m2, valid, levels=[-120, -7, 0])
    by_level = {r["meters"]: r for r in rows}

    # At -120 m: present-day land is cells with elev > 0 -> just the 5 m cell = 1 km^2.
    assert by_level[0]["land_km2"] == 1.0, by_level[0]
    # At -7 m: cells above -7 are -5, 0, 5 -> 3 km^2. Exposed vs present = 3 - 1 = 2.
    assert by_level[-7]["land_km2"] == 3.0, by_level[-7]
    assert by_level[-7]["exposed_vs_present_km2"] == 2.0, by_level[-7]
    # At -120 m: all 4 cells above -120 -> 4 km^2 land, 3 km^2 newly exposed.
    assert by_level[-120]["land_km2"] == 4.0
    assert by_level[-120]["exposed_vs_present_km2"] == 3.0


def test_invalid_cells_are_excluded():
    elev = np.array([[5.0, 5.0]], dtype=np.float32)
    cell_area_m2 = np.full((1, 2), 1_000_000.0)
    valid = np.array([[True, False]])
    rows = exposed_area_km2_by_level(elev, cell_area_m2, valid, levels=[0])
    assert rows[0]["land_km2"] == 1.0  # the masked cell does not count


def run():
    test_exposed_area_counts_cells_above_level()
    test_invalid_cells_are_excluded()
    print("sealevel_stats: OK")


if __name__ == "__main__":
    run()
