export type ResearchStatus = "pending" | "running" | "completed" | "failed";
export type StepKind = "plan" | "search" | "extract" | "judge" | "synthesize";
export type ConfidenceLevel = "high" | "medium" | "low";

export type Source = {
  id: string;
  title: string;
  url: string;
  snippet: string;
  site_name: string;
  published: string;
};

export type Conclusion = {
  text: string;
  source_ids: string[];
  inferred: boolean;
};

export type ReportSection = {
  heading: string;
  body: string;
  source_ids: string[];
};

export type Report = {
  title: string;
  summary: string;
  sections: ReportSection[];
  key_conclusions: Conclusion[];
  open_questions: string[];
};

export type ReviewedItem = {
  title: string;
  url: string;
  query: string;
};

export type ProcessStep = {
  kind: StepKind;
  round: number;
  title: string;
  detail: string;
  at: string;
};

export type ResearchProcess = {
  queries: string[];
  reviewed: ReviewedItem[];
  iterations: number;
  steps: ProcessStep[];
};

export type Confidence = {
  level: ConfidenceLevel;
  as_of: string;
  rationale: string;
  inferred_count: number;
};

export type ResearchRecord = {
  id: string;
  topic: string;
  status: ResearchStatus;
  created_at: string;
  updated_at: string;
  error: string | null;
  draft: string;
  report: Report | null;
  sources: Source[];
  process: ResearchProcess;
  confidence: Confidence | null;
};

export type ResearchSummary = {
  id: string;
  topic: string;
  status: ResearchStatus;
  created_at: string;
  updated_at: string;
};

export type ResearchCreated = {
  id: string;
  status: ResearchStatus;
  topic: string;
};
