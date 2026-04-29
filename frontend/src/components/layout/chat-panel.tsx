import { useState, useRef, useEffect, useMemo } from "react"
import { useParams } from "react-router-dom"
import { Send, Loader2 } from "lucide-react"

function renderMd(text: string): string {
  return text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, '<code class="bg-black/10 px-1 rounded text-xs font-mono">$1</code>')
    .replace(/^- (.+)$/gm, '<li class="ml-4">$1</li>')
    .replace(/^(\d+)\. (.+)$/gm, '<li class="ml-4">$1. $2</li>')
    .replace(/\n/g, "<br>")
}
import { cn } from "@/lib/utils"
import { streamSSE } from "@/lib/sse"
import { useDashboardStore } from "@/stores/dashboard-store"
import type { SSEEventType, Widget } from "@/lib/types"

interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  toolCalls?: Array<{ tool: string; status: string }>
}

export function ChatPanel() {
  const { spaceId, dashId } = useParams()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [streaming, setStreaming] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<(() => void) | null>(null)
  const addWidget = useDashboardStore((s) => s.addWidget)
  const updateWidget = useDashboardStore((s) => s.updateWidget)
  const chatPrompt = useDashboardStore((s) => s.chatPrompt)
  const setChatPrompt = useDashboardStore((s) => s.setChatPrompt)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [messages])

  // Pick up prompt from widget "edit in chat" button
  useEffect(() => {
    if (chatPrompt) {
      setInput(chatPrompt)
      setChatPrompt("")
      inputRef.current?.focus()
    }
  }, [chatPrompt, setChatPrompt])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!input.trim() || streaming || !spaceId) return

    const userMsg: Message = { id: crypto.randomUUID(), role: "user", content: input }
    setMessages((prev) => [...prev, userMsg])
    setInput("")
    setStreaming(true)

    const assistantId = crypto.randomUUID()
    setMessages((prev) => [...prev, { id: assistantId, role: "assistant", content: "", toolCalls: [] }])

    const abort = streamSSE(
      `/chat/spaces/${spaceId}/chat/stream`,
      { message: input, space_id: spaceId, dashboard_id: dashId || null },
      (event: SSEEventType, data: Record<string, unknown>) => {
        if (event === "text") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: m.content + (data.content as string) } : m
            )
          )
        } else if (event === "tool_call_start") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, toolCalls: [...(m.toolCalls || []), { tool: data.tool as string, status: "running" }] }
                : m
            )
          )
        } else if (event === "tool_call_result") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    toolCalls: m.toolCalls?.map((tc) =>
                      tc.tool === data.tool ? { ...tc, status: "done" } : tc
                    ),
                  }
                : m
            )
          )
        } else if (event === "widget_create") {
          const widget = (data as { widget: Widget }).widget
          addWidget(widget)
        } else if (event === "widget_update") {
          const widgetId = data.widget_id as string
          const widget = data.widget as Widget
          updateWidget(widgetId, widget)
        } else if (event === "done") {
          setStreaming(false)
        } else if (event === "error") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content + `\n\n**Error:** ${data.message}` }
                : m
            )
          )
          setStreaming(false)
        }
      },
      (err) => {
        setStreaming(false)
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: m.content + `\n\n**Connection error:** ${err.message}` } : m
          )
        )
      }
    )
    abortRef.current = abort
  }

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
            Ask a question about your data to create dashboard widgets
          </div>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}>
            <div
              className={cn(
                "max-w-[85%] rounded-lg px-3 py-2 text-sm",
                msg.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-foreground"
              )}
            >
              {msg.toolCalls && msg.toolCalls.length > 0 && (
                <div className="mb-2 space-y-1">
                  {msg.toolCalls.map((tc, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs text-muted-foreground">
                      {tc.status === "running" ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <span className="h-3 w-3 text-center">&#10003;</span>
                      )}
                      <span>{tc.tool.replace(/_/g, " ")}</span>
                    </div>
                  ))}
                </div>
              )}
              <div dangerouslySetInnerHTML={{ __html: renderMd(msg.content) }} />
            </div>
          </div>
        ))}
        {streaming && messages[messages.length - 1]?.content === "" && (
          <div className="flex justify-start">
            <div className="bg-muted rounded-lg px-3 py-2">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="border-t border-border p-3">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your data..."
            disabled={streaming}
            className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={streaming || !input.trim()}
            className="rounded-md bg-primary px-3 py-2 text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </form>
    </div>
  )
}
