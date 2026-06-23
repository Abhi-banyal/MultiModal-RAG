import { env } from "../config/env";
import type { ErrorResponse } from "./types";

const API_TIMEOUT_MS = 45_000;

export class ApiError extends Error {
  status?: number;
  details?: unknown;

  constructor(message: string, status?: number, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

const parseResponse = async <T>(response: Response): Promise<T> => {
  const text = await response.text();
  if (!text) {
    throw new ApiError("The backend returned an empty response.", response.status);
  }

  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError("The backend returned an unreadable response.", response.status);
  }
};

const getErrorMessage = (status: number, data: ErrorResponse | null) => {
  if (status === 422) {
    return "The backend rejected the chat request as invalid. The request body may not match the expected schema.";
  }

  if (status >= 500) {
    return "The backend chat logic failed while generating a response. Please check the backend terminal for the traceback.";
  }

  if (typeof data?.detail === "string") {
    return data.detail;
  }

  return "The backend rejected the request. Please try again.";
};

export const apiFetch = async <T>(
  path: string,
  options: RequestInit = {},
): Promise<T> => {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  const headers = new Headers(options.headers);

  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  try {
    const response = await fetch(`${env.apiBaseUrl}${path}`, {
      ...options,
      signal: controller.signal,
      headers,
    });

    if (!response.ok) {
      let data: ErrorResponse | null = null;
      try {
        data = await response.json();
      } catch {
        data = null;
      }

      throw new ApiError(getErrorMessage(response.status, data), response.status, data);
    }

    return parseResponse<T>(response);
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }

    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("The chat request timed out. Please try a shorter question.");
    }

    if (path === "/chat") {
      throw new ApiError(
        "The health check is reachable, but the chat request could not reach the backend. This is usually a blocked CORS preflight, a frontend origin mismatch, or a network failure on POST /chat.",
      );
    }

    throw new ApiError(
      "Could not reach the backend health endpoint. Check that FastAPI is running at the configured API URL.",
    );
  } finally {
    window.clearTimeout(timeoutId);
  }
};
