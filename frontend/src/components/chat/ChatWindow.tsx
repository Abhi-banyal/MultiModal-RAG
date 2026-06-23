import { useEffect, useRef } from "react";

import type { ChatMessageModel } from "../../hooks/useChat";
import { EmptyState } from "../common/EmptyState";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { ChatMessage } from "./ChatMessage";

interface ChatWindowProps {
  messages: ChatMessageModel[];
  isLoading: boolean;
}

export const ChatWindow = ({ messages, isLoading }: ChatWindowProps) => {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isLoading]);

  if (!messages.length) {
    return <EmptyState />;
  }

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-6">
      <div className="space-y-6">
        {messages.map((message) => (
          <ChatMessage key={message.id} message={message} />
        ))}

        {isLoading ? (
          <div className="flex items-center gap-3 text-sm text-slate-500">
            <div className="grid h-8 w-8 place-items-center rounded-lg bg-lime-100">
              <LoadingSpinner />
            </div>
            Thinking through the retrieved context...
          </div>
        ) : null}

        <div ref={bottomRef} />
      </div>
    </div>
  );
};
