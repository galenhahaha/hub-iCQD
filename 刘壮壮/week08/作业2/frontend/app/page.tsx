"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Composer } from "@/components/Composer";
import { ConfidencePanel } from "@/components/ConfidencePanel";
import { HistoryPanel } from "@/components/HistoryPanel";
import { ProcessPanel, TopicHeader } from "@/components/ProcessPanel";
import { ReportPanel } from "@/components/ReportPanel";
import { SourcesPanel } from "@/components/SourcesPanel";
import { API_BASE, createResearch, getResearch, listResearch } from "@/lib/api";
import type { ResearchRecord, ResearchSummary, Source } from "@/lib/types";

const POLL_MS = 1500;

function sourceMap(sources: Source[]): Map<string, Source> {
  return new Map(sources.map((s) => [s.id, s]));
}

export default function Page() {
  const [topic, setTopic] = useState("");
  const [history, setHistory] = useState<ResearchSummary[]>([]);
  const [current, setCurrent] = useState<ResearchRecord | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshHistory = useCallback(async () => {
    try {
      setHistory(await listResearch());
    } catch {
      /* 后端未启动时允许先渲染表单 */
    }
  }, []);

  useEffect(() => {
    void refreshHistory();
  }, [refreshHistory]);

  useEffect(() => {
    if (!activeId) return;
    let cancelled = false;
    let timer: number | undefined;

    const tick = async () => {
      try {
        const rec = await getResearch(activeId);
        if (cancelled) return;
        setCurrent(rec);
        setError(null);
        if (rec.status === "pending" || rec.status === "running") {
          timer = window.setTimeout(tick, POLL_MS);
        } else {
          void refreshHistory();
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "轮询失败");
      }
    };

    void tick();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [activeId, refreshHistory]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const text = topic.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createResearch(text);
      setActiveId(created.id);
      setCurrent(null);
      setTopic("");
      await refreshHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "发起研究失败");
    } finally {
      setBusy(false);
    }
  }

  const lookup = useMemo(() => sourceMap(current?.sources ?? []), [current]);
  const live = current?.status === "pending" || current?.status === "running";

  return (
    <div className="shell">
      <header className="masthead">
        <div>
          <p className="kicker">Deep Research</p>
          <h1>深度研究助手</h1>
          <p>输入一个主题。工具会规划检索词、多轮搜索、判断是否补检，再写出带来源的报告。</p>
        </div>
        <p className="hint">API {API_BASE}</p>
      </header>

      <div className="layout">
        <HistoryPanel history={history} activeId={activeId} onSelect={setActiveId} />

        <div>
          <Composer
            topic={topic}
            busy={busy}
            error={error}
            onTopicChange={setTopic}
            onSubmit={onSubmit}
          />

          {!current ? (
            <section className="panel block">
              <p className="empty">提交主题后，这里会显示规划、检索、抽取、补检判断和最终四类产物。</p>
            </section>
          ) : (
            <>
              <TopicHeader current={current} live={live} />
              <ProcessPanel current={current} />
              {current.report ? <ReportPanel report={current.report} lookup={lookup} /> : null}
              <SourcesPanel sources={current.sources} />
              <ConfidencePanel confidence={current.confidence} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
