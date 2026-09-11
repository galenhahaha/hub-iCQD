import type { Report, Source } from "@/lib/types";
import { SourceChips } from "./SourceChips";

export function ReportPanel({
  report,
  lookup,
}: {
  report: Report;
  lookup: Map<string, Source>;
}) {
  return (
    <section className="panel block article" aria-labelledby="report-heading">
      <h2 id="report-heading">研究报告</h2>
      <h3>{report.title}</h3>
      <p className="lede">{report.summary}</p>
      {report.sections.map((sec) => (
        <div key={sec.heading}>
          <h3>{sec.heading}</h3>
          <p>{sec.body}</p>
          <SourceChips ids={sec.source_ids} lookup={lookup} />
        </div>
      ))}
      <h3>关键结论</h3>
      <ul className="conclusions">
        {report.key_conclusions.map((item, idx) => (
          <li key={idx}>
            <p>{item.text}</p>
            <SourceChips ids={item.source_ids} inferred={item.inferred} lookup={lookup} />
          </li>
        ))}
      </ul>
      {report.open_questions.length > 0 ? (
        <>
          <h3>遗留问题</h3>
          <ul>
            {report.open_questions.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
