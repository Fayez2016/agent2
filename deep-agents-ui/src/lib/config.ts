export interface StandaloneConfig {
  deploymentUrl: string;
  assistantId: string;
  langsmithApiKey?: string;
}

const CONFIG_KEY = "deep-agent-config";

export function getConfig(): StandaloneConfig | null {
  if (typeof window === "undefined") return null;

  const defaultVal: StandaloneConfig = {
    deploymentUrl: "http://localhost:8123",
    assistantId: "linux_operator",
  };

  const stored = localStorage.getItem(CONFIG_KEY);
  if (!stored) return defaultVal;

  try {
    const parsed = JSON.parse(stored);
    return {
      deploymentUrl: parsed.deploymentUrl || defaultVal.deploymentUrl,
      assistantId: parsed.assistantId || defaultVal.assistantId,
      langsmithApiKey: parsed.langsmithApiKey,
    };
  } catch {
    return defaultVal;
  }
}

export function saveConfig(config: StandaloneConfig): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(CONFIG_KEY, JSON.stringify(config));
}
