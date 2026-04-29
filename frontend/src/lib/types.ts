// Mirrors backend Pydantic schemas

export interface Space {
  id: string
  name: string
  description: string
  created_at: string
  updated_at: string
}

export interface DatasetMetadata {
  id: string
  dataset_name: string
  original_filename: string
  column_dictionary: Record<string, unknown>
  table_name: string
  row_count: number
  upload_date: string
}

export interface SpaceDetail extends Space {
  datasets: DatasetMetadata[]
}

export interface WidgetLayout {
  x: number
  y: number
  w: number
  h: number
}

export interface Widget {
  id: string
  dashboard_id: string
  widget_type: "chart" | "kpi" | "table"
  title: string
  config: Record<string, unknown>
  sql_query: string | null
  layout: WidgetLayout
  created_at: string
  updated_at: string
}

export interface Dashboard {
  id: string
  space_id: string
  name: string
  created_at: string
  updated_at: string
  widgets: Widget[]
}

export interface WidgetVersion {
  id: string
  widget_id: string
  dashboard_id: string
  title: string
  widget_type: string
  config: Record<string, unknown>
  layout: WidgetLayout
  sql_query: string | null
  change_type: "created" | "updated" | "restored"
  user_message: string | null
  created_at: string
}

export interface Asset {
  id: string
  space_id: string
  filename: string
  mime: string
  url: string
  tags: string[]
  created_at: string
}

export interface ChatMessage {
  id: string
  space_id: string
  role: "user" | "assistant" | "tool"
  content: string
  tool_calls?: Record<string, unknown>[] | null
  tool_result?: Record<string, unknown> | null
  created_at: string
}

// SSE event types
export type SSEEventType =
  | "thinking"
  | "text"
  | "tool_call_start"
  | "tool_call_result"
  | "widget_create"
  | "widget_update"
  | "ask_user"
  | "ingestion_start"
  | "ingestion_progress"
  | "ingestion_schema_review"
  | "ingestion_complete"
  | "error"
  | "done"

export interface SSEEvent {
  event: SSEEventType
  data: Record<string, unknown>
}

export interface AskUserEvent {
  question: string
  options: string[]
  context: string
  checkpoint_id: string
}

export interface WidgetCreateEvent {
  widget: Widget
}

export interface IngestionSchemaReview {
  file_id: string
  schema: {
    columns: Array<{
      original: string
      mapped_name: string
      sql_type: string
      description: string
      confidence: string
    }>
  }
}
