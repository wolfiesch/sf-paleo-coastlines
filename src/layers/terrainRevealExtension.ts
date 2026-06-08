import { LayerExtension, type Layer } from "deck.gl";

interface TerrainRevealProps {
  terrainRevealBandMeters?: number;
  terrainRevealDepthFogStrength?: number;
  terrainRevealEnabled?: boolean;
  terrainRevealReliefStrength?: number;
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
  float depthFogStrength;
  float reliefStrength;
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
  float depthFogStrength;
  float reliefStrength;
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
      if (color.a < 0.05) {
        discard;
      }

      if (terrainReveal.enabled > 0.5) {
        vec2 heightGradient = vec2(dFdx(terrainReveal_heightZ), dFdy(terrainReveal_heightZ));
        float slope = clamp(length(heightGradient) * 0.12, 0.0, 1.0);
        vec3 reliefNormal = normalize(vec3(-heightGradient.x * 0.08, -heightGradient.y * 0.08, 1.0));
        vec3 reliefLight = normalize(vec3(-0.58, 0.46, 0.68));
        float reliefShade = dot(reliefNormal, reliefLight);
        float reliefContrast = clamp((reliefShade - 0.54) * 2.85, -0.58, 0.72);
        color.rgb *= 1.0 + reliefContrast * slope * terrainReveal.reliefStrength;
        color.rgb += vec3(0.09, 0.10, 0.085) * slope * terrainReveal.reliefStrength;

        float aboveWater = smoothstep(terrainReveal.waterLevelZ - 0.4, terrainReveal.waterLevelZ + 1.2, terrainReveal_heightZ);
        float nearWaterline = 1.0 - smoothstep(
          terrainReveal.waterLevelZ + 1.0,
          terrainReveal.waterLevelZ + max(terrainReveal.bandMeters * 1.25, 4.0),
          terrainReveal_heightZ
        );
        float reveal = clamp(aboveWater * nearWaterline * terrainReveal.strength, 0.0, 0.88);
        vec3 exposedTint = vec3(1.0, 0.76, 0.24);
        color.rgb = mix(color.rgb, exposedTint, reveal);

        float belowWater = 1.0 - smoothstep(terrainReveal.waterLevelZ - 1.2, terrainReveal.waterLevelZ + 0.2, terrainReveal_heightZ);
        float nearSubmerged = smoothstep(
          terrainReveal.waterLevelZ - max(terrainReveal.bandMeters * 0.9, 4.0),
          terrainReveal.waterLevelZ - 1.0,
          terrainReveal_heightZ
        );
        float submerged = clamp(belowWater * nearSubmerged * terrainReveal.submergedStrength, 0.0, 0.58);
        vec3 submergedTint = vec3(0.04, 0.48, 0.68);
        color.rgb = mix(color.rgb, submergedTint, submerged);

        float depthBelowWater = max(terrainReveal.waterLevelZ - terrainReveal_heightZ, 0.0);
        float depthFog = smoothstep(20.0, 190.0, depthBelowWater);
        vec3 deepWaterTint = vec3(0.01, 0.11, 0.22);
        color.rgb = mix(color.rgb, deepWaterTint, clamp(depthFog * terrainReveal.depthFogStrength, 0.0, 0.42));
      }
    `,
  },
  getUniforms: (props?: TerrainRevealProps) => ({
    enabled: props?.terrainRevealEnabled ? 1 : 0,
    waterLevelZ: props?.terrainRevealWaterLevelZ ?? -480,
    bandMeters: props?.terrainRevealBandMeters ?? 40,
    depthFogStrength: props?.terrainRevealDepthFogStrength ?? 0.12,
    reliefStrength: props?.terrainRevealReliefStrength ?? 0.22,
    strength: props?.terrainRevealStrength ?? 0.34,
    submergedStrength: props?.terrainRevealSubmergedStrength ?? 0.18,
  }),
  uniformTypes: {
    enabled: "f32",
    waterLevelZ: "f32",
    bandMeters: "f32",
    depthFogStrength: "f32",
    reliefStrength: "f32",
    strength: "f32",
    submergedStrength: "f32",
  },
};

export class TerrainRevealExtension extends LayerExtension {
  static extensionName = "TerrainRevealExtension";
  static defaultProps = {
    terrainRevealBandMeters: 40,
    terrainRevealDepthFogStrength: 0.12,
    terrainRevealEnabled: true,
    terrainRevealReliefStrength: 0.22,
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
        terrainRevealDepthFogStrength: props.terrainRevealDepthFogStrength,
        terrainRevealEnabled: props.terrainRevealEnabled,
        terrainRevealReliefStrength: props.terrainRevealReliefStrength,
        terrainRevealStrength: props.terrainRevealStrength,
        terrainRevealSubmergedStrength: props.terrainRevealSubmergedStrength,
        terrainRevealWaterLevelZ: props.terrainRevealWaterLevelZ,
      },
    });
  }
}

export const terrainRevealExtension = new TerrainRevealExtension();
