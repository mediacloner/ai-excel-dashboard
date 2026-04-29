import { useEffect, useRef, useState } from "react"
import { History, RotateCcw } from "lucide-react"
import { useWidgetVersions, useRestoreWidgetVersion } from "@/hooks/use-dashboards"
import { useDashboardStore } from "@/stores/dashboard-store"
import { cn } from "@/lib/utils"
import type { WidgetVersion } from "@/lib/types"

function relTime(iso: string): string {
  const then = new Date(iso.replace(" ", "T") + (iso.includes("Z") ? "" : "Z"))
  const diff = Date.now() - then.getTime()
  const s = Math.max(0, Math.floor(diff / 1000))
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  return `${d}d ago`
}

interface Props {
  widgetId: string
}

export function WidgetHistoryButton({ widgetId }: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const { data: versions, isLoading } = useWidgetVersions(widgetId, open)
  const restore = useRestoreWidgetVersion()
  const updateWidget = useDashboardStore((s) => s.updateWidget)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [open])

  const onRestore = (v: WidgetVersion) => {
    restore.mutate(v.id, {
      onSuccess: (widget) => {
        updateWidget(widget.id, widget)
        setOpen(false)
      },
    })
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "p-0.5 rounded text-muted-foreground hover:text-primary hover:bg-primary/10",
          open && "bg-primary/10 text-primary",
        )}
        title="Version history"
      >
        <History className="h-3.5 w-3.5" />
      </button>
      {open && (
        <div className="absolute right-0 top-6 z-50 w-80 max-h-96 overflow-auto rounded-md border border-border bg-popover shadow-lg text-popover-foreground">
          <div className="sticky top-0 bg-popover border-b border-border px-3 py-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Version history
          </div>
          {isLoading && <div className="p-3 text-sm text-muted-foreground">Loading…</div>}
          {!isLoading && versions && versions.length === 0 && (
            <div className="p-3 text-sm text-muted-foreground">No versions yet.</div>
          )}
          {versions?.map((v, i) => (
            <div
              key={v.id}
              className={cn(
                "px-3 py-2 border-b border-border/50 hover:bg-accent/40 group",
                i === 0 && "bg-accent/20",
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium uppercase text-muted-foreground">
                      {v.change_type}
                    </span>
                    <span className="text-xs text-muted-foreground">{relTime(v.created_at)}</span>
                    {i === 0 && (
                      <span className="text-[10px] px-1 py-0.5 rounded bg-primary/20 text-primary">current</span>
                    )}
                  </div>
                  {v.user_message && (
                    <div className="mt-1 text-xs text-foreground/80 line-clamp-2" title={v.user_message}>
                      “{v.user_message}”
                    </div>
                  )}
                  {v.title !== undefined && (
                    <div className="mt-0.5 text-[11px] text-muted-foreground truncate">{v.title}</div>
                  )}
                </div>
                {i !== 0 && (
                  <button
                    onClick={() => onRestore(v)}
                    disabled={restore.isPending}
                    className="opacity-0 group-hover:opacity-100 flex items-center gap-1 px-2 py-1 text-xs rounded bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-40"
                    title="Restore this version"
                  >
                    <RotateCcw className="h-3 w-3" />
                    Restore
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
