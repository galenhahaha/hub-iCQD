import type { Source } from "@/lib/types";

export function SourceChips({
  ids,
  inferred,
  lookup,
}: {
  ids: string[];
  inferred?: boolean;
  lookup: Map<string, Source>;
}) {
  if (inferred || ids.length === 0) {
    return <span className="chip inferred">模型推断</span>;
  }
  return (
    <span className="chips">
      {ids.map((id) => {
        const src = lookup.get(id);
        if (!src) return <span className="chip" key={id}>{id}</span>;
        return (
          <a key={id} className="chip-link" href={src.url} target="_blank" rel="noreferrer">
            {id} · {src.title}
          </a>
        );
      })}
    </span>
  );
}
