import { LEVEL_LABEL } from "@/lib/labels";
import type { Confidence } from "@/lib/types";

export function ConfidencePanel({ confidence }: { confidence: Confidence | null }) {
  return (
    <section className="panel block" aria-labelledby="conf-heading">
      <h2 id="conf-heading">置信度</h2>
      {confidence ? (
        <>
          <p>
            可靠程度 <strong>{LEVEL_LABEL[confidence.level]}</strong>
            {" · "}信息截止 {confidence.as_of}
            {" · "}模型推断 {confidence.inferred_count} 条
          </p>
          <p>{confidence.rationale}</p>
          <p className="hint">没有来源支撑的结论会标成「模型推断」，不会假装成检索事实。</p>
        </>
      ) : (
        <p className="empty">报告生成后会给出可靠程度与信息截止时间。</p>
      )}
    </section>
  );
}
