/**
 * CalendarView — presentation component for the "query/calendar" style.
 *
 * Renders records on a month grid, positioned by a date/datetime field.
 * All records are fetched at once (high page size) and filtered client-side
 * to the visible month.
 *
 * Does NOT own data fetching — receives data through props.
 */

import { useState, useMemo, useCallback } from 'react'
import type { PresentationProps } from '@/lib/viewTypes'

export interface CalendarStyleConfig {
  /** Date or datetime field used to position records on the calendar */
  dateField: string
  /** Field shown as the event label within day cells */
  titleField: string
  /** CSS color for event indicators (default: var(--brand)) */
  eventColor?: string
}

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MAX_EVENTS_PER_DAY = 3

function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
}

function isToday(d: Date): boolean {
  return sameDay(d, new Date())
}

function monthLabel(date: Date): string {
  return date.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
}

interface DayCell {
  date: Date
  isCurrentMonth: boolean
  events: Record<string, unknown>[]
}

function buildMonthGrid(year: number, month: number, events: Map<string, Record<string, unknown>[]>): DayCell[] {
  const firstDay = new Date(year, month, 1)
  const startOffset = firstDay.getDay() // 0=Sun
  const daysInMonth = new Date(year, month + 1, 0).getDate()

  const cells: DayCell[] = []

  // Previous month padding
  for (let i = startOffset - 1; i >= 0; i--) {
    const d = new Date(year, month, -i)
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    cells.push({ date: d, isCurrentMonth: false, events: events.get(key) ?? [] })
  }

  // Current month
  for (let day = 1; day <= daysInMonth; day++) {
    const d = new Date(year, month, day)
    const key = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    cells.push({ date: d, isCurrentMonth: true, events: events.get(key) ?? [] })
  }

  // Pad to complete weeks (6 rows max)
  const totalCells = Math.ceil(cells.length / 7) * 7
  for (let i = cells.length; i < totalCells; i++) {
    const d = new Date(year, month + 1, i - (startOffset + daysInMonth) + 1)
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    cells.push({ date: d, isCurrentMonth: false, events: events.get(key) ?? [] })
  }

  return cells
}

export function CalendarView({
  data,
  styleConfig,
  isLoading,
  error,
  compact,
  onRowClick,
}: PresentationProps<CalendarStyleConfig>) {
  const [currentDate, setCurrentDate] = useState(() => new Date())

  const { dateField, titleField, eventColor } = styleConfig
  const color = eventColor || 'var(--brand)'

  const year = currentDate.getFullYear()
  const month = currentDate.getMonth()

  const goToPrev = useCallback(() => {
    setCurrentDate(new Date(year, month - 1, 1))
  }, [year, month])

  const goToNext = useCallback(() => {
    setCurrentDate(new Date(year, month + 1, 1))
  }, [year, month])

  const goToToday = useCallback(() => {
    setCurrentDate(new Date())
  }, [])

  // Group events by date key (YYYY-MM-DD)
  const eventsByDate = useMemo(() => {
    const rows = data?.data ?? []
    const map = new Map<string, Record<string, unknown>[]>()

    for (const row of rows) {
      const raw = row[dateField]
      if (!raw) continue
      const d = new Date(String(raw))
      if (isNaN(d.getTime())) continue
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(row)
    }

    return map
  }, [data, dateField])

  const cells = useMemo(
    () => buildMonthGrid(year, month, eventsByDate),
    [year, month, eventsByDate],
  )

  if (isLoading) {
    return <div className="calendar-container calendar-loading">Loading...</div>
  }

  if (error) {
    return <div className="calendar-container calendar-error">{error}</div>
  }

  return (
    <div className={`calendar-container${compact ? ' compact' : ''}`}>
      {/* Header: navigation + month label */}
      <div className="calendar-header">
        <button className="calendar-nav-btn" onClick={goToPrev}>
          &larr;
        </button>
        <button className="calendar-today-btn" onClick={goToToday}>
          Today
        </button>
        <span className="calendar-month-label">{monthLabel(currentDate)}</span>
        <button className="calendar-nav-btn" onClick={goToNext}>
          &rarr;
        </button>
      </div>

      {/* Day-of-week headers */}
      <div className="calendar-weekdays">
        {WEEKDAYS.map((day) => (
          <div key={day} className="calendar-weekday">
            {day}
          </div>
        ))}
      </div>

      {/* Month grid */}
      <div className="calendar-grid">
        {cells.map((cell, i) => {
          const dayClasses = [
            'calendar-day',
            cell.isCurrentMonth ? '' : 'outside',
            isToday(cell.date) ? 'today' : '',
          ]
            .filter(Boolean)
            .join(' ')

          return (
            <div key={i} className={dayClasses}>
              <div className="calendar-day-number">{cell.date.getDate()}</div>
              {compact ? (
                /* Compact: show colored dots */
                cell.events.length > 0 && (
                  <div className="calendar-dots">
                    {cell.events.slice(0, 4).map((_, j) => (
                      <span
                        key={j}
                        className="calendar-dot"
                        style={{ backgroundColor: color }}
                      />
                    ))}
                    {cell.events.length > 4 && (
                      <span className="calendar-dot-more">+{cell.events.length - 4}</span>
                    )}
                  </div>
                )
              ) : (
                /* Full: show event titles */
                <div className="calendar-events">
                  {cell.events.slice(0, MAX_EVENTS_PER_DAY).map((event, j) => (
                    <div
                      key={j}
                      className="calendar-event"
                      style={{ borderLeftColor: color }}
                      onClick={() => onRowClick?.(event)}
                    >
                      {String(event[titleField] ?? '')}
                    </div>
                  ))}
                  {cell.events.length > MAX_EVENTS_PER_DAY && (
                    <div className="calendar-event-overflow">
                      +{cell.events.length - MAX_EVENTS_PER_DAY} more
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
