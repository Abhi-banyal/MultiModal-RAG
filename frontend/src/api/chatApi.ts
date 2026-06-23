import { apiFetch } from "./client";
import type { ChatRequest, ChatResponse, HealthResponse } from "./types";

export const sendChatMessage = async (question: string): Promise<ChatResponse> => {
  const response = await apiFetch<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({ question } satisfies ChatRequest),
  });

  if (!response.answer?.trim()) {
    throw new Error("The backend returned an empty answer.");
  }

  return {
    answer: response.answer,
    sources: Array.isArray(response.sources) ? response.sources : [],
  };
};

export const getHealth = () => apiFetch<HealthResponse>("/health");
