import { STATUS_LABEL } from "@/lib/labels";
import type { ResearchSummary } from "@/lib/types";

export function HistoryPanel({
  history,
  activeId,
  onSelect,
}: {
  history: ResearchSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <aside className="panel history" aria-label="历史研究">
      <h2>历史</h2>
      {history.length === 0 ? (
        <p className="empty">还没有记录。提交一个主题开始。</p>
      ) : (
        <ul className="history-list">
          {history.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className={`history-item${item.id === activeId ? " active" : ""}`}
                onClick={() => onSelect(item.id)}
              >
                <span className="topic">{item.topic}</span>
                <span className="meta">
                  {STATUS_LABEL[item.status]} · {item.id}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
