import { useState, useCallback } from "react";

const FALLBACK = "Something went wrong. Please try again.";

interface UseApiErrorReturn {
  error: string | null;
  setError: (err: unknown) => void;
  clearError: () => void;
}

/** Normalises unknown thrown values into a display string.
 *  Prefers the `.detail` field from FastAPI error responses (already extracted
 *  into the Error message by client.ts), then falls back to a generic message. */
export function useApiError(): UseApiErrorReturn {
  const [error, setErrorState] = useState<string | null>(null);

  const setError = useCallback((err: unknown) => {
    if (err instanceof Error && err.message) {
      setErrorState(err.message);
    } else if (typeof err === "string" && err) {
      setErrorState(err);
    } else {
      setErrorState(FALLBACK);
    }
  }, []);

  const clearError = useCallback(() => setErrorState(null), []);

  return { error, setError, clearError };
}
