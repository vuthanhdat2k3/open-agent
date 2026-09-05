export interface CompanionConfig {
  name: string;
  tagline: string;
  brainAgentId: string | null;
  modelUrl: string;
  defaultPosition: "bottom-right" | "middle-right" | "top-right" | "bottom-left";
  avatarScale: number; // Scale percentage (60 - 130), default 85% for balanced aesthetics
  showThoughtBubbles: boolean;
  enableEmailTriage: boolean;
  enableApprovals: boolean;
  enableBriefings: boolean;
  enableDirectPrompt: boolean;
}

export const DEFAULT_COMPANION_CONFIG: CompanionConfig = {
  name: "Personal Operator",
  tagline: "Executive Chief of Staff",
  brainAgentId: null,
  modelUrl: "/agent-service-robot.glb",
  defaultPosition: "bottom-right",
  avatarScale: 85,
  showThoughtBubbles: true,
  enableEmailTriage: true,
  enableApprovals: true,
  enableBriefings: true,
  enableDirectPrompt: true,
};

export const COMPANION_SCALE_PRESETS = [
  { id: "compact", scale: 70, baseW: 133, baseH: 130 },
  { id: "standard", scale: 85, baseW: 162, baseH: 157 },
  { id: "default", scale: 100, baseW: 190, baseH: 185 },
  { id: "large", scale: 115, baseW: 219, baseH: 213 },
] as const;

// Display labels for these presets live in the consuming component (locale-aware via tx()).
export const AVATAR_3D_PRESETS = [
  { id: "service-robot", url: "/agent-service-robot.glb" },
  { id: "cyber-orb", url: "https://modelviewer.dev/shared-assets/models/Astronaut.glb" },
  { id: "custom", url: "" },
];

const STORAGE_KEY = "openagent_companion_config";

export function getCompanionConfig(): CompanionConfig {
  if (typeof window === "undefined") return DEFAULT_COMPANION_CONFIG;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_COMPANION_CONFIG;
    const parsed = JSON.parse(raw);
    return {
      ...DEFAULT_COMPANION_CONFIG,
      ...parsed,
      avatarScale: typeof parsed.avatarScale === "number" ? parsed.avatarScale : DEFAULT_COMPANION_CONFIG.avatarScale,
    };
  } catch {
    return DEFAULT_COMPANION_CONFIG;
  }
}

export function saveCompanionConfig(config: Partial<CompanionConfig>): CompanionConfig {
  if (typeof window === "undefined") return DEFAULT_COMPANION_CONFIG;
  try {
    const current = getCompanionConfig();
    const updated = { ...current, ...config };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    window.dispatchEvent(new Event("companion-config-updated"));
    return updated;
  } catch {
    return DEFAULT_COMPANION_CONFIG;
  }
}
