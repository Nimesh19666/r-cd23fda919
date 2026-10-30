// One hook per endpoint. Components never build URLs themselves.
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { getJson } from './client'

export const useMeta = () =>
  useQuery({ queryKey: ['meta'], queryFn: () => getJson('/api/meta'), staleTime: Infinity })

export const useDecision = (deliveryDate) =>
  useQuery({
    queryKey: ['decision', deliveryDate],
    queryFn: () => getJson(`/api/decision?delivery_date=${encodeURIComponent(deliveryDate)}`),
    placeholderData: keepPreviousData, // keep the old chart visible while a new day loads
  })

export const useAccuracy = () =>
  useQuery({ queryKey: ['accuracy'], queryFn: () => getJson('/api/accuracy'), staleTime: Infinity })
