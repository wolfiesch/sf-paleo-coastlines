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

function smoothMeshNormals(mesh: TerrainMesh): TerrainMesh {
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

  const normals = new Float32Array(vertexCount * 3);

  for (let i = 0; i <= triangleIndexCount - 3; i += 3) {
    const a = vertexIndex(indices, i);
    const b = vertexIndex(indices, i + 1);
    const c = vertexIndex(indices, i + 2);

    if (a >= vertexCount || b >= vertexCount || c >= vertexCount) {
      continue;
    }

    const ax = Number(positions[a * positionSize]);
    const ay = Number(positions[a * positionSize + 1]);
    const az = Number(positions[a * positionSize + 2]);
    const bx = Number(positions[b * positionSize]);
    const by = Number(positions[b * positionSize + 1]);
    const bz = Number(positions[b * positionSize + 2]);
    const cx = Number(positions[c * positionSize]);
    const cy = Number(positions[c * positionSize + 1]);
    const cz = Number(positions[c * positionSize + 2]);

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
      NORMAL: normalAttribute,
      normals: normalAttribute,
    },
  };

  smoothedMeshCache.set(mesh, smoothedMesh);
  return smoothedMesh;
}

export class SmoothTerrainMeshLayer<DataT = unknown> extends SimpleMeshLayer<DataT> {
  protected getModel(mesh: TerrainMesh) {
    const smoothedMesh = smoothMeshNormals(mesh);
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
