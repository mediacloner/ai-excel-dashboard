import { useState, useRef } from "react"
import { useParams } from "react-router-dom"
import { Upload, X, FileSpreadsheet, Loader2, CheckCircle2, Send } from "lucide-react"
import { useQueryClient } from "@tanstack/react-query"
import { uploadFile } from "@/lib/api"
import { streamFileUpload, streamSSE } from "@/lib/sse"
import type { SSEEventType } from "@/lib/types"

interface UploadDialogProps {
  open: boolean
  onClose: () => void
}

type UploadStep = "pick" | "uploading" | "analyzing" | "question" | "schema_review" | "importing" | "done" | "error"

interface PendingQuestion {
  question: string
  options: string[]
  context: string
}

interface SchemaColumn {
  original: string
  mapped_name: string
  sql_type: string
  description: string
  confidence: string
}

function tryParseToolCall(text: string): { name: string; arguments: Record<string, unknown> } | null {
  const cleaned = text.trim().replace(/\{\{/g, "{").replace(/\}\}/g, "}")
  try {
    const obj = JSON.parse(cleaned)
    if (obj && typeof obj === "object" && "name" in obj) {
      return obj as { name: string; arguments: Record<string, unknown> }
    }
  } catch { /* not JSON */ }
  return null
}

function renderMd(text: string): string {
  return text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")  // escape HTML
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")                    // **bold**
    .replace(/`([^`]+)`/g, '<code class="bg-black/10 px-1 rounded text-xs">$1</code>')  // `code`
    .replace(/\n/g, "<br>")                                               // newlines
}

export function UploadDialog({ open, onClose }: UploadDialogProps) {
  const { spaceId } = useParams()
  const queryClient = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [step, setStep] = useState<UploadStep>("pick")
  const [progress, setProgress] = useState("")
  const [messages, setMessages] = useState<Array<{ role: string; content: string }>>([])
  const [questionQueue, setQuestionQueue] = useState<PendingQuestion[]>([])
  const [answerInput, setAnswerInput] = useState("")
  const [schema, setSchema] = useState<SchemaColumn[] | null>(null)
  const [filePath, setFilePath] = useState("")
  const [sheetName, setSheetName] = useState<string | null>(null)
  const [headerRow, setHeaderRow] = useState(0)
  const [error, setError] = useState("")
  const [result, setResult] = useState<{ dataset_id?: string; row_count?: number } | null>(null)
  const abortRef = useRef<(() => void) | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  if (!open) return null

  function scrollBottom() {
    setTimeout(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }), 50)
  }

  function appendAssistant(content: string) {
    setMessages((prev) => {
      if (prev.length > 0 && prev[prev.length - 1].role === "assistant") {
        const updated = [...prev]
        updated[updated.length - 1] = {
          ...updated[updated.length - 1],
          content: updated[updated.length - 1].content + content,
        }
        return updated
      }
      return [...prev, { role: "assistant", content }]
    })
    scrollBottom()
  }

  function newAssistant(content: string) {
    setMessages((prev) => [...prev, { role: "assistant", content }])
    scrollBottom()
  }

  function newUser(content: string) {
    setMessages((prev) => [...prev, { role: "user", content }])
    scrollBottom()
  }

  function cleanText(text: string): string {
    let cleaned = text
    // Remove tool_call XML tags
    cleaned = cleaned.replace(/<tool_call>[\s\S]*?<\/tool_call>/g, "")
    // Remove any JSON-like content that looks like a tool call
    cleaned = cleaned.replace(/\{+"name"\s*:\s*"[^"]*"[\s\S]*?\}+/g, "")
    // Remove partial JSON fragments (start of a tool call that got cut off)
    cleaned = cleaned.replace(/\{+"name"\s*:[\s\S]*$/g, "")
    // Remove "arguments" JSON fragments
    cleaned = cleaned.replace(/"arguments"\s*:\s*\{[\s\S]*$/g, "")
    // Replace UUID filenames with the real filename
    if (file?.name) {
      cleaned = cleaned.replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.\w+/g, file.name)
    }
    return cleaned.trim()
  }

  function handleEvent(event: SSEEventType, data: Record<string, unknown>) {
    console.log("SSE event:", event, data)

    switch (event) {
      case "ingestion_start":
        setStep("analyzing")
        setProgress(`Analyzing ${file?.name || data.file_name}...`)
        newAssistant(`Analyzing **${file?.name || data.file_name}** (${(data.file_size_mb as number)?.toFixed?.(2) || "?"} MB, ${data.sheets_found} sheet(s))...\n\n`)
        break

      case "ingestion_progress":
        setProgress(data.message as string)
        break

      case "text": {
        const raw = data.content as string
        // Check if this is a raw tool call that leaked as text
        const parsedCall = tryParseToolCall(raw)
        if (parsedCall?.name === "ask_user") {
          // Queue it as a question
          const args = parsedCall.arguments || {}
          setQuestionQueue((prev) => {
            if (prev.length === 0) setStep("question")
            return [...prev, {
              question: (args.question as string) || "",
              options: (args.options as string[]) || [],
              context: (args.context as string) || "",
            }]
          })
          newAssistant((args.question as string) || "")
        } else if (parsedCall) {
          // Other tool call leaked — just ignore it
        } else {
          setStep("analyzing")
          const cleaned = cleanText(raw)
          if (cleaned && cleaned.length > 2) appendAssistant(cleaned)
        }
        break
      }

      case "tool_call_start":
        setProgress(`Running ${(data.tool as string).replace(/_/g, " ")}...`)
        break

      case "ask_user":
        // Queue all questions, show one at a time FIFO
        setQuestionQueue((prev) => {
          if (prev.length === 0) setStep("question")
          return [...prev, {
            question: data.question as string,
            options: (data.options as string[]) || [],
            context: (data.context as string) || "",
          }]
        })
        newAssistant(data.question as string)
        break

      case "ingestion_schema_review": {
        const cols = (data.schema as { columns: SchemaColumn[] })?.columns || []
        setSchema(cols)
        setStep("schema_review")
        setFilePath((data.file_path as string) || "")
        setSheetName((data.sheet_name as string | null) ?? null)
        setHeaderRow((data.header_row as number) ?? 0)
        newAssistant(`Schema generated with ${cols.length} columns. Review and confirm to import.`)
        break
      }

      case "ingestion_complete":
        setStep("done")
        setResult({ dataset_id: data.dataset_id as string, row_count: data.row_count as number })
        newAssistant(`Imported successfully — ${data.row_count} rows.`)
        queryClient.invalidateQueries({ queryKey: ["spaces", spaceId] })
        break

      case "error":
        setStep("error")
        setError(data.message as string)
        break

      case "done":
        // Stream finished — if we're still analyzing with no schema review, it might mean
        // the LLM finished asking questions. Keep current state.
        break
    }
  }

  function handleUpload() {
    if (!file || !spaceId) return
    setStep("uploading")
    setProgress("Uploading file...")
    setMessages([])

    const abort = streamFileUpload(
      file, spaceId, file.name.replace(/\.[^.]+$/, ""),
      handleEvent,
      (err) => { setStep("error"); setError(err.message) },
    )
    abortRef.current = abort
  }

  function handleAnswer(answer: string) {
    if (!answer.trim() || !spaceId) return

    newUser(answer)
    setAnswerInput("")

    setQuestionQueue((prev) => {
      const remaining = prev.slice(1)
      if (remaining.length > 0) {
        // More questions queued — show next one
        setStep("question")
      } else {
        // All questions answered — send all Q&A to backend
        setStep("analyzing")
        setProgress("Processing your answers...")

        // Build combined answer with all Q&A pairs from chat
        const updatedMessages = [...messages, { role: "user", content: answer }]
        const qaText = updatedMessages
          .filter(m => m.role === "user")
          .map(m => m.content)
          .join("\n")

        const abort = streamSSE(
          "/upload/ingest/answer",
          {
            answer: qaText,
            file_path: filePath,
            space_id: spaceId,
            dataset_name: file?.name.replace(/\.[^.]+$/, "") || "dataset",
            conversation_history: updatedMessages,
            sheet_name: sheetName,
            header_row: headerRow,
          },
          handleEvent,
          (err) => { setStep("error"); setError(err.message) },
        )
        abortRef.current = abort
      }
      return remaining
    })
  }

  function handleApproveSchema() {
    if (!schema || !spaceId) return

    setStep("importing")
    setProgress("Importing to database...")
    newUser("Approved — import the data.")

    // Build business context from Q&A
    const bizCtx = messages
      .filter(m => m.role === "user" || m.role === "assistant")
      .map(m => `${m.role === "user" ? "User" : "AI"}: ${m.content}`)
      .join("\n")

    const abort = streamSSE(
      "/upload/ingest/approve",
      {
        file_path: filePath,
        space_id: spaceId,
        dataset_name: file?.name.replace(/\.[^.]+$/, "") || "dataset",
        approved_schema: { columns: schema },
        sheet_name: sheetName,
        header_row: headerRow,
        business_context: bizCtx,
      },
      handleEvent,
      (err) => { setStep("error"); setError(err.message) },
    )
    abortRef.current = abort
  }

  function handleSimpleUpload() {
    if (!file || !spaceId) return
    setStep("uploading")
    setProgress("Uploading...")

    uploadFile(file, spaceId, file.name.replace(/\.[^.]+$/, ""))
      .then((res) => {
        setStep("done")
        setResult({ row_count: res.row_count })
        queryClient.invalidateQueries({ queryKey: ["spaces", spaceId] })
      })
      .catch((err) => { setStep("error"); setError(err.message) })
  }

  function handleClose() {
    abortRef.current?.()
    setFile(null)
    setStep("pick")
    setProgress("")
    setMessages([])
    setQuestionQueue([])
    setAnswerInput("")
    setSchema(null)
    setFilePath("")
    setError("")
    setResult(null)
    onClose()
  }

  const showConversation = step !== "pick" && step !== "done" && step !== "error"

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={handleClose}>
      <div
        className={`bg-card border border-border rounded-lg shadow-lg mx-4 flex flex-col ${showConversation ? "w-full max-w-2xl h-[80vh]" : "w-full max-w-md"}`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
          <h3 className="font-semibold">Upload Dataset</h3>
          <button onClick={handleClose} className="p-1 rounded hover:bg-muted">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-hidden flex flex-col min-h-0">

          {/* File picker */}
          {step === "pick" && (
            <div className="p-4">
              <div
                onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) setFile(f) }}
                onDragOver={(e) => e.preventDefault()}
                onClick={() => fileRef.current?.click()}
                className="border-2 border-dashed border-border rounded-lg p-8 text-center cursor-pointer hover:border-primary hover:bg-muted/50 transition-colors"
              >
                {file ? (
                  <div className="flex items-center justify-center gap-3">
                    <FileSpreadsheet className="h-8 w-8 text-primary" />
                    <div className="text-left">
                      <p className="font-medium text-sm">{file.name}</p>
                      <p className="text-xs text-muted-foreground">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
                    </div>
                  </div>
                ) : (
                  <>
                    <Upload className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
                    <p className="text-sm text-muted-foreground">Drop an Excel or CSV file here, or click to browse</p>
                    <p className="text-xs text-muted-foreground mt-1">.xlsx, .xls, .csv</p>
                  </>
                )}
                <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" onChange={(e) => { const f = e.target.files?.[0]; if (f) setFile(f) }} className="hidden" />
              </div>
              {file && (
                <div className="mt-4 flex gap-2">
                  <button onClick={handleSimpleUpload} className="flex-1 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90">
                    Quick Upload
                  </button>
                  <button onClick={handleUpload} className="flex-1 rounded-md border border-border px-4 py-2 text-sm hover:bg-muted">
                    AI-Assisted Import
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Conversational view */}
          {showConversation && (
            <>
              {/* Messages */}
              <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3 min-h-0">
                {messages.map((msg, i) => (
                  <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                    <div
                      className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${msg.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted"}`}
                      dangerouslySetInnerHTML={{ __html: renderMd(msg.content) }}
                    />
                  </div>
                ))}

                {/* Loading */}
                {(step === "uploading" || step === "analyzing" || step === "importing") && (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {progress}
                  </div>
                )}

                {/* Schema review */}
                {step === "schema_review" && schema && (
                  <div className="border border-border rounded-lg overflow-hidden">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="bg-muted">
                          <th className="text-left px-2 py-1.5 font-medium">Original</th>
                          <th className="text-left px-2 py-1.5 font-medium">Mapped Name</th>
                          <th className="text-left px-2 py-1.5 font-medium">Type</th>
                          <th className="text-left px-2 py-1.5 font-medium">Description</th>
                        </tr>
                      </thead>
                      <tbody>
                        {schema.map((col) => (
                          <tr key={col.mapped_name} className="border-t border-border">
                            <td className="px-2 py-1.5 text-muted-foreground">{col.original}</td>
                            <td className="px-2 py-1.5 font-mono">{col.mapped_name}</td>
                            <td className="px-2 py-1.5">{col.sql_type}</td>
                            <td className="px-2 py-1.5 text-muted-foreground">{col.description}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <div className="p-2 border-t border-border flex gap-2">
                      <button onClick={handleApproveSchema} className="rounded-md bg-primary px-4 py-1.5 text-sm text-primary-foreground hover:bg-primary/90">
                        Approve &amp; Import
                      </button>
                      <button onClick={handleClose} className="rounded-md border border-border px-4 py-1.5 text-sm hover:bg-muted">
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* FIFO question — one at a time from queue */}
              {step === "question" && questionQueue.length > 0 && (
                <div className="border-t border-border p-3 shrink-0">
                  {questionQueue.length > 1 && (
                    <p className="text-xs text-muted-foreground mb-2">{questionQueue.length} questions remaining</p>
                  )}
                  {questionQueue[0].options.length > 0 && (
                    <div className="flex flex-wrap gap-2 mb-2">
                      {questionQueue[0].options.map((opt) => (
                        <button
                          key={opt}
                          onClick={() => handleAnswer(opt)}
                          className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted hover:border-primary transition-colors"
                        >
                          {opt}
                        </button>
                      ))}
                    </div>
                  )}
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={answerInput}
                      onChange={(e) => setAnswerInput(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter" && answerInput.trim()) handleAnswer(answerInput) }}
                      placeholder="Or type your own answer..."
                      className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                      autoFocus
                    />
                    <button
                      onClick={() => handleAnswer(answerInput)}
                      disabled={!answerInput.trim()}
                      className="rounded-md bg-primary px-3 py-2 text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                    >
                      <Send className="h-4 w-4" />
                    </button>
                  </div>
                  <button
                    onClick={() => handleAnswer("skip")}
                    className="mt-2 text-xs text-muted-foreground hover:text-foreground"
                  >
                    Skip this question
                  </button>
                </div>
              )}
            </>
          )}

          {/* Done */}
          {step === "done" && (
            <div className="p-4 text-center py-8">
              <CheckCircle2 className="h-8 w-8 mx-auto text-green-600 mb-3" />
              <p className="text-sm font-medium">Dataset imported successfully</p>
              {result?.row_count && <p className="text-xs text-muted-foreground mt-1">{result.row_count} rows</p>}
              <button onClick={handleClose} className="mt-4 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90">
                Done
              </button>
            </div>
          )}

          {/* Error */}
          {step === "error" && (
            <div className="p-4 text-center py-8">
              <X className="h-8 w-8 mx-auto text-destructive mb-3" />
              <p className="text-sm font-medium text-destructive">Upload failed</p>
              <p className="text-xs text-muted-foreground mt-1 break-all">{error}</p>
              <button onClick={() => { setStep("pick"); setError(""); setMessages([]) }} className="mt-4 rounded-md border border-border px-4 py-2 text-sm hover:bg-muted">
                Try again
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
