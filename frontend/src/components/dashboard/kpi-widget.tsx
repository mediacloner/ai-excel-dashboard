import { TrendingUp, TrendingDown, Minus } from "lucide-react"
import { cn } from "@/lib/utils"

interface KpiWidgetProps {
  config: Record<string, unknown>
}

export function KpiWidget({ config }: KpiWidgetProps) {
  const value = (config.value as string) || "—"
  const subtitle = (config.subtitle as string) || ""
  const trend = config.trend as string | null

  return (
    <div className="flex flex-col items-center justify-center h-full">
      <div className="text-3xl font-bold">{value}</div>
      {subtitle && <div className="text-sm text-muted-foreground mt-1">{subtitle}</div>}
      {trend && (
        <div
          className={cn(
            "flex items-center gap-1 mt-2 text-sm font-medium",
            trend === "up" && "text-green-600",
            trend === "down" && "text-red-600",
            trend === "neutral" && "text-muted-foreground"
          )}
        >
          {trend === "up" && <TrendingUp className="h-4 w-4" />}
          {trend === "down" && <TrendingDown className="h-4 w-4" />}
          {trend === "neutral" && <Minus className="h-4 w-4" />}
          {trend}
        </div>
      )}
    </div>
  )
}
