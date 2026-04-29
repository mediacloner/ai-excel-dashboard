import { Outlet } from "react-router-dom"

export function AppShell() {
  return (
    <div className="flex h-screen bg-background text-foreground">
      <Outlet />
    </div>
  )
}
