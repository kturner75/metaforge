import type { ValidationErrorItem } from '@/lib/api'

interface WarningDialogProps {
  warnings: ValidationErrorItem[]
  onProceed: () => void
  onCancel: () => void
  isPending?: boolean
}

export function WarningDialog({ warnings, onProceed, onCancel, isPending }: WarningDialogProps) {
  return (
    <div className="warning-dialog-overlay">
      <div className="warning-dialog">
        <div className="warning-dialog-header">
          <span className="warning-dialog-icon">!</span>
          <h3>Review Warnings</h3>
        </div>

        <p className="warning-dialog-description">
          The following warnings were found. You can proceed with saving or go back to make changes.
        </p>

        <ul className="warning-dialog-list">
          {warnings.map((w, i) => (
            <li key={i} className="warning-dialog-item">
              <span className="warning-dialog-message">{w.message}</span>
              {w.field && <span className="warning-dialog-field">{w.field}</span>}
            </li>
          ))}
        </ul>

        <div className="warning-dialog-actions">
          <button type="button" onClick={onCancel} disabled={isPending}>
            Go Back
          </button>
          <button type="button" className="warning-proceed" onClick={onProceed} disabled={isPending}>
            {isPending ? 'Saving...' : 'Save Anyway'}
          </button>
        </div>
      </div>
    </div>
  )
}
