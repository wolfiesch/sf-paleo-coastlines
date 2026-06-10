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
        float gradientSize = length(heightGradient);
        float slope = smoothstep(0.02, 1.45, gradientSize * 0.08);
        vec2 softenedGradient = heightGradient / (1.0 + gradientSize * 0.28);
        vec3 reliefNormal = normalize(vec3(-softenedGradient.x * 0.045, -softenedGradient.y * 0.045, 1.0));
        vec3 reliefLight = normalize(vec3(-0.48, 0.38, 0.78));
        float reliefShade = dot(reliefNormal, reliefLight);
        float reliefContrast = clamp((reliefShade - 0.62) * 1.85, -0.34, 0.42);
        color.rgb *= 1.0 + reliefContrast * slope * terrainReveal.reliefStrength;
        color.rgb += vec3(0.055, 0.06, 0.05) * slope * terrainReveal.reliefStrength;

        float aboveWater = smoothstep(terrainReveal.waterLevelZ - 0.4, terrainReveal.waterLevelZ + 1.2, terrainReveal_heightZ);
        float nearWaterline = 1.0 - smoothstep(
          terrainReveal.waterLevelZ + 1.0,
          terrainReveal.waterLevelZ + max(terrainReveal.bandMeters * 1.25, 4.0),
          terrainReveal_heightZ
        );

        // Hypsometric land ramp keyed to height above the active waterline.
        // Heights are display meters (real meters x ~4 exaggeration x scene
        // scale), so 110 here is roughly 20 real meters: wet sand at the
        // fresh shoreline, lowland olive, upland brown, pale rock on crests.
        float landHeight = max(terrainReveal_heightZ - terrainReveal.waterLevelZ, 0.0);
        vec3 landRamp = mix(vec3(0.84, 0.74, 0.50), vec3(0.55, 0.56, 0.33), smoothstep(8.0, 110.0, landHeight));
        landRamp = mix(landRamp, vec3(0.47, 0.37, 0.24), smoothstep(110.0, 430.0, landHeight));
        landRamp = mix(landRamp, vec3(0.62, 0.57, 0.47), smoothstep(430.0, 1100.0, landHeight));

        // Preserve the texture's luminance so survey/relief detail keeps
        // reading through the tint instead of being painted over.
        float landLuma = dot(color.rgb, vec3(0.299, 0.587, 0.114));
        vec3 exposedColor = landRamp * (0.55 + landLuma * 0.75);

        // Full strength in the freshly exposed band near the waterline,
        // easing to a gentler hypsometric wash on land well above it.
        float reveal = clamp(aboveWater * (0.38 + 0.62 * nearWaterline) * terrainReveal.strength, 0.0, 0.88);
        color.rgb = mix(color.rgb, exposedColor, reveal);

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
