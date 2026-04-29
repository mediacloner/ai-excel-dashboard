import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as api from "@/lib/api"

export function useAssets(spaceId: string | undefined) {
  return useQuery({
    queryKey: ["assets", spaceId],
    queryFn: () => api.listAssets(spaceId!),
    enabled: !!spaceId,
  })
}

export function useUploadAsset(spaceId: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ file, tags }: { file: File; tags?: string }) =>
      api.uploadAsset(spaceId!, file, tags),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["assets", spaceId] }),
  })
}

export function useUploadAssetFromUrl(spaceId: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ url, tags }: { url: string; tags?: string }) =>
      api.uploadAssetFromUrl(spaceId!, url, tags),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["assets", spaceId] }),
  })
}

export function useDeleteAsset(spaceId: string | undefined) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.deleteAsset(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["assets", spaceId] }),
  })
}
