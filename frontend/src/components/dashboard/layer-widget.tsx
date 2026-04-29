import { type CSSProperties, useMemo } from "react"
import ReactECharts from "echarts-for-react"

type Anchor =
  | "top-left" | "top-center" | "top-right"
  | "center-left" | "center" | "center-right"
  | "bottom-left" | "bottom-center" | "bottom-right"
  | "fill"

interface Layer {
  id: string
  type: "chart" | "image" | "text" | "svg" | "shape"
  anchor?: Anchor
  offset?: [number, number]
  size?: [number, number] | null
  z?: number
  echarts_option?: Record<string, unknown>
  src?: string
  asset_id?: string
  content?: string
  markup?: string
  kind?: "rect" | "circle" | "line"
  style?: Record<string, string | number>
}

interface Composition {
  canvas?: { background?: string } & Record<string, unknown>
  layers?: Layer[]
}

interface LayerWidgetProps {
  config: Record<string, unknown>
}

function normalize(config: Record<string, unknown>): Composition {
  if (Array.isArray((config as Composition).layers)) {
    return config as Composition
  }
  // Legacy path: wrap single echarts_option as one chart layer filling the body
  const opt = config.echarts_option as Record<string, unknown> | undefined
  if (opt) {
    return {
      canvas: {},
      layers: [
        { id: "chart", type: "chart", anchor: "fill", echarts_option: opt },
      ],
    }
  }
  return { canvas: {}, layers: [] }
}

function layerPosition(layer: Layer): CSSProperties {
  const anchor = layer.anchor ?? "top-left"
  const [ox, oy] = layer.offset ?? [0, 0]
  const size = layer.size ?? null
  const style: CSSProperties = { position: "absolute", zIndex: layer.z ?? 0 }

  if (anchor === "fill") {
    style.inset = 0
    return style
  }

  if (size) {
    style.width = size[0]
    style.height = size[1]
  }

  const topish = anchor.startsWith("top-")
  const bottomish = anchor.startsWith("bottom-")
  const leftish = anchor.endsWith("-left")
  const rightish = anchor.endsWith("-right")

  if (topish) style.top = oy
  else if (bottomish) style.bottom = oy
  else {
    style.top = "50%"
    style.transform = (style.transform ?? "") + " translateY(-50%)"
  }

  if (leftish) style.left = ox
  else if (rightish) style.right = ox
  else {
    style.left = "50%"
    style.transform = (style.transform ?? "") + " translateX(-50%)"
  }

  if (anchor === "center") {
    style.transform = `translate(calc(-50% + ${ox}px), calc(-50% + ${oy}px))`
  }
  return style
}

function RenderLayer({ layer }: { layer: Layer }) {
  const pos = layerPosition(layer)

  if (layer.type === "chart") {
    return (
      <div style={pos}>
        <ReactECharts
          option={layer.echarts_option ?? {}}
          notMerge={true}
          lazyUpdate={false}
          style={{ height: "100%", width: "100%" }}
          opts={{ renderer: "canvas" }}
        />
      </div>
    )
  }

  if (layer.type === "image") {
    const src = layer.src ?? (layer.asset_id ? `/api/assets/file/${layer.asset_id}` : "")
    if (!src) return null
    return (
      <img
        src={src}
        alt=""
        style={{
          ...pos,
          objectFit: "contain",
          pointerEvents: "none",
          ...(layer.style as CSSProperties ?? {}),
        }}
      />
    )
  }

  if (layer.type === "text") {
    return (
      <div
        style={{
          ...pos,
          color: "rgb(229, 229, 229)",
          fontSize: 12,
          whiteSpace: "pre-wrap",
          pointerEvents: "none",
          ...(layer.style as CSSProperties ?? {}),
        }}
      >
        {layer.content ?? ""}
      </div>
    )
  }

  if (layer.type === "svg") {
    return (
      <div
        style={{ ...pos, pointerEvents: "none" }}
        dangerouslySetInnerHTML={{ __html: layer.markup ?? "" }}
      />
    )
  }

  if (layer.type === "shape") {
    const kind = layer.kind ?? "rect"
    const shapeStyle: CSSProperties = {
      ...pos,
      pointerEvents: "none",
      background: (layer.style?.fill as string) ?? "rgba(255,255,255,0.08)",
      ...(layer.style as CSSProperties ?? {}),
    }
    if (kind === "circle") shapeStyle.borderRadius = "50%"
    if (kind === "line") {
      // Render a 1-2px bar as a "line"
      shapeStyle.background = (layer.style?.fill as string) ?? "rgb(120,120,120)"
      if (!layer.size) {
        shapeStyle.height = 1
        shapeStyle.width = "100%"
      }
    }
    return <div style={shapeStyle} />
  }

  return null
}

export function LayerWidget({ config }: LayerWidgetProps) {
  const comp = useMemo(() => normalize(config), [config])
  const bg = comp.canvas?.background
  const sorted = [...(comp.layers ?? [])].sort((a, b) => (a.z ?? 0) - (b.z ?? 0))

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        background: bg,
      }}
    >
      {sorted.map((layer) => (
        <RenderLayer key={layer.id} layer={layer} />
      ))}
    </div>
  )
}

/**
 * Overlay-only renderer: renders the `layers` from a widget's config without
 * the chart-layer auto-wrap. Use it to decorate non-chart widgets (table, KPI)
 * with the same layer primitives (logos, annotations, fill-image backgrounds).
 */
interface LayerOverlayProps {
  config: Record<string, unknown>
}

export function LayerOverlay({ config }: LayerOverlayProps) {
  const layers = (config.layers as Layer[] | undefined) ?? []
  if (layers.length === 0) return null
  // Skip chart layers here — those only make sense inside LayerWidget
  const overlays = layers
    .filter((l) => l.type !== "chart")
    .sort((a, b) => (a.z ?? 0) - (b.z ?? 0))
  return (
    <>
      {overlays.map((layer) => (
        <RenderLayer key={layer.id} layer={layer} />
      ))}
    </>
  )
}
