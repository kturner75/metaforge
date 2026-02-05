import { useState, useRef, useMemo, useEffect } from 'react'
import type { FieldComponentProps } from '@/lib/types'
import { useEntityQuery } from '@/hooks/useApi'

export function RelationSelect({ value, onChange, field, disabled, error }: FieldComponentProps<string>) {
  const relation = field.relation
  const [search, setSearch] = useState('')
  const [isOpen, setIsOpen] = useState(false)
  const [highlightIndex, setHighlightIndex] = useState(-1)
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const { data, isLoading } = useEntityQuery(relation?.entity ?? '', {
    fields: ['id', relation?.displayField ?? 'name'],
    limit: 200,
  })

  if (!relation) {
    return <span className="field-error">Missing relation config</span>
  }

  const records = data?.data ?? []
  const displayField = relation.displayField

  // Find the display label for the currently selected value
  const selectedLabel = useMemo(() => {
    if (!value) return ''
    const match = records.find((r) => r.id === value)
    return match ? (match[displayField] as string) : value
  }, [value, records, displayField])

  // Filter records based on search text
  const filtered = useMemo(() => {
    if (!search) return records
    const lower = search.toLowerCase()
    return records.filter((r) => {
      const label = (r[displayField] as string) ?? ''
      return label.toLowerCase().includes(lower)
    })
  }, [records, search, displayField])

  // Close dropdown on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
        setSearch('')
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const handleSelect = (id: string) => {
    onChange?.(id)
    setIsOpen(false)
    setSearch('')
    setHighlightIndex(-1)
  }

  const handleClear = () => {
    onChange?.('')
    setSearch('')
    setIsOpen(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen) {
      if (e.key === 'ArrowDown' || e.key === 'Enter') {
        setIsOpen(true)
        e.preventDefault()
      }
      return
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setHighlightIndex((i) => Math.min(i + 1, filtered.length - 1))
        break
      case 'ArrowUp':
        e.preventDefault()
        setHighlightIndex((i) => Math.max(i - 1, 0))
        break
      case 'Enter':
        e.preventDefault()
        if (highlightIndex >= 0 && highlightIndex < filtered.length) {
          handleSelect(filtered[highlightIndex].id as string)
        }
        break
      case 'Escape':
        setIsOpen(false)
        setSearch('')
        setHighlightIndex(-1)
        break
    }
  }

  return (
    <div
      ref={containerRef}
      className={`relation-select ${error ? 'field-error' : ''} ${disabled ? 'disabled' : ''}`}
    >
      <div className="relation-select-input-wrapper">
        <input
          ref={inputRef}
          type="text"
          className="relation-select-input"
          placeholder={value ? selectedLabel : `Search ${field.displayName}...`}
          value={isOpen ? search : (value ? selectedLabel : '')}
          onChange={(e) => {
            setSearch(e.target.value)
            setHighlightIndex(-1)
            if (!isOpen) setIsOpen(true)
          }}
          onFocus={() => setIsOpen(true)}
          onKeyDown={handleKeyDown}
          disabled={disabled || isLoading}
        />
        {value && !disabled && (
          <button
            type="button"
            className="relation-select-clear"
            onClick={handleClear}
            tabIndex={-1}
          >
            ×
          </button>
        )}
      </div>

      {isOpen && !disabled && (
        <ul className="relation-select-dropdown">
          {isLoading ? (
            <li className="relation-select-loading">Loading...</li>
          ) : filtered.length === 0 ? (
            <li className="relation-select-empty">No matches</li>
          ) : (
            filtered.map((record, i) => {
              const id = record.id as string
              const label = record[displayField] as string
              return (
                <li
                  key={id}
                  className={`relation-select-option${id === value ? ' selected' : ''}${i === highlightIndex ? ' highlighted' : ''}`}
                  onMouseDown={(e) => {
                    e.preventDefault()
                    handleSelect(id)
                  }}
                  onMouseEnter={() => setHighlightIndex(i)}
                >
                  {label}
                </li>
              )
            })
          )}
        </ul>
      )}
    </div>
  )
}
