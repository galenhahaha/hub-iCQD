import type { Source } from "@/lib/types";

export function SourcesPanel({ sources }: { sources: Source[] }) {
  return (
    <section className="panel block" aria-labelledby="sources-heading">
      <h2 id="sources-heading">来源列表</h2>
      {sources.length === 0 ? (
        <p className="empty">尚无来源。检索开始后会出现可点击的 URL。</p>
      ) : (
        <ol className="sources">
          {sources.map((src) => (
            <li key={src.id}>
              <span className="src-id">{src.id}</span>
              <a href={src.url} target="_blank" rel="noreferrer">
                {src.title || src.url}
              </a>
              {src.site_name ? <span className="hint"> · {src.site_name}</span> : null}
              {src.published ? <span className="hint"> · {src.published}</span> : null}
              {src.snippet ? <p className="hint">{src.snippet}</p> : null}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
