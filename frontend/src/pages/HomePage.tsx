import { RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";

import { getHealth } from "../api/chatApi";
import { ChatInput } from "../components/chat/ChatInput";
import { ChatWindow } from "../components/chat/ChatWindow";
import { Button } from "../components/common/Button";
import { ErrorAlert } from "../components/common/ErrorAlert";
import { useChat } from "../hooks/useChat";

type BackendStatus = "checking" | "online" | "offline";

export const HomePage = () => {
  const { messages, isLoading, error, sendMessage, clearChat } = useChat();
  const [backendStatus, setBackendStatus] = useState<BackendStatus>("checking");

  useEffect(() => {
    let isMounted = true;

    getHealth()
      .then(() => {
        if (isMounted) {
          setBackendStatus("online");
        }
      })
      .catch(() => {
        if (isMounted) {
          setBackendStatus("offline");
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const statusClasses = {
    checking: "bg-amber-400",
    online: "bg-emerald-500",
    offline: "bg-rose-500",
  } satisfies Record<BackendStatus, string>;

  const statusLabel = {
    checking: "Checking backend",
    online: "Backend online",
    offline: "Backend offline",
  } satisfies Record<BackendStatus, string>;

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/92 backdrop-blur">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between gap-4 px-4">
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold text-slate-950 sm:text-lg">
              Multimodal RAG Chatbot
            </h1>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600 sm:flex">
              <span
                className={`h-2 w-2 rounded-full ${statusClasses[backendStatus]}`}
                aria-hidden="true"
              />
              {statusLabel[backendStatus]}
            </div>
            <Button
              type="button"
              variant="ghost"
              disabled={!messages.length || isLoading}
              onClick={clearChat}
              className="hidden sm:inline-flex"
            >
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
              Clear
            </Button>
          </div>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto pb-4">
        {error ? <ErrorAlert message={error} /> : null}
        <ChatWindow messages={messages} isLoading={isLoading} />
      </main>

      <ChatInput
        isLoading={isLoading}
        hasMessages={messages.length > 0}
        onSend={sendMessage}
        onClear={clearChat}
      />
    </div>
  );
};
