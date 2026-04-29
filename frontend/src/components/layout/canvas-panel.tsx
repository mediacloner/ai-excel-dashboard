import { useCallback } from "react"
import GridLayoutLib, { WidthProvider, type Layout } from "react-grid-layout/legacy"
import { X, MessageSquare } from "lucide-react"
import { useDashboardStore } from "@/stores/dashboard-store"
import { useDeleteWidget } from "@/hooks/use-dashboards"
import { ChartWidget } from "@/components/dashboard/chart-widget"
import { KpiWidget } from "@/components/dashboard/kpi-widget"
import { TableWidget } from "@/components/dashboard/table-widget"
import { LayerOverlay } from "@/components/dashboard/layer-widget"
import { WidgetHistoryButton } from "@/components/dashboard/widget-history"
import { updateLayouts } from "@/lib/api"
import type { Widget } from "@/lib/types"
import "react-grid-layout/css/styles.css"

const GridLayout = WidthProvider(GridLayoutLib)

export function CanvasPanel() {
  const widgets = useDashboardStore((s) => s.widgets)
  const removeWidget = useDashboardStore((s) => s.removeWidget)
  const updateWidgetLocal = useDashboardStore((s) => s.updateWidget)
  const setChatPrompt = useDashboardStore((s) => s.setChatPrompt)
  const deleteWidgetMutation = useDeleteWidget()

  const layout = widgets.map((w) => ({
    i: w.id,
    x: w.layout.x,
    y: w.layout.y,
    w: w.layout.w,
    h: w.layout.h,
    minW: 2,
    minH: 1,
  }))

  const handleDelete = useCallback(
    (widgetId: string) => {
      removeWidget(widgetId)
      deleteWidgetMutation.mutate(widgetId)
    },
    [removeWidget, deleteWidgetMutation]
  )

  const handleLayoutChange = useCallback(
    (nextLayout: Layout[]) => {
      if (widgets.length === 0) return
      const dashboardId = widgets[0].dashboard_id
      const layouts: Record<string, { x: number; y: number; w: number; h: number }> = {}
      let changed = false
      for (const item of nextLayout) {
        const widget = widgets.find((w) => w.id === item.i)
        if (!widget) continue
        const prev = widget.layout
        if (prev.x === item.x && prev.y === item.y && prev.w === item.w && prev.h === item.h) continue
        changed = true
        layouts[item.i] = { x: item.x, y: item.y, w: item.w, h: item.h }
        updateWidgetLocal(item.i, {
          layout: { ...prev, x: item.x, y: item.y, w: item.w, h: item.h },
        })
      }
      if (!changed) return
      updateLayouts(dashboardId, layouts).catch((err) => {
        console.error("Failed to persist layout", err)
      })
    },
    [widgets, updateWidgetLocal]
  )

  function renderWidget(widget: Widget) {
    // Use updated_at as a remount key so any mutation — restore, update,
    // add_layer — forces a fresh mount of ECharts / table / KPI. Cheap, and
    // guarantees we never show stale visuals after a restore.
    const key = widget.updated_at || widget.id
    const hasLayers = Array.isArray((widget.config as Record<string, unknown>).layers)
    if (widget.widget_type === "chart") {
      return <ChartWidget key={key} config={widget.config} />
    }
    const base =
      widget.widget_type === "kpi" ? (
        <KpiWidget key={key} config={widget.config} />
      ) : widget.widget_type === "table" ? (
        <TableWidget key={key} config={widget.config} />
      ) : (
        <div className="p-4 text-muted-foreground">Unknown widget type</div>
      )
    if (!hasLayers) return base
    return (
      <div className="relative w-full h-full" key={key}>
        <LayerOverlay config={widget.config} />
        <div className="relative w-full h-full" style={{ zIndex: 1 }}>
          {base}
        </div>
      </div>
    )
  }

  if (widgets.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center bg-muted/30 h-full">
        <div className="text-center text-muted-foreground">
          <p className="text-lg font-medium mb-1">Empty dashboard</p>
          <p className="text-sm">Use the chat to ask questions and create widgets</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-auto bg-muted/30 p-4 h-full">
      <GridLayout
        className="layout"
        layout={layout}
        cols={12}
        rowHeight={120}
        margin={[12, 12]}
        isDraggable={true}
        isResizable={true}
        draggableHandle=".widget-drag-handle"
        onLayoutChange={handleLayoutChange}
      >
        {widgets.map((widget) => {
          const cfg = (widget.config || {}) as Record<string, unknown>
          const canvas = (cfg.canvas as Record<string, unknown> | undefined) || {}
          const bodyBg =
            (cfg.background as string | undefined) ??
            (canvas.background as string | undefined)
          const bodyFg = cfg.foreground as string | undefined
          return (
          <div key={widget.id} className="bg-card border border-border rounded-lg shadow-sm overflow-hidden">
            <div className="widget-drag-handle flex items-center justify-between px-3 py-2 border-b border-border bg-muted/50 cursor-move">
              <span className="text-sm font-medium truncate">{widget.title}</span>
              <div className="flex items-center gap-1">
                <WidgetHistoryButton widgetId={widget.id} />
                <button
                  onClick={() => setChatPrompt(`Update the "${widget.title}" chart: `)}
                  className="p-0.5 rounded hover:bg-primary/10 text-muted-foreground hover:text-primary"
                  title="Edit in chat"
                >
                  <MessageSquare className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => handleDelete(widget.id)}
                  className="p-0.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive"
                  title="Delete widget"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
            <div
              className="p-2 h-[calc(100%-36px)]"
              style={{ background: bodyBg, color: bodyFg }}
            >
              {renderWidget(widget)}
            </div>
          </div>
          )
        })}
      </GridLayout>
    </div>
  )
}
