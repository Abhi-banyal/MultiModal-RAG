import { ExternalLink, ImageIcon } from "lucide-react";

import type { Source } from "../../api/types";
import { env } from "../../config/env";

interface VisualEvidenceProps {
  sources: Source[];
}

const toAbsoluteUrl = (url: string) => {
  if (/^https?:\/\//i.test(url)) {
    return url;
  }

  return `${env.apiBaseUrl}${url.startsWith("/") ? url : `/${url}`}`;
};

const visualKey = (source: Source) =>
  `${source.visual_url}-${source.file_name}-${source.page_number ?? "source"}`;

export const VisualEvidence = ({ sources }: VisualEvidenceProps) => {
  const visuals = sources
    .filter((source) => source.visual_url)
    .filter(
      (source, index, all) =>
        all.findIndex((candidate) => visualKey(candidate) === visualKey(source)) === index,
    )
    .slice(0, 3);

  if (!visuals.length) {
    return null;
  }

  return (
    <section className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-800">
        <ImageIcon className="h-4 w-4 text-slate-500" aria-hidden="true" />
        Visual evidence
      </div>

      <div className="grid gap-3">
        {visuals.map((source) => {
          const imageUrl = toAbsoluteUrl(source.visual_url!);
          const label =
            source.visual_label ||
            source.caption ||
            source.title ||
            `${source.file_name}${source.page_number ? `, page ${source.page_number}` : ""}`;

          return (
            <figure
              key={visualKey(source)}
              className="overflow-hidden rounded-lg border border-slate-200 bg-white"
            >
              <a href={imageUrl} target="_blank" rel="noreferrer" className="block">
                <img
                  src={imageUrl}
                  alt={label}
                  className="max-h-[520px] w-full bg-white object-contain"
                  loading="lazy"
                />
              </a>
              <figcaption className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 px-3 py-2 text-xs text-slate-600">
                <span>
                  {label}
                  {source.page_number ? ` | page ${source.page_number}` : ""}
                </span>
                <a
                  href={imageUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 font-medium text-slate-700 hover:text-slate-950"
                >
                  Open
                  <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                </a>
              </figcaption>
            </figure>
          );
        })}
      </div>
    </section>
  );
};
