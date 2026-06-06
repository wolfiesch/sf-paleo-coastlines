import { LayerExtension, type Layer } from "deck.gl";

interface TerrainRevealProps {
  terrainRevealBandMeters?: number;
  terrainRevealEnabled?: boolean;
  terrainRevealStrength?: number;
  terrainRevealSubmergedStrength?: number;
  terrainRevealWaterLevelZ?: number;
}

const terrainRevealModule = {
  name: "terrainReveal",
  vs: /* glsl */ `
layout(std140) uniform terrainRevealUniforms {
  float enabled;
  float waterLevelZ;
  float bandMeters;
  float strength;
  float submergedStrength;
} terrainReveal;

out float terrainReveal_heightZ;
`,
  fs: /* glsl */ `
layout(std140) uniform terrainRevealUniforms {
  float enabled;
  float waterLevelZ;
  float bandMeters;
  float strength;
  float submergedStrength;
} terrainReveal;

in float terrainReveal_heightZ;
`,
  inject: {
    "vs:DECKGL_FILTER_GL_POSITION": /* glsl */ `
      terrainReveal_heightZ = geometry.worldPosition.z;
    `,
    "fs:DECKGL_FILTER_COLOR": /* glsl */ `
      if (terrainReveal.enabled > 0.5) {
        float aboveWater = smoothstep(terrainReveal.waterLevelZ - 0.4, terrainReveal.waterLevelZ + 1.2, terrainReveal_heightZ);
        float nearWaterline = 1.0 - smoothstep(
          terrainReveal.waterLevelZ + 2.0,
          terrainReveal.waterLevelZ + max(terrainReveal.bandMeters, 3.0),
          terrainReveal_heightZ
        );
        float reveal = clamp(aboveWater * nearWaterline * terrainReveal.strength, 0.0, 0.78);
        vec3 exposedTint = vec3(1.0, 0.78, 0.30);
        color.rgb = mix(color.rgb, exposedTint, reveal);

        float belowWater = 1.0 - smoothstep(terrainReveal.waterLevelZ - 1.2, terrainReveal.waterLevelZ + 0.2, terrainReveal_heightZ);
        float nearSubmerged = smoothstep(
          terrainReveal.waterLevelZ - max(terrainReveal.bandMeters * 0.65, 3.0),
          terrainReveal.waterLevelZ - 1.0,
          terrainReveal_heightZ
        );
        float submerged = clamp(belowWater * nearSubmerged * terrainReveal.submergedStrength, 0.0, 0.48);
        vec3 submergedTint = vec3(0.08, 0.58, 0.72);
        color.rgb = mix(color.rgb, submergedTint, submerged);
      }
    `,
  },
  getUniforms: (props?: TerrainRevealProps) => ({
    enabled: props?.terrainRevealEnabled ? 1 : 0,
    waterLevelZ: props?.terrainRevealWaterLevelZ ?? -480,
    bandMeters: props?.terrainRevealBandMeters ?? 40,
    strength: props?.terrainRevealStrength ?? 0.34,
    submergedStrength: props?.terrainRevealSubmergedStrength ?? 0.18,
  }),
  uniformTypes: {
    enabled: "f32",
    waterLevelZ: "f32",
    bandMeters: "f32",
    strength: "f32",
    submergedStrength: "f32",
  },
};

export class TerrainRevealExtension extends LayerExtension {
  static extensionName = "TerrainRevealExtension";
  static defaultProps = {
    terrainRevealBandMeters: 40,
    terrainRevealEnabled: true,
    terrainRevealStrength: 0.34,
    terrainRevealSubmergedStrength: 0.18,
    terrainRevealWaterLevelZ: 0,
  };

  getShaders() {
    return {
      modules: [terrainRevealModule],
    };
  }

  draw(this: Layer) {
    const props = this.props as TerrainRevealProps;
    this.setShaderModuleProps({
      terrainReveal: {
        terrainRevealBandMeters: props.terrainRevealBandMeters,
        terrainRevealEnabled: props.terrainRevealEnabled,
        terrainRevealStrength: props.terrainRevealStrength,
        terrainRevealSubmergedStrength: props.terrainRevealSubmergedStrength,
        terrainRevealWaterLevelZ: props.terrainRevealWaterLevelZ,
      },
    });
  }
}

export const terrainRevealExtension = new TerrainRevealExtension();
