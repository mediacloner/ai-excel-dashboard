interface TableWidgetProps {
  config: Record<string, unknown>
}

export function TableWidget({ config }: TableWidgetProps) {
  const columns = (config.columns as string[]) || []
  const data = (config.data as unknown[][]) || []

  if (columns.length === 0) {
    return <div className="p-2 text-sm text-muted-foreground">No data</div>
  }

  return (
    <div className="overflow-auto h-full">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border">
            {columns.map((col) => (
              <th key={col} className="text-left px-2 py-1.5 font-medium text-muted-foreground whitespace-nowrap">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={i} className="border-b border-border/50 hover:bg-muted/50">
              {row.map((cell, j) => (
                <td key={j} className="px-2 py-1.5 whitespace-nowrap">
                  {cell != null ? String(cell) : "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
