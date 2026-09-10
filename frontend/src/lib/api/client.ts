/**
 * Base fetch wrapper for talking to the FastAPI backend. This is the ONLY
 * place that should read NEXT_PUBLIC_API_BASE_URL -- feature modules under
 * lib/api/* call `apiFetch`, they never construct URLs themselves.
 */

import { getStoredToken } from "@/lib/auth/token";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

/** Attaches `Authorization: Bearer <token>` whenever AuthProvider has a
 * stored token, so every apiFetch/apiFetchStream call is authenticated
 * without callers having to think about it -- see app/api/deps.py on the
 * backend for what it expects. */
function buildHeaders(extra?: HeadersInit): HeadersInit {
  const token = getStoredToken();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  };
}

export class ApiError extends Error {
  status: number;
  /** Per-field messages parsed from a FastAPI 422 body, keyed by field name (camelCase). */
  fieldErrors?: Record<string, string>;

  constructor(status: number, message: string, fieldErrors?: Record<string, string>) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

interface FastApiValidationError {
  loc?: (string | number)[];
  msg?: string;
}

interface ParsedError {
  message: string;
  fieldErrors?: Record<string, string>;
}

async function parseErrorResponse(res: Response): Promise<ParsedError> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") {
      return { message: body.detail };
    }
    if (Array.isArray(body?.detail)) {
      const errors = body.detail as FastApiValidationError[];
      const fieldErrors: Record<string, string> = {};
      for (const err of errors) {
        const field = err.loc?.[err.loc.length - 1];
        if (typeof field === "string" && err.msg) {
          fieldErrors[field] = err.msg;
        }
      }
      const message = errors
        .map((err) => {
          const field = err.loc?.[err.loc.length - 1] ?? "request";
          return err.msg ? `${field}: ${err.msg}` : "Invalid request";
        })
        .join("; ");
      return { message, fieldErrors: Object.keys(fieldErrors).length ? fieldErrors : undefined };
    }
  } catch {
    // Body wasn't JSON (or was empty) -- fall through to the generic message.
  }
  return { message: `Request failed (${res.status})` };
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: buildHeaders(init?.headers),
    });
  } catch {
    throw new ApiError(0, "Could not reach the StudyGraph API. Is the backend running?");
  }

  if (!res.ok) {
    const { message, fieldErrors } = await parseErrorResponse(res);
    throw new ApiError(res.status, message, fieldErrors);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

/**
 * Same request/error handling as `apiFetch`, but for endpoints whose
 * successful response isn't JSON (e.g. `text/event-stream`) -- returns the
 * raw `Response` so the caller can read `.body` itself. A non-OK response is
 * still parsed and thrown as `ApiError` exactly like `apiFetch`, since a
 * failed request (422/503) comes back as plain JSON even for a streaming
 * endpoint -- see docs/API.md ("POST /api/v1/chat").
 */
export async function apiFetchStream(path: string, init?: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: buildHeaders(init?.headers),
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "Could not reach the StudyGraph API. Is the backend running?");
  }

  if (!res.ok) {
    const { message, fieldErrors } = await parseErrorResponse(res);
    throw new ApiError(res.status, message, fieldErrors);
  }

  return res;
}
