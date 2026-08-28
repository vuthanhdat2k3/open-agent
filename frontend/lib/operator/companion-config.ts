export interface CompanionConfig {
  name: string;
  tagline: string;
  brainAgentId: string | null;
  modelUrl: string;
  defaultPosition: "bottom-right" | "middle-right" | "top-right" | "bottom-left";
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
  showThoughtBubbles: true,
  enableEmailTriage: true,
  enableApprovals: true,
  enableBriefings: true,
  enableDirectPrompt: true,
};

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
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_COMPANION_CONFIG;
    return { ...DEFAULT_COMPANION_CONFIG, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_COMPANION_CONFIG;
  }
}

export function saveCompanionConfig(config: Partial<CompanionConfig>): CompanionConfig {
  if (typeof window === "undefined") return DEFAULT_COMPANION_CONFIG;
  try {
    const current = getCompanionConfig();
    const updated = { ...current, ...config };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    window.dispatchEvent(new Event("companion-config-updated"));
    return updated;
  } catch {
    return DEFAULT_COMPANION_CONFIG;
  }
}
