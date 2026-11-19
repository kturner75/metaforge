import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { FieldMetadata } from '@/lib/types'
import { Checkbox } from './Checkbox'
import { Select } from './Select'
import { TextArea } from './TextArea'

const ui = { component: '' }
const field: FieldMetadata = {
  name: 'question',
  displayName: 'Question',
  type: 'picklist',
  ui: { display: ui, edit: ui, filter: ui, grid: ui },
}

describe('record field labels', () => {
  it('uses the field name as the control ID for the record form label', () => {
    expect(renderToStaticMarkup(<Select field={field} value="" />)).toContain('id="question"')
    expect(renderToStaticMarkup(<TextArea field={field} value="" />)).toContain('id="question"')
    expect(renderToStaticMarkup(<Checkbox field={field} value={false} />)).toContain('id="question"')
  })
})
