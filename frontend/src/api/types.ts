export interface ChatRequest {
  question: string;
}

export interface Source {
  file_name: string;
  page_number?: number | null;
  content_type: string;
  chunk_type?: string | null;
  title?: string | null;
  caption?: string | null;
  figure_number?: string | null;
  visual_type?: string | null;
  year?: number | null;
  quarter?: string | string[] | null;
  score?: number | null;
  rerank_score?: number | null;
  matched_text_preview?: string | null;
  visual_url?: string | null;
  visual_label?: string | null;
}

export interface ChatResponse {
  answer: string;
  sources: Source[];
}

export interface HealthResponse {
  status: string;
  vector_store?: string | null;
  vector_store_backend?: string | null;
  collection?: string | null;
  embedding_model?: string | null;
  vector_count?: number | null;
}

export interface ValidationErrorDetail {
  loc?: Array<string | number>;
  msg?: string;
  type?: string;
}

export interface ErrorResponse {
  detail?: string | ValidationErrorDetail[];
}
