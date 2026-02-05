/**
 * Metadata types matching the backend API.
 */

export interface ValidationRules {
  required?: boolean
  min?: number
  max?: number
  minLength?: number
  maxLength?: number
  pattern?: string
}

export interface FieldUIConfig {
  component: string
  format?: string
  alignment?: string
  operator?: string
  mode?: string
}

export interface FieldMetadata {
  name: string
  displayName: string
  type: string
  primaryKey?: boolean
  readOnly?: boolean
  validation?: ValidationRules
  options?: { value: string; label: string }[]
  relation?: {
    entity: string
    displayField: string
  } | null
  ui: {
    display: FieldUIConfig
    edit: FieldUIConfig
    filter: FieldUIConfig
    grid: FieldUIConfig
  }
}

export interface EntityMetadata {
  entity: string
  displayName: string
  pluralName: string
  primaryKey: string
  fields: FieldMetadata[]
}

export interface FilterCondition {
  field: string
  operator: string
  value: unknown
}

export interface FilterGroup {
  operator: 'and' | 'or'
  conditions: (FilterCondition | FilterGroup)[]
}

export interface SortField {
  field: string
  direction: 'asc' | 'desc'
}

export interface QueryRequest {
  fields?: string[]
  filter?: FilterGroup
  sort?: SortField[]
  limit?: number
  offset?: number
}

export interface PaginationInfo {
  total: number
  limit: number | null
  offset: number
  hasMore: boolean
}

export interface QueryResult<T = Record<string, unknown>> {
  data: T[]
  pagination: PaginationInfo
}

export type UIContext = 'display' | 'edit' | 'filter' | 'grid'

export interface FieldComponentProps<T = unknown> {
  value: T
  onChange?: (value: T) => void
  field: FieldMetadata
  disabled?: boolean
  error?: string
}
