/**
 * Types for config-driven view components (ADR-0008).
 */

import type { ComponentType } from 'react'
import type { EntityMetadata, QueryResult, SortField, FilterGroup } from './types'
import type { ValidationErrorBody } from './api'

// --- Data Patterns ---

export type DataPattern = 'query' | 'aggregate' | 'record' | 'compose'

export interface DataConfig {
  entityName?: string
  filter?: FilterGroup
  sort?: SortField[]
  pageSize?: number
  fields?: string[]
  // Record-specific
  recordId?: string | null
  // Aggregate-specific
  groupBy?: string[]
  measures?: Measure[]
  /** Declares which foreign-key field to filter by when embedded in a parent context */
  contextFilter?: { field: string }
}

export interface Measure {
  field: string
  aggregate: 'sum' | 'avg' | 'min' | 'max' | 'count'
  label?: string
  format?: string
}

// --- Config ---

export interface ConfigBase {
  id: string
  name: string
  description?: string | null
  entityName?: string | null
  pattern: DataPattern
  style: string
  scope: string
  source: string
  dataConfig: DataConfig
  styleConfig: Record<string, unknown>
}

// --- Presentation ---

export interface PresentationProps<TStyleConfig = Record<string, unknown>> {
  data: QueryResult
  metadata: EntityMetadata
  styleConfig: TStyleConfig
  dataConfig: DataConfig
  isLoading: boolean
  error: string | null
  /** When true, the component should render in a denser, embedded-friendly layout */
  compact?: boolean
  onSort?: (sort: SortField[]) => void
  onPageChange?: (offset: number) => void
  onRowClick?: (row: Record<string, unknown>) => void
  // Form callbacks (record/form pattern)
  onSubmit?: (data: Record<string, unknown>) => void
  onCancel?: () => void
  isSubmitting?: boolean
  serverErrors?: ValidationErrorBody | null
}

// --- Style Registry ---

export interface StyleRegistration<TStyleConfig = Record<string, unknown>> {
  pattern: DataPattern
  style: string
  component: ComponentType<PresentationProps<TStyleConfig>>
  defaultStyleConfig: TStyleConfig
  label: string
  /** Optional: metadata-aware config inference for this style */
  inferConfig?: (metadata: EntityMetadata) => Partial<TStyleConfig>
  /** Optional: suggested page size for this style (used during style swap) */
  suggestedPageSize?: number
}
