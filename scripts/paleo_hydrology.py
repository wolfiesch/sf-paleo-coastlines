"""Pure numpy hydrology for paleo-drainage extraction. No file IO here."""
from __future__ import annotations

import heapq
from collections import deque

import numpy as np

__all__ = [
    "fill_depressions",
    "d8_flow_directions",
    "flow_accumulation",
    "trace_channels",
    "simplify_polyline",
]

# 8-neighbour offsets and their planar distances (diagonals = sqrt(2)).
NEIGHBORS: list[tuple[int, int]] = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
NEIGHBOR_DIST = np.array([2 ** 0.5, 1.0, 2 ** 0.5, 1.0, 1.0, 2 ** 0.5, 1.0, 2 ** 0.5], dtype=np.float64)

# Type alias for 2-D float points used by simplify_polyline.
Point = tuple[float, float]


def fill_depressions(dem: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Priority-flood depression filling (Barnes 2014).

    Invalid cells (ocean below the lowstand, or nodata) act as the outer ocean
    that every valid cell ultimately spills toward. Returns a filled copy where
    no valid cell sits below its lowest spill path. Never lowers terrain.
    """
    rows, cols = dem.shape
    filled = dem.astype(np.float64, copy=True)
    closed = ~valid  # invalid cells are treated as already-resolved outlets

    # Seed the queue with every valid cell on the array border or adjacent to an
    # invalid (ocean) cell: these can drain straight out.
    border = np.zeros((rows, cols), dtype=bool)
    border[0, :] = border[-1, :] = border[:, 0] = border[:, -1] = True
    invalid = ~valid
    adj_invalid = np.zeros((rows, cols), dtype=bool)
    adj_invalid[:-1, :] |= invalid[1:, :]
    adj_invalid[1:, :] |= invalid[:-1, :]
    adj_invalid[:, :-1] |= invalid[:, 1:]
    adj_invalid[:, 1:] |= invalid[:, :-1]
    adj_invalid[:-1, :-1] |= invalid[1:, 1:]
    adj_invalid[1:, 1:] |= invalid[:-1, :-1]
    adj_invalid[:-1, 1:] |= invalid[1:, :-1]
    adj_invalid[1:, :-1] |= invalid[:-1, 1:]
    seed = valid & (border | adj_invalid)

    heap: list[tuple[float, int, int]] = []
    seed_rows, seed_cols = np.nonzero(seed)
    for r, c in zip(seed_rows.tolist(), seed_cols.tolist()):
        heapq.heappush(heap, (float(filled[r, c]), r, c))
        closed[r, c] = True

    while heap:
        elev, r, c = heapq.heappop(heap)
        for dr, dc in NEIGHBORS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and not closed[nr, nc]:
                ne = filled[nr, nc] if filled[nr, nc] > elev else elev
                filled[nr, nc] = ne
                closed[nr, nc] = True
                heapq.heappush(heap, (ne, nr, nc))

    return filled.astype(np.float32)


def d8_flow_directions(filled: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Steepest-descent D8 direction per cell.

    Returns an int8 array of NEIGHBORS indices (0..7), or -1 for invalid cells
    and for valid cells with no lower neighbour (pits/flat sinks). A valid cell
    bordering an invalid (ocean) cell drains into it if that is the steepest drop.
    """
    rows, cols = filled.shape
    elev = filled.astype(np.float64)
    # Padding lets us compute all 8 neighbour drops without per-edge branching.
    padded = np.pad(elev, 1, mode="constant", constant_values=np.inf)
    best_slope = np.zeros((rows, cols), dtype=np.float64)
    best_dir = np.full((rows, cols), -1, dtype=np.int8)

    for k, (dr, dc) in enumerate(NEIGHBORS):
        neighbor = padded[1 + dr:1 + dr + rows, 1 + dc:1 + dc + cols]
        slope = (elev - neighbor) / NEIGHBOR_DIST[k]
        take = slope > best_slope
        best_slope[take] = slope[take]
        best_dir[take] = k

    best_dir[~valid] = -1
    best_dir[valid & (best_slope <= 0.0)] = -1
    return best_dir


def flow_accumulation(flowdir: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Number of upstream cells draining through each cell (self-inclusive).

    Each valid cell starts with a count of 1 and pushes its running total to its
    single D8 downstream neighbour. Kahn's algorithm gives the exact processing
    order over the acyclic D8 graph: a cell is only consumed once all of its
    upstream contributors (its in-degree) have been processed, so its total is
    final before it is pushed downstream.
    """
    rows, cols = flowdir.shape
    acc = valid.astype(np.float64)

    # Downstream target (row, col) for each cell, or (-1,-1) if it is a sink.
    dr = np.full((rows, cols), -1, dtype=np.int64)
    dc = np.full((rows, cols), -1, dtype=np.int64)
    rr, cc = np.meshgrid(np.arange(rows), np.arange(cols), indexing="ij")
    for k, (ndr, ndc) in enumerate(NEIGHBORS):
        sel = flowdir == k
        tr = rr[sel] + ndr
        tc = cc[sel] + ndc
        dr[sel] = tr
        dc[sel] = tc

    # In-degree: how many cells flow into each cell. Kahn's topological order.
    indeg = np.zeros((rows, cols), dtype=np.int64)
    has_down = dr >= 0
    np.add.at(indeg, (dr[has_down], dc[has_down]), 1)

    queue = deque(zip(*np.nonzero((indeg == 0) & valid)))
    while queue:
        r, c = queue.popleft()
        tr, tc = int(dr[r, c]), int(dc[r, c])
        if tr < 0:
            continue  # sink: flows into ocean / out of grid
        acc[tr, tc] += acc[r, c]
        indeg[tr, tc] -= 1
        if indeg[tr, tc] == 0 and valid[tr, tc]:
            queue.append((tr, tc))

    return acc.astype(np.float32)


def trace_channels(
    flowdir: np.ndarray,
    acc: np.ndarray,
    valid: np.ndarray,
    threshold: float,
) -> list[dict]:
    """Trace accumulation-thresholded channels into downstream polylines.

    A channel cell is a valid cell with acc >= threshold. A head is a channel
    cell with no channel cell flowing into it. From each head we walk D8
    downstream until leaving the channel, hitting an ocean sink, or reaching a
    cell already part of an emitted path (so trunks join visually). Returns a
    list of {"cells": [(r,c), ...], "max_flow": float}.
    """
    rows, cols = flowdir.shape
    channel = valid & (acc >= threshold)
    if not channel.any():
        return []

    # Mark channel cells that receive inflow from another channel cell.
    receives_inflow = np.zeros((rows, cols), dtype=bool)
    for k, (dr, dc) in enumerate(NEIGHBORS):
        src = channel & (flowdir == k)
        sr, sc = np.nonzero(src)
        tr, tc = sr + dr, sc + dc
        inb = (tr >= 0) & (tr < rows) & (tc >= 0) & (tc < cols)
        receives_inflow[tr[inb], tc[inb]] |= channel[tr[inb], tc[inb]]

    heads = channel & ~receives_inflow
    visited = np.zeros((rows, cols), dtype=bool)
    lines: list[dict] = []

    head_cells = sorted(
        zip(*np.nonzero(heads)),
        key=lambda rc: -float(acc[rc[0], rc[1]]),
    )
    for r0, c0 in head_cells:
        path: list[tuple[int, int]] = [(int(r0), int(c0))]
        max_flow = float(acc[r0, c0])
        r, c = int(r0), int(c0)
        steps = 0
        while steps < rows * cols:
            steps += 1
            k = int(flowdir[r, c])
            if k < 0:
                break
            nr, nc = r + NEIGHBORS[k][0], c + NEIGHBORS[k][1]
            if not (0 <= nr < rows and 0 <= nc < cols) or not channel[nr, nc]:
                break
            path.append((nr, nc))
            max_flow = max(max_flow, float(acc[nr, nc]))
            if visited[nr, nc]:
                break  # joined an existing trunk; stop to avoid duplication
            r, c = nr, nc
        for rc in path:
            visited[rc[0], rc[1]] = True
        if len(path) >= 2:
            lines.append({"cells": path, "max_flow": max_flow})

    return lines


def simplify_polyline(points: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    """Iterative Douglas-Peucker. `points` are (x, y); endpoints are preserved."""
    if len(points) <= 2:
        return list(points)

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        ax, ay = points[start]
        bx, by = points[end]
        dx, dy = bx - ax, by - ay
        seg_len = (dx * dx + dy * dy) ** 0.5
        max_dist = -1.0
        index = -1
        for i in range(start + 1, end):
            px, py = points[i]
            if seg_len == 0.0:
                dist = ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
            else:
                dist = abs(dy * px - dx * py + bx * ay - by * ax) / seg_len
            if dist > max_dist:
                max_dist = dist
                index = i
        if max_dist > tolerance and index != -1:
            keep[index] = True
            stack.append((start, index))
            stack.append((index, end))

    return [points[i] for i in range(len(points)) if keep[i]]
