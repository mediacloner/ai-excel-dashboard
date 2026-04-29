import type {
  Space,
  SpaceDetail,
  Dashboard,
  ChatMessage,
  DatasetMetadata,
  WidgetLayout,
  Widget,
  WidgetVersion,
  Asset,
} from "./types"

const BASE = "/api"

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

// --- Spaces ---

export async function listSpaces(): Promise<Space[]> {
  const res = await request<{ spaces: Space[] }>("/spaces")
  return res.spaces
}

export async function getSpace(id: string): Promise<SpaceDetail> {
  return request<SpaceDetail>(`/spaces/${id}`)
}

export async function createSpace(name: string, description = ""): Promise<Space> {
  return request<Space>("/spaces", {
    method: "POST",
    body: JSON.stringify({ name, description }),
  })
}

export async function updateSpace(id: string, data: { name?: string; description?: string }): Promise<Space> {
  return request<Space>(`/spaces/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  })
}

export async function deleteSpace(id: string): Promise<void> {
  await request(`/spaces/${id}`, { method: "DELETE" })
}

export async function linkDataset(spaceId: string, datasetId: string): Promise<void> {
  await request(`/spaces/${spaceId}/datasets/${datasetId}`, { method: "POST" })
}

// --- Dashboards ---

export async function listDashboards(spaceId: string): Promise<Dashboard[]> {
  const res = await request<{ dashboards: Dashboard[] }>(`/spaces/${spaceId}/dashboards`)
  return res.dashboards
}

export async function getDashboard(id: string): Promise<Dashboard> {
  return request<Dashboard>(`/dashboards/${id}`)
}

export async function createDashboard(spaceId: string, name: string): Promise<Dashboard> {
  return request<Dashboard>(`/spaces/${spaceId}/dashboards`, {
    method: "POST",
    body: JSON.stringify({ name }),
  })
}

export async function deleteDashboard(id: string): Promise<void> {
  await request(`/dashboards/${id}`, { method: "DELETE" })
}

export async function updateLayouts(
  dashboardId: string,
  layouts: Record<string, WidgetLayout>,
): Promise<void> {
  await request(`/dashboards/${dashboardId}/layout`, {
    method: "PUT",
    body: JSON.stringify({ layouts }),
  })
}

// --- Widgets ---

export async function deleteWidget(id: string): Promise<void> {
  await request(`/widgets/${id}`, { method: "DELETE" })
}

export async function listWidgetVersions(widgetId: string): Promise<WidgetVersion[]> {
  const res = await request<{ versions: WidgetVersion[] }>(`/widgets/${widgetId}/versions`)
  return res.versions
}

export async function restoreWidgetVersion(versionId: string): Promise<Widget> {
  return request<Widget>(`/widget-versions/${versionId}/restore`, { method: "POST" })
}

// --- Chat ---

export async function getChatHistory(spaceId: string): Promise<ChatMessage[]> {
  const res = await request<{ messages: ChatMessage[] }>(`/chat/spaces/${spaceId}/history`)
  return res.messages
}

export async function clearChatHistory(spaceId: string): Promise<void> {
  await request(`/chat/spaces/${spaceId}/history`, { method: "DELETE" })
}

// --- Datasets ---

export async function listDatasets(): Promise<DatasetMetadata[]> {
  const res = await request<{ datasets: DatasetMetadata[] }>("/datasets")
  return res.datasets
}

export async function deleteDataset(id: string): Promise<void> {
  await request(`/datasets/${id}`, { method: "DELETE" })
}

export async function unlinkDataset(spaceId: string, datasetId: string): Promise<void> {
  await request(`/spaces/${spaceId}/datasets/${datasetId}`, { method: "DELETE" })
}

export async function getDataset(id: string): Promise<DatasetMetadata & { schema: Record<string, string>; suggested_questions: string[] }> {
  return request(`/datasets/${id}`)
}

// --- Upload ---

// --- Assets ---

export async function listAssets(spaceId: string): Promise<Asset[]> {
  const res = await request<{ assets: Asset[] }>(`/spaces/${spaceId}/assets`)
  return res.assets
}

export async function uploadAssetFromUrl(
  spaceId: string,
  url: string,
  tags?: string,
): Promise<Asset> {
  return request<Asset>(`/spaces/${spaceId}/assets/from-url`, {
    method: "POST",
    body: JSON.stringify({ url, tags }),
  })
}

export async function uploadAsset(
  spaceId: string,
  file: File,
  tags?: string,
): Promise<Asset> {
  const formData = new FormData()
  formData.append("file", file)
  const params = new URLSearchParams()
  if (tags) params.set("tags", tags)

  const res = await fetch(`${BASE}/spaces/${spaceId}/assets?${params}`, {
    method: "POST",
    body: formData,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

export async function deleteAsset(id: string): Promise<void> {
  await request(`/assets/${id}`, { method: "DELETE" })
}

// --- Upload ---

export async function uploadFile(
  file: File,
  spaceId?: string,
  datasetName?: string,
): Promise<{ file_id: string; filename: string; row_count: number; column_count: number }> {
  const formData = new FormData()
  formData.append("file", file)
  const params = new URLSearchParams()
  if (spaceId) params.set("space_id", spaceId)
  if (datasetName) params.set("dataset_name", datasetName)

  const res = await fetch(`${BASE}/upload?${params}`, {
    method: "POST",
    body: formData,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}
