import { SendHorizontal, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "../common/Button";
import { LoadingSpinner } from "../common/LoadingSpinner";

interface ChatInputProps {
  isLoading: boolean;
  hasMessages: boolean;
  onSend: (message: string) => void;
  onClear: () => void;
}

export const ChatInput = ({ isLoading, hasMessages, onSend, onClear }: ChatInputProps) => {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const canSend = value.trim().length > 0 && !isLoading;

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }

    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
  }, [value]);

  const submit = () => {
    if (!canSend) {
      return;
    }

    onSend(value);
    setValue("");
  };

  return (
    <div className="border-t border-slate-200 bg-white/92 px-4 py-4 backdrop-blur">
      <div className="mx-auto flex w-full max-w-4xl items-end gap-3">
        <div className="min-h-[56px] flex-1 rounded-2xl border border-slate-200 bg-white px-4 py-2 shadow-soft focus-within:border-slate-400">
          <textarea
            ref={textareaRef}
            value={value}
            rows={1}
            placeholder="Ask a question..."
            disabled={isLoading}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
            className="block max-h-[180px] min-h-10 w-full resize-none bg-transparent py-2 text-sm leading-6 text-slate-900 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed"
          />
        </div>

        <Button
          type="button"
          variant="secondary"
          disabled={!hasMessages || isLoading}
          onClick={onClear}
          className="hidden w-10 px-0 sm:inline-flex"
          title="Clear chat"
          aria-label="Clear chat"
        >
          <Trash2 className="h-4 w-4" aria-hidden="true" />
        </Button>

        <Button
          type="button"
          disabled={!canSend}
          onClick={submit}
          className="w-11 px-0"
          title="Send message"
          aria-label="Send message"
        >
          {isLoading ? (
            <LoadingSpinner />
          ) : (
            <SendHorizontal className="h-4 w-4" aria-hidden="true" />
          )}
        </Button>
      </div>
    </div>
  );
};
