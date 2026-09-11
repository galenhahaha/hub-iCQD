import type { ConfidenceLevel, ResearchStatus, StepKind } from "./types";

export const STATUS_LABEL: Record<ResearchStatus, string> = {
  pending: "排队中",
  running: "研究中",
  completed: "已完成",
  failed: "失败",
};

export const LEVEL_LABEL: Record<ConfidenceLevel, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

export const KIND_LABEL: Record<StepKind, string> = {
  plan: "规划",
  search: "检索",
  extract: "抽取",
  judge: "判断",
  synthesize: "综合",
};
