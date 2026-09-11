import type { ResearchCreated, ResearchRecord, ResearchSummary } from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://127.0.0.1:8000";

async function readError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
    if (Array.isArray(data?.detail)) return data.detail.map(String).join("; ");
  } catch {
    /* ignore */
  }
  return `请求失败（${res.status}）`;
}

export async function createResearch(topic: string): Promise<ResearchCreated> {
  const res = await fetch(`${API_BASE}/api/research`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic }),
  });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

export async function getResearch(id: string): Promise<ResearchRecord> {
  const res = await fetch(`${API_BASE}/api/research/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

export async function listResearch(): Promise<ResearchSummary[]> {
  const res = await fetch(`${API_BASE}/api/research`, { cache: "no-store" });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}
