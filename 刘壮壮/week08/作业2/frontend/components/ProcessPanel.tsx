import { KIND_LABEL, STATUS_LABEL } from "@/lib/labels";
import type { ResearchRecord } from "@/lib/types";

export function TopicHeader({ current, live }: { current: ResearchRecord; live: boolean }) {
  return (
    <section className="panel block">
      <span className={`status ${current.status}`}>{STATUS_LABEL[current.status]}</span>
      {live ? <span className="hint"> 正在更新过程…</span> : null}
      <h2 className="topic-line">{current.topic}</h2>
      <p className="hint">
        轮次 {current.process.iterations} · 检索词 {current.process.queries.length} · 已读
        {" "}{current.process.reviewed.length} · 来源 {current.sources.length}
      </p>
      {current.error ? <p className="error">{current.error}</p> : null}
    </section>
  );
}

export function ProcessPanel({ current }: { current: ResearchRecord }) {
  return (
    <section className="panel block" aria-labelledby="process-heading">
      <h2 id="process-heading">研究过程</h2>
      {current.process.queries.length > 0 ? (
        <p className="chips" style={{ marginBottom: 12 }}>
          {current.process.queries.map((q) => (
            <span className="chip" key={q}>{q}</span>
          ))}
        </p>
      ) : null}
      {current.process.steps.length === 0 ? (
        <p className="empty">等待规划开始…</p>
      ) : (
        <ol className="timeline">
          {current.process.steps.map((step, idx) => (
            <li key={`${step.at}-${idx}`}>
              <div>
                <span className="step-kind">{KIND_LABEL[step.kind]}</span>
                <span className="step-title">{step.title}</span>
              </div>
              {step.detail ? <p className="step-detail">{step.detail}</p> : null}
            </li>
          ))}
        </ol>
      )}
      {current.draft ? (
        <>
          <h3>中间草稿</h3>
          <pre className="draft">{current.draft}</pre>
        </>
      ) : null}
    </section>
  );
}
