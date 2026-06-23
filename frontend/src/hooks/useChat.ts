import { useCallback, useState } from "react";

import { sendChatMessage } from "../api/chatApi";
import { ApiError } from "../api/client";
import type { Source } from "../api/types";

export type ChatRole = "user" | "assistant";

export interface ChatMessageModel {
  id: string;
  role: ChatRole;
  content: string;
  sources?: Source[];
  isError?: boolean;
}

const createId = () => `${Date.now()}-${crypto.randomUUID()}`;

const toFriendlyError = (error: unknown) => {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message;
  }

  return "Something went wrong while contacting the backend.";
};

export const useChat = () => {
  const [messages, setMessages] = useState<ChatMessageModel[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(
    async (question: string) => {
      const trimmed = question.trim();

      if (!trimmed || isLoading) {
        return;
      }

      setError(null);
      setMessages((current) => [
        ...current,
        {
          id: createId(),
          role: "user",
          content: trimmed,
        },
      ]);
      setIsLoading(true);

      try {
        const response = await sendChatMessage(trimmed);
        setMessages((current) => [
          ...current,
          {
            id: createId(),
            role: "assistant",
            content: response.answer,
            sources: response.sources,
          },
        ]);
      } catch (caughtError) {
        const message = toFriendlyError(caughtError);
        setError(message);
        setMessages((current) => [
          ...current,
          {
            id: createId(),
            role: "assistant",
            content: message,
            isError: true,
          },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [isLoading],
  );

  const clearChat = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  return {
    messages,
    isLoading,
    error,
    sendMessage,
    clearChat,
  };
};
