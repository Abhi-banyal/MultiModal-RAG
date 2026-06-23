import { Bot, UserRound } from "lucide-react";

import type { ChatMessageModel } from "../../hooks/useChat";
import { SourcePanel } from "./SourcePanel";
import { VisualEvidence } from "./VisualEvidence";

interface ChatMessageProps {
  message: ChatMessageModel;
}

export const ChatMessage = ({ message }: ChatMessageProps) => {
  const isUser = message.role === "user";
  const bubbleClasses = isUser
    ? "ml-auto max-w-[78%] bg-slate-950 text-white"
    : message.isError
      ? "mr-auto max-w-[86%] border border-rose-200 bg-rose-50 text-rose-900"
      : "mr-auto max-w-[86%] border border-slate-200 bg-white text-slate-800 shadow-sm";

  return (
    <div className={`flex w-full gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser ? (
        <div className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-lime-100 text-slate-900">
          <Bot className="h-4 w-4" aria-hidden="true" />
        </div>
      ) : null}

      <div className={`rounded-2xl px-4 py-3 ${bubbleClasses}`}>
        <div className="whitespace-pre-wrap text-sm leading-7">{message.content}</div>
        {!isUser && !message.isError ? (
          <>
            <VisualEvidence sources={message.sources ?? []} />
            <SourcePanel sources={message.sources ?? []} />
          </>
        ) : null}
      </div>

      {isUser ? (
        <div className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-slate-200 text-slate-700">
          <UserRound className="h-4 w-4" aria-hidden="true" />
        </div>
      ) : null}
    </div>
  );
};
