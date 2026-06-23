import { ChevronDown, FileText } from "lucide-react";

import type { Source } from "../../api/types";

interface SourcePanelProps {
  sources: Source[];
}

const formatScore = (score?: number | null) =>
  typeof score === "number" ? score.toFixed(3) : null;

const formatQuarter = (quarter?: string | string[] | null) => {
  if (Array.isArray(quarter)) {
    return quarter.join(", ");
  }

  return quarter ?? null;
};

const SourceMeta = ({ label, value }: { label: string; value?: string | number | null }) => {
  if (value === undefined || value === null || value === "") {
    return null;
  }

  return (
    <span className="rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600">
      {label}: {value}
    </span>
  );
};

export const SourcePanel = ({ sources }: SourcePanelProps) => {
  if (!sources.length) {
    return null;
  }

  return (
    <details className="group mt-4 rounded-lg border border-slate-200 bg-white">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-medium text-slate-700">
        <span className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-slate-500" aria-hidden="true" />
          Sources ({sources.length})
        </span>
        <ChevronDown
          className="h-4 w-4 text-slate-500 transition group-open:rotate-180"
          aria-hidden="true"
        />
      </summary>
      <div className="space-y-3 border-t border-slate-100 p-4">
        {sources.map((source, index) => (
          <article
            key={`${source.file_name}-${source.page_number ?? "na"}-${index}`}
            className="rounded-lg border border-slate-100 bg-slate-50 p-4"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-slate-900">
                  {source.title || source.file_name}
                </h3>
                <p className="mt-1 text-xs text-slate-500">{source.file_name}</p>
              </div>
              <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200">
                #{index + 1}
              </span>
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              <SourceMeta label="Page" value={source.page_number} />
              <SourceMeta label="Type" value={source.content_type} />
              <SourceMeta label="Chunk" value={source.chunk_type} />
              <SourceMeta label="Figure" value={source.figure_number} />
              <SourceMeta label="Visual" value={source.visual_type} />
              <SourceMeta label="Year" value={source.year} />
              <SourceMeta label="Quarter" value={formatQuarter(source.quarter)} />
              <SourceMeta label="Score" value={formatScore(source.score)} />
              <SourceMeta label="Rerank" value={formatScore(source.rerank_score)} />
            </div>

            {source.visual_url ? (
              <p className="mt-3 text-xs font-medium text-emerald-700">
                Visual source attached above
              </p>
            ) : null}

            {source.caption ? (
              <p className="mt-3 text-sm leading-6 text-slate-700">{source.caption}</p>
            ) : null}

            {source.matched_text_preview ? (
              <blockquote className="mt-3 border-l-2 border-lime-400 pl-3 text-sm leading-6 text-slate-600">
                {source.matched_text_preview}
              </blockquote>
            ) : null}
          </article>
        ))}
      </div>
    </details>
  );
};
