import { useEffect, useState } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { Group, Panel, Separator } from "react-resizable-panels"
import { SpaceSidebar } from "@/components/layout/space-sidebar"
import { CanvasPanel } from "@/components/layout/canvas-panel"
import { ChatPanel } from "@/components/layout/chat-panel"
import { UploadDialog } from "@/components/upload/upload-dialog"
import { useDashboard, useDashboards } from "@/hooks/use-dashboards"
import { useDashboardStore } from "@/stores/dashboard-store"

export function SpacePage() {
  const { spaceId, dashId } = useParams()
  const navigate = useNavigate()
  const { data: dashboards } = useDashboards(spaceId)
  const { data: dashboard } = useDashboard(dashId)
  const setWidgets = useDashboardStore((s) => s.setWidgets)
  const clear = useDashboardStore((s) => s.clear)
  const [uploadOpen, setUploadOpen] = useState(false)

  // Auto-navigate to first dashboard if no dashId in URL
  useEffect(() => {
    if (!dashId && dashboards && dashboards.length > 0) {
      navigate(`/spaces/${spaceId}/dash/${dashboards[0].id}`, { replace: true })
    }
  }, [dashId, dashboards, spaceId, navigate])

  // Clear store when changing space or dashboard
  useEffect(() => {
    clear()
  }, [spaceId, dashId, clear])

  // Sync dashboard widgets to Zustand store
  useEffect(() => {
    if (dashboard?.widgets) {
      setWidgets(dashboard.widgets)
    }
  }, [dashboard, setWidgets])

  return (
    <div className="flex h-screen w-full">
      <SpaceSidebar onUploadClick={() => setUploadOpen(true)} />
      <Group orientation="horizontal" className="flex-1">
        <Panel defaultSize={65} minSize={30}>
          <CanvasPanel />
        </Panel>
        <Separator className="w-1.5 bg-border hover:bg-primary/20 transition-colors" />
        <Panel defaultSize={35} minSize={20}>
          <ChatPanel />
        </Panel>
      </Group>
      <UploadDialog open={uploadOpen} onClose={() => setUploadOpen(false)} />
    </div>
  )
}
