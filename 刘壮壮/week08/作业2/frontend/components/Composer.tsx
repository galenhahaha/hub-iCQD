import { FormEvent } from "react";

export function Composer({
  topic,
  busy,
  error,
  onTopicChange,
  onSubmit,
}: {
  topic: string;
  busy: boolean;
  error: string | null;
  onTopicChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
}) {
  return (
    <form className="panel composer" onSubmit={onSubmit}>
      <label htmlFor="topic">研究主题</label>
      <textarea
        id="topic"
        name="topic"
        value={topic}
        onChange={(e) => onTopicChange(e.target.value)}
        placeholder="例如：国内智能驾驶舱供应商格局与头部产品差异"
        required
      />
      <div className="row">
        <button className="primary" type="submit" disabled={busy || !topic.trim()}>
          {busy ? "提交中…" : "开始研究"}
        </button>
        <p className="hint">任务在后台执行，页面会轮询过程，不必等全部完成才看到内容。</p>
      </div>
      {error ? <p className="error" role="alert">{error}</p> : null}
    </form>
  );
}
