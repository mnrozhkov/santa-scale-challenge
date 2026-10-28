import { operatorHeaders } from "./access";

export type Step = {
  role: string;
  model: string;
  fallback: boolean;
  ms: number;
};

export type WallItem = {
  id: string;
  name: string;
  age: number;
  wish: string;
  gift?: string;
  mood: string;
  city: string;
  tags: string[];
  has_video: boolean;
  png_url: string | null;
  video_url: string | null;
  model?: string;
};

export type WallResponse = {
  cards: string[];
  videos: string[];
  items: WallItem[];
  summary: Record<string, unknown> | null;
  counter: number | null;
};

export type CardResponse = {
  card: {
    kid_id: string;
    recommendation: { gifts: string[] };
    wish: { text: string; mood: string };
    image: { model_version?: string };
  };
  steps: Step[];
  png_url: string | null;
  html_url: string | null;
  kid?: { id: string; name: string; age: number; wishlist: string[] };
};

export type CardProgressEvent =
  | { type: "active"; node: string }
  | { type: "step"; step: Step }
  | { type: "done"; node: string; status?: string; meta?: string }
  | ({ type: "complete" } & CardResponse)
  | { type: "error"; detail: string };

export type KidRow = {
  id: string;
  name: string;
  age: number;
  wishlist: string[];
};

export type RunJob = {
  job_id: string;
  chunk: string;
  ids: string[];
  state?: string;
};

export type RunResponse = {
  run_id: string;
  kids: string[];
  jobs: RunJob[];
  waiting?: boolean;
  summary?: {
    totals?: {
      done?: number;
      skipped?: number;
      failed?: number;
      run_s?: number;
      cost_usd?: number;
      on_demand_cost_usd?: number;
    };
    savings_usd?: number;
  } | null;
};

function yieldFrame(): Promise<void> {
  return new Promise((resolve) => {
    requestAnimationFrame(() => resolve());
  });
}

async function readError(resp: Response): Promise<string> {
  const text = await resp.text();
  try {
    const data = JSON.parse(text) as { detail?: unknown };
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail
        .map((item) => (typeof item === "object" && item && "msg" in item ? String(item.msg) : String(item)))
        .join("; ");
    }
  } catch {
    /* raw text */
  }
  return text || `${resp.status} ${resp.statusText}`;
}

export async function fetchWall(): Promise<WallResponse> {
  const resp = await fetch("/api/wall");
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json() as Promise<WallResponse>;
}

export async function createCard(body: {
  name: string;
  age: number;
  wishlist: string[];
}): Promise<CardResponse> {
  const resp = await fetch("/api/cards", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json() as Promise<CardResponse>;
}

export async function createCardStream(
  body: { name: string; age: number; wishlist: string[] },
  onEvent: (event: CardProgressEvent) => void,
): Promise<CardResponse> {
  const resp = await fetch("/api/cards/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(await readError(resp));
  if (!resp.body) throw new Error("Empty stream body");

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let complete: CardResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      const event = JSON.parse(line.slice(6)) as CardProgressEvent;
      if (event.type === "error") throw new Error(event.detail);
      if (event.type === "complete") {
        complete = event;
        continue;
      }
      onEvent(event);
      await yieldFrame();
    }
  }

  if (!complete) throw new Error("Stream ended without a complete event");
  return complete;
}

export async function animateCard(kidId: string): Promise<{ id: string; video_url: string }> {
  const resp = await fetch(`/api/cards/${encodeURIComponent(kidId)}/animate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...operatorHeaders() },
    body: JSON.stringify({ mood_bank: true }),
  });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json() as Promise<{ id: string; video_url: string }>;
}

export async function fetchKids(limit = 20): Promise<KidRow[]> {
  const resp = await fetch(`/api/kids?limit=${limit}`);
  if (!resp.ok) throw new Error(await readError(resp));
  const data = (await resp.json()) as { kids: KidRow[] };
  return data.kids;
}

export async function submitRun(jobs = 4): Promise<RunResponse> {
  const resp = await fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...operatorHeaders() },
    body: JSON.stringify({ jobs }),
  });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json() as Promise<RunResponse>;
}

export async function fetchRun(runId: string): Promise<RunResponse> {
  const resp = await fetch(`/api/runs/${encodeURIComponent(runId)}`, {
    headers: operatorHeaders(),
  });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json() as Promise<RunResponse>;
}

export type AgentStreamEvent = Record<string, unknown> & {
  type?: string;
  event?: string;
  detail?: string;
  report?: Record<string, unknown>;
};

export async function runAgentStream(
  body: {
    kids?: Array<{ id?: string; name: string; age: number; wishlist?: string[] }>;
    limit?: number;
    budget_usd?: number;
    publish?: boolean;
  },
  onEvent: (event: AgentStreamEvent) => void,
): Promise<Record<string, unknown>> {
  const resp = await fetch("/api/agent/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...operatorHeaders(),
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(await readError(resp));
  if (!resp.body) throw new Error("Empty stream body");

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let complete: Record<string, unknown> | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      const event = JSON.parse(line.slice(6)) as AgentStreamEvent;
      if (event.type === "error") throw new Error(String(event.detail || "Agent run failed"));
      if (event.type === "complete") {
        complete = (event.report as Record<string, unknown>) || event;
        continue;
      }
      onEvent(event);
      await yieldFrame();
    }
  }

  if (!complete) throw new Error("Stream ended without a complete event");
  return complete;
}
