import { useRef, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { LayoutDashboard, Database, Upload, ArrowLeft, Plus, Trash2, Image as ImageIcon, Link as LinkIcon } from "lucide-react"
import { useQueryClient } from "@tanstack/react-query"
import { cn } from "@/lib/utils"
import { deleteDataset } from "@/lib/api"
import { useSpace } from "@/hooks/use-spaces"
import { useDashboards } from "@/hooks/use-dashboards"
import { useAssets, useUploadAsset, useUploadAssetFromUrl, useDeleteAsset } from "@/hooks/use-assets"
import type { DatasetMetadata, Dashboard, Asset } from "@/lib/types"

interface SpaceSidebarProps {
  onUploadClick?: () => void
}

export function SpaceSidebar({ onUploadClick }: SpaceSidebarProps) {
  const { spaceId, dashId } = useParams()
  const { data: space } = useSpace(spaceId)
  const { data: dashboards } = useDashboards(spaceId)
  const { data: assets } = useAssets(spaceId)
  const uploadAsset = useUploadAsset(spaceId)
  const uploadAssetFromUrl = useUploadAssetFromUrl(spaceId)
  const deleteAsset = useDeleteAsset(spaceId)
  const assetInputRef = useRef<HTMLInputElement>(null)
  const [urlInputOpen, setUrlInputOpen] = useState(false)
  const [urlInput, setUrlInput] = useState("")
  const queryClient = useQueryClient()

  const handleAssetPick = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) uploadAsset.mutate({ file })
    event.target.value = ""
  }

  const handleUrlSubmit = () => {
    const url = urlInput.trim()
    if (!url) return
    uploadAssetFromUrl.mutate(
      { url },
      {
        onSuccess: () => {
          setUrlInput("")
          setUrlInputOpen(false)
        },
      },
    )
  }

  return (
    <div className="w-60 border-r border-sidebar-border bg-sidebar text-sidebar-foreground flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-sidebar-border">
        <Link to="/" className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-2">
          <ArrowLeft className="h-4 w-4" />
          All Spaces
        </Link>
        <h2 className="font-semibold text-lg truncate">{space?.name || "Loading..."}</h2>
        {space?.description && (
          <p className="text-xs text-muted-foreground mt-1 truncate">{space.description}</p>
        )}
      </div>

      {/* Dashboards */}
      <div className="flex-1 overflow-y-auto">
        <div className="p-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Dashboards</span>
          </div>
          {dashboards?.map((d: Dashboard) => (
            <Link
              key={d.id}
              to={`/spaces/${spaceId}/dash/${d.id}`}
              className={cn(
                "flex items-center gap-2 px-2 py-1.5 rounded text-sm hover:bg-sidebar-accent",
                dashId === d.id && "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
              )}
            >
              <LayoutDashboard className="h-4 w-4 shrink-0" />
              <span className="truncate">{d.name}</span>
              <span className="ml-auto text-xs text-muted-foreground">{d.widgets.length}</span>
            </Link>
          ))}
          {(!dashboards || dashboards.length === 0) && (
            <p className="text-xs text-muted-foreground px-2">No dashboards yet</p>
          )}
        </div>

        {/* Datasets */}
        <div className="p-3 border-t border-sidebar-border">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Datasets</span>
            <button
              onClick={onUploadClick}
              className="p-1 rounded hover:bg-sidebar-accent"
              title="Upload dataset"
            >
              <Upload className="h-3.5 w-3.5" />
            </button>
          </div>
          {space?.datasets?.map((ds: DatasetMetadata) => (
            <div key={ds.id} className="flex items-center gap-2 px-2 py-1.5 text-sm group">
              <Database className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="truncate flex-1">{ds.dataset_name}</span>
              <span className="text-xs text-muted-foreground group-hover:hidden">{ds.row_count}</span>
              <button
                onClick={() => {
                  if (confirm(`Delete dataset "${ds.dataset_name}"?`)) {
                    deleteDataset(ds.id).then(() =>
                      queryClient.invalidateQueries({ queryKey: ["spaces", spaceId] })
                    )
                  }
                }}
                className="hidden group-hover:block p-0.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
          {(!space?.datasets || space.datasets.length === 0) && (
            <button
              onClick={onUploadClick}
              className="w-full flex items-center gap-2 px-2 py-1.5 text-sm text-muted-foreground hover:text-foreground"
            >
              <Plus className="h-4 w-4" />
              Upload your first dataset
            </button>
          )}
        </div>

        {/* Assets (logos / images the composer can place on widgets) */}
        <div className="p-3 border-t border-sidebar-border">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Assets</span>
            <div className="flex items-center gap-0.5">
              <button
                onClick={() => setUrlInputOpen((v) => !v)}
                className={cn(
                  "p-1 rounded hover:bg-sidebar-accent disabled:opacity-50",
                  urlInputOpen && "bg-sidebar-accent text-sidebar-accent-foreground",
                )}
                title="Import from URL"
                disabled={uploadAssetFromUrl.isPending}
              >
                <LinkIcon className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => assetInputRef.current?.click()}
                className="p-1 rounded hover:bg-sidebar-accent disabled:opacity-50"
                title="Upload image/logo"
                disabled={uploadAsset.isPending}
              >
                <Upload className="h-3.5 w-3.5" />
              </button>
            </div>
            <input
              ref={assetInputRef}
              type="file"
              accept=".png,.jpg,.jpeg,.svg,.webp,.gif"
              className="hidden"
              onChange={handleAssetPick}
            />
          </div>
          {urlInputOpen && (
            <div className="mb-2 space-y-1">
              <input
                type="url"
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleUrlSubmit()}
                placeholder="https://…/image.png"
                className="w-full px-2 py-1 text-xs bg-background border border-border rounded focus:outline-none focus:ring-1 focus:ring-ring"
                autoFocus
              />
              <div className="flex items-center gap-1">
                <button
                  onClick={handleUrlSubmit}
                  disabled={!urlInput.trim() || uploadAssetFromUrl.isPending}
                  className="px-2 py-0.5 text-xs bg-primary text-primary-foreground rounded hover:opacity-90 disabled:opacity-40"
                >
                  {uploadAssetFromUrl.isPending ? "Fetching…" : "Import"}
                </button>
                {uploadAssetFromUrl.isError && (
                  <span className="text-xs text-destructive truncate" title={uploadAssetFromUrl.error?.message}>
                    Failed
                  </span>
                )}
              </div>
            </div>
          )}
          {assets?.map((a: Asset) => (
            <div key={a.id} className="flex items-center gap-2 px-2 py-1 text-sm group">
              <img src={a.url} alt="" className="h-5 w-5 object-contain shrink-0" />
              <span className="truncate flex-1" title={a.filename}>{a.filename}</span>
              <button
                onClick={() => {
                  if (confirm(`Delete asset "${a.filename}"?`)) {
                    deleteAsset.mutate(a.id)
                  }
                }}
                className="hidden group-hover:block p-0.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
          {(!assets || assets.length === 0) && (
            <button
              onClick={() => assetInputRef.current?.click()}
              className="w-full flex items-center gap-2 px-2 py-1.5 text-sm text-muted-foreground hover:text-foreground"
            >
              <ImageIcon className="h-4 w-4" />
              Upload a logo or image
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
