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

export async function animateCard(kidId: string): Promise<{ id: string; video_url: string }> {
  const resp = await fetch(`/api/cards/${encodeURIComponent(kidId)}/animate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jobs }),
  });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json() as Promise<RunResponse>;
}

export async function fetchRun(runId: string): Promise<RunResponse> {
  const resp = await fetch(`/api/runs/${encodeURIComponent(runId)}`);
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json() as Promise<RunResponse>;
}
