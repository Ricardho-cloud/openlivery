// The AI provider (must match backend app/services/providers.py).
//
// This fork talks to xAI Grok directly (https://api.x.ai/v1) with a single
// agency key. The registry id stays "openrouter" so existing routes and
// stored credentials keep working; the label, key URL and models are Grok.
// Models are grouped by cost/speed versus capability. The first recommended
// entry is preselected so an agent can never be created without a model.
// Any other xAI model id still works when typed.

export type ModelGroup = "fast" | "balanced" | "capable";

export type ModelOption = {
  id: string;
  label: string;
  group: ModelGroup;
  // Marks the provider's default. Exactly one per provider.
  recommended?: boolean;
};

export const PROVIDERS = [
  {
    id: "openrouter",
    label: "xAI Grok",
    keyPlaceholder: "xai-...",
    keyUrl: "https://console.x.ai/",
    models: [
      { id: "grok-4.6", label: "Grok 4.6", group: "capable", recommended: true },
      { id: "grok-4.5", label: "Grok 4.5", group: "capable" },
      { id: "grok-4.3", label: "Grok 4.3", group: "capable" },
      { id: "grok-4", label: "Grok 4", group: "capable" },
      { id: "grok-4-fast-reasoning", label: "Grok 4 Fast Reasoning", group: "balanced" },
      { id: "grok-4-fast-non-reasoning", label: "Grok 4 Fast", group: "fast" },
      { id: "grok-code-fast-1", label: "Grok Code Fast 1", group: "fast" },
      { id: "grok-3", label: "Grok 3", group: "balanced" },
      { id: "grok-3-mini", label: "Grok 3 Mini", group: "fast" },
    ] as const satisfies readonly ModelOption[],
  },
] as const;

export type ProviderId = (typeof PROVIDERS)[number]["id"];

export const DEFAULT_PROVIDER: ProviderId = "openrouter";

// Transcription models for the audio-recognition capability (OpenRouter's
// audio endpoint).
export const AUDIO_MODELS = ["grok-4.6", "grok-3"] as const;
export const DEFAULT_AUDIO_MODEL = AUDIO_MODELS[0];

// Embedding models for the knowledge base (mirrors the API catalog, used while
// it loads). Vectors from different models are not comparable, so changing an
// agent's model reindexes its documents.
export const EMBEDDING_MODELS = [
  "openai/text-embedding-3-small",
  "openai/text-embedding-3-large",
  "google/gemini-embedding-2",
  "qwen/qwen3-embedding-8b",
  "voyageai/voyage-4",
  "voyageai/voyage-4-lite",
  "mistralai/mistral-embed-2312",
] as const;
export const DEFAULT_EMBEDDING_MODEL = EMBEDDING_MODELS[0];

// Vision models for the image-recognition capability: any chat model that
// accepts images. DeepSeek is text-only, so it is left out.
export const IMAGE_MODELS = [
  "grok-4.6", "grok-4.5", "grok-4.3", "grok-4", "grok-3",
] as const;
export const DEFAULT_IMAGE_MODEL = "grok-4.6";

export function providerLabel(id: string): string {
  return PROVIDERS.find((p) => p.id === id)?.label ?? id;
}

// What the API's catalog says about every model OpenRouter serves, loaded by
// useAvailableModels. The static lists above are the seed: they keep the
// curated labels, tiers and the recommended default for the models we know,
// and everything else takes its name and context window from here.
export type LiveModel = { id: string; label: string; provider: string; context_window: number; output_price_per_1k: number };

let liveOptions: ModelOption[] = [];
const liveContext = new Map<string, number>();

// A tier from the list price, so a model the seed does not know still gets a
// tag in the picker.
function tierFor(outputPricePer1k: number): ModelGroup {
  if (outputPricePer1k < 0.002) return "fast";
  if (outputPricePer1k < 0.01) return "balanced";
  return "capable";
}

export function setLiveModels(models: LiveModel[]): void {
  const seeded = new Set<string>(PROVIDERS.flatMap((p) => p.models.map((m) => m.id)));
  liveOptions = models.filter((m) => !seeded.has(m.id)).map((m) => ({ id: m.id, label: m.label, group: tierFor(m.output_price_per_1k) }));
  liveContext.clear();
  for (const m of models) liveContext.set(m.id, m.context_window);
}

export function modelOptionsFor(id: string): readonly ModelOption[] {
  const seed: readonly ModelOption[] = PROVIDERS.find((p) => p.id === id)?.models ?? [];
  return id === DEFAULT_PROVIDER ? [...seed, ...liveOptions] : seed;
}

export function modelsFor(id: string): readonly string[] {
  return modelOptionsFor(id).map((model) => model.id);
}

export function defaultModelFor(id: string): string {
  const options = modelOptionsFor(id);
  return (options.find((model) => model.recommended) ?? options[0])?.id ?? "";
}

/** Human label for a model id, falling back to the id itself. */
export function modelLabel(id: string): string {
  return modelOptionsFor(DEFAULT_PROVIDER).find((model) => model.id === id)?.label ?? id;
}

// ~4 characters per token: same approximation as the backend, for the token
// counter in the agent creation wizard.
export function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

// Approximate context window (in tokens) per model family, used only for the
// "context window usage" bar. Values are representative, not exact.
export function modelContextWindow(id: string): number {
  // What OpenRouter reports for the model, once the catalog has loaded.
  const live = liveContext.get(id);
  if (live) return live;
  // Slugs are "vendor/model"; the family is readable from the model part.
  const name = id.includes("/") ? id.slice(id.indexOf("/") + 1) : id;
  // Haiku is the one current Claude model still on a 200k window; the rest of
  // the line-up is 1M, so the generic "claude" case must not assume 200k.
  if (name.startsWith("claude-haiku")) return 200_000;
  if (name.startsWith("claude")) return 1_000_000;
  if (name.startsWith("gpt-4.1")) return 1_000_000;
  if (name.startsWith("gpt-5.6") || name.startsWith("gpt-5.5")) return 1_000_000;
  if (name.startsWith("gpt-5")) return 400_000;
  if (name.startsWith("gemini") || name.startsWith("deepseek") || name.startsWith("llama")) return 1_000_000;
  if (name.startsWith("grok")) return 1_000_000;
  return 128_000;
}
