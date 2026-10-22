import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './api'
import type { Dashboard, Document, ProvidersResponse, Subject } from './types'

export function useDocuments(poll = false) {
  return useQuery({
    queryKey: ['documents'],
    queryFn: () => api<Document[]>('/api/v1/documents'),
    refetchInterval: (query) => {
      const docs = query.state.data
      const busy = docs?.some((d) => d.status === 'uploaded' || d.status === 'processing')
      return poll && busy ? 2000 : false
    },
  })
}

export function useReadyDocuments() {
  const q = useDocuments()
  return { ...q, data: (q.data ?? []).filter((d) => d.status === 'ready') }
}

export function useSubjects() {
  return useQuery({ queryKey: ['subjects'], queryFn: () => api<Subject[]>('/api/v1/syllabus/subjects'), staleTime: 5 * 60_000 })
}

export function useDashboard() {
  return useQuery({ queryKey: ['dashboard'], queryFn: () => api<Dashboard>('/api/v1/dashboard'), staleTime: 30_000 })
}

export function useProviders() {
  return useQuery({ queryKey: ['providers'], queryFn: () => api<ProvidersResponse>('/api/v1/settings/providers') })
}

export function useInvalidate() {
  const qc = useQueryClient()
  return (...keys: string[]) => keys.forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
}
