import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { Plus, LayoutDashboard, Trash2 } from "lucide-react"
import { useSpaces, useCreateSpace, useDeleteSpace } from "@/hooks/use-spaces"
import type { Space } from "@/lib/types"

export function HomePage() {
  const navigate = useNavigate()
  const { data: spaces, isLoading } = useSpaces()
  const createSpace = useCreateSpace()
  const deleteSpaceMutation = useDeleteSpace()
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState("")
  const [newDesc, setNewDesc] = useState("")

  function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!newName.trim()) return
    createSpace.mutate(
      { name: newName.trim(), description: newDesc.trim() },
      {
        onSuccess: (space) => {
          setShowCreate(false)
          setNewName("")
          setNewDesc("")
          navigate(`/spaces/${space.id}`)
        },
      }
    )
  }

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8">
      <div className="w-full max-w-2xl">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold mb-2">Space Dashboard</h1>
          <p className="text-muted-foreground">
            AI-powered workspaces for building dashboards from your data
          </p>
        </div>

        {/* Create Space */}
        {!showCreate ? (
          <button
            onClick={() => setShowCreate(true)}
            className="w-full flex items-center justify-center gap-2 rounded-lg border-2 border-dashed border-border p-6 text-muted-foreground hover:border-primary hover:text-foreground transition-colors"
          >
            <Plus className="h-5 w-5" />
            Create a new space
          </button>
        ) : (
          <form onSubmit={handleCreate} className="rounded-lg border border-border p-4 mb-4">
            <input
              autoFocus
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Space name"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm mb-2 focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <input
              type="text"
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder="Description (optional)"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={!newName.trim() || createSpace.isPending}
                className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {createSpace.isPending ? "Creating..." : "Create"}
              </button>
              <button
                type="button"
                onClick={() => setShowCreate(false)}
                className="rounded-md border border-border px-4 py-2 text-sm hover:bg-muted"
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        {/* Spaces List */}
        {isLoading && <p className="text-center text-muted-foreground mt-8">Loading spaces...</p>}
        <div className="mt-6 space-y-3">
          {spaces?.map((space: Space) => (
            <div
              key={space.id}
              className="flex items-center gap-4 rounded-lg border border-border p-4 hover:bg-muted/50 cursor-pointer transition-colors group"
              onClick={() => navigate(`/spaces/${space.id}`)}
            >
              <div className="h-10 w-10 rounded-md bg-primary/10 flex items-center justify-center">
                <LayoutDashboard className="h-5 w-5 text-primary" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-medium">{space.name}</h3>
                {space.description && (
                  <p className="text-sm text-muted-foreground truncate">{space.description}</p>
                )}
              </div>
              <span className="text-xs text-muted-foreground">
                {new Date(space.updated_at).toLocaleDateString()}
              </span>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  if (confirm(`Delete "${space.name}"?`)) {
                    deleteSpaceMutation.mutate(space.id)
                  }
                }}
                className="p-2 rounded opacity-0 group-hover:opacity-100 hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-opacity"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
