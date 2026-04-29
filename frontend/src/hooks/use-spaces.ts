import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import * as api from "@/lib/api"

export function useSpaces() {
  return useQuery({
    queryKey: ["spaces"],
    queryFn: api.listSpaces,
  })
}

export function useSpace(id: string | undefined) {
  return useQuery({
    queryKey: ["spaces", id],
    queryFn: () => api.getSpace(id!),
    enabled: !!id,
  })
}

export function useCreateSpace() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ name, description }: { name: string; description?: string }) =>
      api.createSpace(name, description),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["spaces"] }),
  })
}

export function useDeleteSpace() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.deleteSpace(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["spaces"] }),
  })
}
