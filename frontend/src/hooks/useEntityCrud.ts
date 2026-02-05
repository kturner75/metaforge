/**
 * useEntityCrud — encapsulates CRUD mutations + warning acknowledgment
 * for any entity. Extracted from the monolithic ContactsApp logic.
 */

import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  useCreateEntity,
  useUpdateEntity,
  useDeleteEntity,
  type PendingWarnings,
} from './useApi'
import { ApiError, type ValidationErrorBody } from '@/lib/api'

interface WarningContext {
  mode: 'create' | 'edit'
  id?: string
}

export function useEntityCrud(entityName: string, baseUrl: string) {
  const navigate = useNavigate()

  const [validationErrors, setValidationErrors] = useState<ValidationErrorBody | null>(null)
  const [pendingWarnings, setPendingWarnings] = useState<PendingWarnings | null>(null)
  const [isAcknowledging, setIsAcknowledging] = useState(false)
  const [warningContext, setWarningContext] = useState<WarningContext | null>(null)

  const createMutation = useCreateEntity(entityName)
  const updateMutation = useUpdateEntity(entityName)
  const deleteMutation = useDeleteEntity(entityName)

  const clearErrors = useCallback(() => {
    setValidationErrors(null)
    setPendingWarnings(null)
    setWarningContext(null)
  }, [])

  const handleCreate = useCallback(async (data: Record<string, unknown>) => {
    try {
      setValidationErrors(null)
      setPendingWarnings(null)
      const result = await createMutation.mutateAsync(data)
      if (result.saved) {
        navigate(baseUrl)
      } else {
        setWarningContext({ mode: 'create' })
        setPendingWarnings(result.pendingWarnings)
      }
    } catch (err) {
      if (err instanceof ApiError && err.validation) {
        setValidationErrors(err.validation)
      }
    }
  }, [createMutation, navigate, baseUrl])

  const handleUpdate = useCallback(async (id: string, data: Record<string, unknown>) => {
    try {
      setValidationErrors(null)
      setPendingWarnings(null)
      const result = await updateMutation.mutateAsync({ id, data })
      if (result.saved) {
        navigate(baseUrl)
      } else {
        setWarningContext({ mode: 'edit', id })
        setPendingWarnings(result.pendingWarnings)
      }
    } catch (err) {
      if (err instanceof ApiError && err.validation) {
        setValidationErrors(err.validation)
      }
    }
  }, [updateMutation, navigate, baseUrl])

  const handleDelete = useCallback(async (id: string) => {
    if (confirm('Are you sure you want to delete this record?')) {
      await deleteMutation.mutateAsync(id)
      navigate(baseUrl)
    }
  }, [deleteMutation, navigate, baseUrl])

  const handleAcknowledge = useCallback(async () => {
    if (!pendingWarnings || !warningContext) return
    setIsAcknowledging(true)
    try {
      if (warningContext.mode === 'create') {
        await createMutation.acknowledge(pendingWarnings)
      } else if (warningContext.mode === 'edit' && warningContext.id) {
        await updateMutation.acknowledge(warningContext.id, pendingWarnings)
      }
      setPendingWarnings(null)
      setWarningContext(null)
      navigate(baseUrl)
    } catch (err) {
      setPendingWarnings(null)
      setWarningContext(null)
      if (err instanceof ApiError && err.validation) {
        setValidationErrors(err.validation)
      }
    } finally {
      setIsAcknowledging(false)
    }
  }, [pendingWarnings, warningContext, createMutation, updateMutation, navigate, baseUrl])

  const handleDismissWarnings = useCallback(() => {
    setPendingWarnings(null)
    setWarningContext(null)
  }, [])

  return {
    validationErrors,
    pendingWarnings,
    isAcknowledging,
    isCreating: createMutation.isPending,
    isUpdating: updateMutation.isPending,
    handleCreate,
    handleUpdate,
    handleDelete,
    handleAcknowledge,
    handleDismissWarnings,
    clearErrors,
  }
}
