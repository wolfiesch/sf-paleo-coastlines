import { SimpleMeshLayer } from "deck.gl";

type NumericArray =
  | Float32Array
  | Float64Array
  | Int8Array
  | Uint8Array
  | Int16Array
  | Uint16Array
  | Int32Array
  | Uint32Array;

interface TerrainMeshAttribute {
  value: NumericArray;
  size: number;
}

interface TerrainMesh {
  attributes: Record<string, TerrainMeshAttribute>;
  indices?: TerrainMeshAttribute;
}

interface SmoothTerrainState {
  hasNormals?: boolean;
  hasSmoothedTerrainNormals?: boolean;
}

const TERRAIN_HEIGHT_SMOOTHING_STRENGTH = 0.18;

const smoothedMeshCache = new WeakMap<object, TerrainMesh>();

function attributeValue(attribute: TerrainMeshAttribute | undefined): NumericArray | undefined {
  return attribute?.value;
}

function vertexIndex(indices: NumericArray | undefined, fallback: number): number {
  return indices ? Number(indices[fallback]) : fallback;
}

function addNormal(
  normals: Float32Array,
  vertex: number,
  nx: number,
  ny: number,
  nz: number,
): void {
  const offset = vertex * 3;
  normals[offset] += nx;
  normals[offset + 1] += ny;
  normals[offset + 2] += nz;
}

function smoothedPositionAttribute(
  positions: NumericArray,
  positionSize: number,
  indices: NumericArray | undefined,
): TerrainMeshAttribute | null {
  if (!indices || positions.length < positionSize * 3) {
    return null;
  }

  const vertexCount = Math.floor(positions.length / positionSize);
  const triangleIndexCount = indices.length;
  const neighborHeightSums = new Float64Array(vertexCount);
  const neighborCounts = new Uint16Array(vertexCount);
  const smoothedPositions = new Float32Array(positions.length);
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;

  for (let vertex = 0; vertex < vertexCount; vertex += 1) {
    const offset = vertex * positionSize;
    const x = Number(positions[offset]);
    const y = Number(positions[offset + 1]);
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
    for (let component = 0; component < positionSize; component += 1) {
      smoothedPositions[offset + component] = Number(positions[offset + component]);
    }
  }

  const addNeighbor = (vertex: number, neighbor: number) => {
    if (vertex >= vertexCount || neighbor >= vertexCount) return;
    neighborHeightSums[vertex] += Number(positions[neighbor * positionSize + 2]);
    neighborCounts[vertex] += 1;
  };

  for (let i = 0; i <= triangleIndexCount - 3; i += 3) {
    const a = vertexIndex(indices, i);
    const b = vertexIndex(indices, i + 1);
    const c = vertexIndex(indices, i + 2);

    addNeighbor(a, b);
    addNeighbor(a, c);
    addNeighbor(b, a);
    addNeighbor(b, c);
    addNeighbor(c, a);
    addNeighbor(c, b);
  }

  const edgeTolerance = Math.max(maxX - minX, maxY - minY) * 1e-5;

  for (let vertex = 0; vertex < vertexCount; vertex += 1) {
    const count = neighborCounts[vertex];
    if (count === 0) continue;

    const offset = vertex * positionSize;
    const x = Number(positions[offset]);
    const y = Number(positions[offset + 1]);
    const isEdge =
      Math.abs(x - minX) <= edgeTolerance ||
      Math.abs(x - maxX) <= edgeTolerance ||
      Math.abs(y - minY) <= edgeTolerance ||
      Math.abs(y - maxY) <= edgeTolerance;

    if (isEdge) continue;

    const originalZ = Number(positions[offset + 2]);
    const neighborZ = neighborHeightSums[vertex] / count;
    smoothedPositions[offset + 2] =
      originalZ + (neighborZ - originalZ) * TERRAIN_HEIGHT_SMOOTHING_STRENGTH;
  }

  return { size: positionSize, value: smoothedPositions };
}

function smoothMesh(mesh: TerrainMesh): TerrainMesh {
  if (smoothedMeshCache.has(mesh)) {
    return smoothedMeshCache.get(mesh)!;
  }

  const attributes = mesh.attributes;
  const positionAttribute = attributes.POSITION ?? attributes.positions;
  const positions = attributeValue(positionAttribute);
  const positionSize = positionAttribute?.size ?? 3;

  if (!positions || positionSize < 3) {
    return mesh;
  }

  const vertexCount = Math.floor(positions.length / positionSize);
  const indices = attributeValue(mesh.indices);
  const triangleIndexCount = indices?.length ?? vertexCount;

  if (vertexCount < 3 || triangleIndexCount < 3) {
    return mesh;
  }

  const smoothedPosition = smoothedPositionAttribute(positions, positionSize, indices);
  const normalPositions = smoothedPosition?.value ?? positions;
  const normals = new Float32Array(vertexCount * 3);

  for (let i = 0; i <= triangleIndexCount - 3; i += 3) {
    const a = vertexIndex(indices, i);
    const b = vertexIndex(indices, i + 1);
    const c = vertexIndex(indices, i + 2);

    if (a >= vertexCount || b >= vertexCount || c >= vertexCount) {
      continue;
    }

    const ax = Number(normalPositions[a * positionSize]);
    const ay = Number(normalPositions[a * positionSize + 1]);
    const az = Number(normalPositions[a * positionSize + 2]);
    const bx = Number(normalPositions[b * positionSize]);
    const by = Number(normalPositions[b * positionSize + 1]);
    const bz = Number(normalPositions[b * positionSize + 2]);
    const cx = Number(normalPositions[c * positionSize]);
    const cy = Number(normalPositions[c * positionSize + 1]);
    const cz = Number(normalPositions[c * positionSize + 2]);

    const abx = bx - ax;
    const aby = by - ay;
    const abz = bz - az;
    const acx = cx - ax;
    const acy = cy - ay;
    const acz = cz - az;

    const nx = aby * acz - abz * acy;
    const ny = abz * acx - abx * acz;
    const nz = abx * acy - aby * acx;
    const length = Math.hypot(nx, ny, nz);

    if (length === 0) {
      continue;
    }

    addNormal(normals, a, nx / length, ny / length, nz / length);
    addNormal(normals, b, nx / length, ny / length, nz / length);
    addNormal(normals, c, nx / length, ny / length, nz / length);
  }

  for (let i = 0; i < normals.length; i += 3) {
    const nx = normals[i];
    const ny = normals[i + 1];
    const nz = normals[i + 2];
    const length = Math.hypot(nx, ny, nz);

    if (length > 0) {
      normals[i] = nx / length;
      normals[i + 1] = ny / length;
      normals[i + 2] = nz / length;
    } else {
      normals[i + 2] = 1;
    }
  }

  const normalAttribute = { size: 3, value: normals };
  const smoothedMesh = {
    ...mesh,
    attributes: {
      ...attributes,
      ...(smoothedPosition ? { POSITION: smoothedPosition, positions: smoothedPosition } : {}),
      NORMAL: normalAttribute,
      normals: normalAttribute,
    },
  };

  smoothedMeshCache.set(mesh, smoothedMesh);
  return smoothedMesh;
}

export class SmoothTerrainMeshLayer<DataT = unknown> extends SimpleMeshLayer<DataT> {
  protected getModel(mesh: TerrainMesh) {
    const smoothedMesh = smoothMesh(mesh);
    (this.state as SmoothTerrainState).hasSmoothedTerrainNormals = smoothedMesh !== mesh;
    return super.getModel(smoothedMesh);
  }

  draw(params: Parameters<SimpleMeshLayer<DataT>["draw"]>[0]) {
    const state = this.state as SmoothTerrainState;
    if (state.hasSmoothedTerrainNormals) {
      state.hasNormals = true;
    }
    super.draw(params);
  }
}
