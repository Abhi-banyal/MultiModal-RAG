import { MessageSquareText, SearchCheck, Sparkles } from "lucide-react";

const prompts = [
  "Ask about the company report",
  "Compare details across documents",
  "Find evidence from PDFs and images",
];

export const EmptyState = () => (
  <div className="mx-auto flex min-h-[52vh] w-full max-w-3xl flex-col items-center justify-center px-6 text-center">
    <div className="mb-5 grid h-14 w-14 place-items-center rounded-2xl bg-white shadow-soft ring-1 ring-slate-200">
      <MessageSquareText className="h-7 w-7 text-slate-800" aria-hidden="true" />
    </div>
    <h2 className="text-2xl font-semibold text-slate-950">
      What would you like to know?
    </h2>
    <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">
      Ask about the indexed reports, policies, charts, images, and PDFs.
    </p>
    <div className="mt-8 grid w-full gap-3 sm:grid-cols-3">
      {prompts.map((prompt, index) => {
        const Icon = index === 0 ? SearchCheck : Sparkles;

        return (
          <div
            key={prompt}
            className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-left shadow-sm"
          >
            <Icon className="mb-2 h-4 w-4 text-emerald-700" aria-hidden="true" />
            <p className="text-sm font-medium text-slate-700">{prompt}</p>
          </div>
        );
      })}
    </div>
  </div>
);
