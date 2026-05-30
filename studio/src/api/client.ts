export interface RequestOptions extends RequestInit {
  timeoutMs?: number;
}

export class StudioApiError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "StudioApiError";
    this.status = status;
  }
}

export function getApiBase(): string {
  return (import.meta.env.VITE_STUDIO_API_BASE || "http://127.0.0.1:8787").replace(/\/+$/, "");
}

export async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { timeoutMs = 10000, headers, ...requestOptions } = options;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const url = `${getApiBase()}${path.startsWith("/") ? path : `/${path}`}`;

  try {
    const response = await fetch(url, {
      ...requestOptions,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...headers
      }
    });

    if (!response.ok) {
      const body = await response.text().catch(() => "");
      throw new StudioApiError(
        `Studio API ${response.status} for ${path}${body ? `: ${body.slice(0, 240)}` : ""}`,
        response.status
      );
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof StudioApiError) {
      throw error;
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new StudioApiError(`Studio API timeout after ${timeoutMs}ms for ${path}`);
    }
    throw new StudioApiError(error instanceof Error ? error.message : `Studio API request failed for ${path}`);
  } finally {
    window.clearTimeout(timeout);
  }
}
