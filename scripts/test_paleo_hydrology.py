"""Standalone tests for paleo_hydrology. Run: python3 scripts/test_paleo_hydrology.py"""
import numpy as np

from paleo_hydrology import fill_depressions


def test_fill_raises_interior_pit_to_pour_point():
    # 5x5: a deep pit (0) ringed by a 5 m lip inside a 9 m rim. A 2 m notch at
    # (2,3) leads to an ocean outlet at (2,4) (invalid). The only escape from the
    # pit crosses the 2 m notch, so canonical priority-flood must raise the pit to
    # exactly 2 m - its pour point - not leave it at 0 and not flood it to the rim.
    dem = np.array([
        [9, 9, 9, 9, 9],
        [9, 5, 5, 5, 9],
        [9, 5, 0, 2, 9],
        [9, 5, 5, 5, 9],
        [9, 9, 9, 9, 9],
    ], dtype=np.float32)
    valid = np.ones((5, 5), dtype=bool)
    valid[2, 4] = False  # ocean outlet just past the notch

    filled = fill_depressions(dem, valid)

    # Pit raised to the 2 m pour point: not left at 0, not flooded to the 9 m rim.
    assert filled[2, 2] == 2.0, filled[2, 2]
    # The notch is already at its drainage level, so it is unchanged.
    assert filled[2, 3] == 2.0, filled[2, 3]
    # Cells already draining out are unchanged; filling never lowers terrain.
    assert filled[0, 0] == 9.0, filled[0, 0]
    assert np.all(filled >= dem)


def test_fill_leaves_monotone_slope_untouched():
    # A clean ramp draining west has no depressions.
    dem = np.array([[3, 2, 1], [3, 2, 1], [3, 2, 1]], dtype=np.float32)
    valid = np.ones((3, 3), dtype=bool)
    filled = fill_depressions(dem, valid)
    assert np.allclose(filled, dem)


def test_d8_points_downhill_west_on_a_ramp():
    from paleo_hydrology import d8_flow_directions
    # Values increase left-to-right: col 0 is low (west), col 2 is high (east).
    # Water drains westward (toward decreasing column index).
    dem = np.array([[1, 2, 3], [1, 2, 3], [1, 2, 3]], dtype=np.float32)
    valid = np.ones((3, 3), dtype=bool)
    flowdir = d8_flow_directions(dem, valid)
    # NEIGHBORS index 3 is (0,-1) = due west. Middle column drains west.
    assert flowdir[1, 1] == 3, flowdir[1, 1]
    # The west edge has no lower neighbour -> sink sentinel -1.
    assert flowdir[1, 0] == -1, flowdir[1, 0]


def test_d8_marks_invalid_as_sentinel():
    from paleo_hydrology import d8_flow_directions
    dem = np.array([[2, 1], [2, 1]], dtype=np.float32)
    valid = np.array([[True, False], [True, False]])  # right column is ocean
    flowdir = d8_flow_directions(dem, valid)
    assert flowdir[0, 1] == -1  # invalid cell
    assert flowdir[0, 0] == 4   # NEIGHBORS index 4 is (0,1) = east, into ocean


def test_accumulation_grows_downstream():
    from paleo_hydrology import d8_flow_directions, flow_accumulation
    # 1x4 ramp draining west: each cell collects everything east of it.
    dem = np.array([[4, 3, 2, 1]], dtype=np.float32)
    valid = np.ones((1, 4), dtype=bool)
    flowdir = d8_flow_directions(dem, valid)
    acc = flow_accumulation(flowdir, valid)
    # Every cell counts itself plus all upstream cells.
    assert acc.tolist() == [[1.0, 2.0, 3.0, 4.0]], acc.tolist()


def test_accumulation_confluence_sums_branches():
    from paleo_hydrology import d8_flow_directions, flow_accumulation
    # Two headwaters (top corners) flowing to a shared bottom-centre outlet.
    dem = np.array([[2, 9, 2], [9, 1, 9], [9, 0, 9]], dtype=np.float32)
    valid = np.array([[1, 0, 1], [0, 1, 0], [0, 1, 0]], dtype=bool)
    flowdir = d8_flow_directions(dem, valid)
    acc = flow_accumulation(flowdir, valid)
    # Outlet (2,1) receives both headwaters + the mid cell + itself = 4.
    assert acc[2, 1] == 4.0, acc[2, 1]


def test_trace_channels_returns_connected_path():
    from paleo_hydrology import d8_flow_directions, flow_accumulation, trace_channels
    dem = np.array([[4, 3, 2, 1]], dtype=np.float32)
    valid = np.ones((1, 4), dtype=bool)
    flowdir = d8_flow_directions(dem, valid)
    acc = flow_accumulation(flowdir, valid)
    # Threshold 2 keeps cells with accumulation >= 2 (the lower three cells).
    lines = trace_channels(flowdir, acc, valid, threshold=2.0)
    assert len(lines) == 1, lines
    path = lines[0]["cells"]
    # Path runs downstream as (row, col) pairs, head -> outlet.
    # dem [[4,3,2,1]] drains east: head at col 1 (acc=2), outlet at col 3 (acc=4).
    assert path[0] == (0, 1) and path[-1] in {(0, 2), (0, 3)}, path
    assert lines[0]["max_flow"] >= 3.0


def test_trace_channels_threshold_filters_short_branches():
    from paleo_hydrology import d8_flow_directions, flow_accumulation, trace_channels
    dem = np.array([[4, 3, 2, 1]], dtype=np.float32)
    valid = np.ones((1, 4), dtype=bool)
    flowdir = d8_flow_directions(dem, valid)
    acc = flow_accumulation(flowdir, valid)
    # A very high threshold keeps nothing.
    assert trace_channels(flowdir, acc, valid, threshold=99.0) == []


def test_simplify_drops_collinear_midpoints():
    from paleo_hydrology import simplify_polyline
    pts = [(0.0, 0.0), (1.0, 0.0001), (2.0, 0.0), (2.0, 5.0)]
    out = simplify_polyline(pts, tolerance=0.01)
    # The near-collinear midpoint at x=1 is removed; the corner at (2,0) stays.
    assert out[0] == (0.0, 0.0)
    assert out[-1] == (2.0, 5.0)
    assert (2.0, 0.0) in out
    assert (1.0, 0.0001) not in out


def test_simplify_keeps_endpoints_for_two_points():
    from paleo_hydrology import simplify_polyline
    pts = [(0.0, 0.0), (3.0, 4.0)]
    assert simplify_polyline(pts, tolerance=1.0) == pts


def run():
    test_fill_raises_interior_pit_to_pour_point()
    test_fill_leaves_monotone_slope_untouched()
    print("Task 1 fill_depressions: OK")
    test_d8_points_downhill_west_on_a_ramp()
    test_d8_marks_invalid_as_sentinel()
    print("Task 2 d8_flow_directions: OK")
    test_accumulation_grows_downstream()
    test_accumulation_confluence_sums_branches()
    print("Task 3 flow_accumulation: OK")
    test_trace_channels_returns_connected_path()
    test_trace_channels_threshold_filters_short_branches()
    print("Task 4 trace_channels: OK")
    test_simplify_drops_collinear_midpoints()
    test_simplify_keeps_endpoints_for_two_points()
    print("Task 5 simplify_polyline: OK")


if __name__ == "__main__":
    run()
