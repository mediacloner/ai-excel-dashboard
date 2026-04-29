import { create } from "zustand"
import type { Widget } from "@/lib/types"

interface DashboardStore {
  widgets: Widget[]
  chatPrompt: string
  setWidgets: (widgets: Widget[]) => void
  addWidget: (widget: Widget) => void
  removeWidget: (widgetId: string) => void
  updateWidget: (widgetId: string, updates: Partial<Widget>) => void
  setChatPrompt: (prompt: string) => void
  clear: () => void
}

export const useDashboardStore = create<DashboardStore>((set) => ({
  widgets: [],
  chatPrompt: "",
  setWidgets: (widgets) => set({ widgets }),
  addWidget: (widget) => set((s) => ({ widgets: [...s.widgets, widget] })),
  removeWidget: (widgetId) => set((s) => ({ widgets: s.widgets.filter((w) => w.id !== widgetId) })),
  updateWidget: (widgetId, updates) =>
    set((s) => ({
      widgets: s.widgets.map((w) => {
        if (w.id !== widgetId) return w
        return { ...w, ...updates, config: { ...(updates.config || w.config) } }
      }),
    })),
  setChatPrompt: (prompt) => set({ chatPrompt: prompt }),
  clear: () => set({ widgets: [], chatPrompt: "" }),
}))
