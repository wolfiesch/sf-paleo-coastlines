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

interface SmoothTerrainMeshProps {
  terrainSmoothHeights?: boolean;
}

const TERRAIN_HEIGHT_SMOOTHING_STRENGTH = 0.16;
const TERRAIN_HEIGHT_SMOOTHING_PASSES = 2;

const sharpMeshCache = new WeakMap<object, TerrainMesh>();
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
  const neighborIndices: number[][] = Array.from({ length: vertexCount }, () => []);
  const smoothedPositions = new Float32Array(positions.length);
  const workingHeights = new Float64Array(vertexCount);
  const nextHeights = new Float64Array(vertexCount);
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
    workingHeights[vertex] = Number(positions[offset + 2]);
  }

  const addNeighbor = (vertex: number, neighbor: number) => {
    if (vertex >= vertexCount || neighbor >= vertexCount) return;
    neighborIndices[vertex].push(neighbor);
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
  const edgeVertices = new Uint8Array(vertexCount);

  for (let vertex = 0; vertex < vertexCount; vertex += 1) {
    const offset = vertex * positionSize;
    const x = Number(positions[offset]);
    const y = Number(positions[offset + 1]);
    edgeVertices[vertex] =
      Math.abs(x - minX) <= edgeTolerance ||
      Math.abs(x - maxX) <= edgeTolerance ||
      Math.abs(y - minY) <= edgeTolerance ||
      Math.abs(y - maxY) <= edgeTolerance
        ? 1
        : 0;
  }

  for (let pass = 0; pass < TERRAIN_HEIGHT_SMOOTHING_PASSES; pass += 1) {
    nextHeights.set(workingHeights);
    for (let vertex = 0; vertex < vertexCount; vertex += 1) {
      const neighbors = neighborIndices[vertex];
      if (edgeVertices[vertex] || neighbors.length === 0) continue;

      let neighborHeightSum = 0;
      for (const neighbor of neighbors) {
        neighborHeightSum += workingHeights[neighbor];
      }

      const neighborZ = neighborHeightSum / neighbors.length;
      nextHeights[vertex] =
        workingHeights[vertex] + (neighborZ - workingHeights[vertex]) * TERRAIN_HEIGHT_SMOOTHING_STRENGTH;
    }
    workingHeights.set(nextHeights);
  }

  for (let vertex = 0; vertex < vertexCount; vertex += 1) {
    smoothedPositions[vertex * positionSize + 2] = workingHeights[vertex];
  }

  return { size: positionSize, value: smoothedPositions };
}

function smoothMesh(mesh: TerrainMesh, smoothHeights: boolean): TerrainMesh {
  const cache = smoothHeights ? smoothedMeshCache : sharpMeshCache;
  if (cache.has(mesh)) {
    return cache.get(mesh)!;
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

  const smoothedPosition = smoothHeights ? smoothedPositionAttribute(positions, positionSize, indices) : null;
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
    if (nx === 0 && ny === 0 && nz === 0) {
      continue;
    }

    addNormal(normals, a, nx, ny, nz);
    addNormal(normals, b, nx, ny, nz);
    addNormal(normals, c, nx, ny, nz);
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

  cache.set(mesh, smoothedMesh);
  return smoothedMesh;
}

export class SmoothTerrainMeshLayer<DataT = unknown> extends SimpleMeshLayer<DataT> {
  protected getModel(mesh: TerrainMesh) {
    const props = this.props as SmoothTerrainMeshProps;
    const smoothedMesh = smoothMesh(mesh, props.terrainSmoothHeights ?? true);
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
