import type { SSEEventType } from "./types"

type SSEHandler = (event: SSEEventType, data: Record<string, unknown>) => void

// SSE streams go directly to the backend to avoid Vite proxy buffering
const SSE_BASE = "http://127.0.0.1:8000"

/**
 * POST-based SSE client using fetch + ReadableStream.
 * (EventSource API only supports GET, so we use fetch for POST requests.)
 *
 * Returns an abort function to cancel the stream.
 */
export function streamSSE(
  path: string,
  body: Record<string, unknown>,
  onEvent: SSEHandler,
  onError?: (error: Error) => void,
): () => void {
  const controller = new AbortController()

  ;(async () => {
    try {
      const res = await fetch(`${SSE_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      })

      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // Parse SSE events from buffer
        const lines = buffer.split("\n")
        buffer = lines.pop() || "" // Keep incomplete line in buffer

        let currentEvent = ""
        let currentData = ""

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith("data: ")) {
            currentData = line.slice(6)
          } else if (line === "" && currentEvent && currentData) {
            // Empty line = end of event
            try {
              const parsed = JSON.parse(currentData)
              onEvent(currentEvent as SSEEventType, parsed)
            } catch {
              // Skip malformed events
            }
            currentEvent = ""
            currentData = ""
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        onError?.(err as Error)
      }
    }
  })()

  return () => controller.abort()
}

/**
 * Upload a file with SSE streaming response.
 */
export function streamFileUpload(
  file: File,
  spaceId: string,
  datasetName: string,
  onEvent: SSEHandler,
  onError?: (error: Error) => void,
): () => void {
  const controller = new AbortController()

  ;(async () => {
    try {
      const formData = new FormData()
      formData.append("file", file)

      const params = new URLSearchParams({
        space_id: spaceId,
        dataset_name: datasetName,
      })

      const res = await fetch(`${SSE_BASE}/upload/ingest/start?${params}`, {
        method: "POST",
        body: formData,
        signal: controller.signal,
      })

      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split("\n")
        buffer = lines.pop() || ""

        let currentEvent = ""
        let currentData = ""

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith("data: ")) {
            currentData = line.slice(6)
          } else if (line === "" && currentEvent && currentData) {
            try {
              const parsed = JSON.parse(currentData)
              onEvent(currentEvent as SSEEventType, parsed)
            } catch {
              // Skip malformed
            }
            currentEvent = ""
            currentData = ""
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        onError?.(err as Error)
      }
    }
  })()

  return () => controller.abort()
}
