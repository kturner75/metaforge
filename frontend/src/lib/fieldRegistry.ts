/**
 * Field component registry - maps field types to React components.
 */

import type { ComponentType } from 'react'
import type { FieldComponentProps, UIContext } from './types'
import {
  Text,
  TextInput,
  TextArea,
  Select,
  Badge,
  RelationSelect,
  Checkbox,
  NumberInput,
  CurrencyInput,
  DatePicker,
  DateTimePicker,
  DateDisplay,
  NumberDisplay,
  BooleanBadge,
  UrlLink,
  MultiPicklistBadges,
} from '@/components/fields'

type FieldComponent = ComponentType<FieldComponentProps<any>>

type Registry = Record<string, Record<UIContext, FieldComponent>>

const registry: Registry = {
  uuid: {
    display: Text,
    edit: TextInput,
    filter: TextInput,
    grid: Text,
  },
  string: {
    display: Text,
    edit: TextInput,
    filter: TextInput,
    grid: Text,
  },
  name: {
    display: Text,
    edit: TextInput,
    filter: TextInput,
    grid: Text,
  },
  text: {
    display: Text,
    edit: TextArea,
    filter: TextInput,
    grid: Text,
  },
  description: {
    display: Text,
    edit: TextArea,
    filter: TextInput,
    grid: Text,
  },
  email: {
    display: Text,
    edit: TextInput,
    filter: TextInput,
    grid: Text,
  },
  phone: {
    display: Text,
    edit: TextInput,
    filter: TextInput,
    grid: Text,
  },
  url: {
    display: UrlLink,
    edit: TextInput,
    filter: TextInput,
    grid: UrlLink,
  },
  picklist: {
    display: Badge,
    edit: Select,
    filter: Select,
    grid: Badge,
  },
  multi_picklist: {
    display: MultiPicklistBadges,
    edit: Select,
    filter: Select,
    grid: MultiPicklistBadges,
  },
  relation: {
    display: Text,
    edit: RelationSelect,
    filter: RelationSelect,
    grid: Text,
  },
  date: {
    display: DateDisplay,
    edit: DatePicker,
    filter: DatePicker,
    grid: DateDisplay,
  },
  datetime: {
    display: DateDisplay,
    edit: DateTimePicker,
    filter: DateTimePicker,
    grid: DateDisplay,
  },
  number: {
    display: NumberDisplay,
    edit: NumberInput,
    filter: NumberInput,
    grid: NumberDisplay,
  },
  currency: {
    display: NumberDisplay,
    edit: CurrencyInput,
    filter: NumberInput,
    grid: NumberDisplay,
  },
  percent: {
    display: NumberDisplay,
    edit: NumberInput,
    filter: NumberInput,
    grid: NumberDisplay,
  },
  boolean: {
    display: BooleanBadge,
    edit: Checkbox,
    filter: Select,
    grid: BooleanBadge,
  },
  checkbox: {
    display: BooleanBadge,
    edit: Checkbox,
    filter: Select,
    grid: BooleanBadge,
  },
  address: {
    display: Text,
    edit: TextArea,
    filter: TextInput,
    grid: Text,
  },
  attachment: {
    display: UrlLink,
    edit: TextInput,
    filter: TextInput,
    grid: UrlLink,
  },
}

export function getFieldComponent(type: string, context: UIContext): FieldComponent {
  return registry[type]?.[context] ?? registry.string[context]
}

export function registerFieldComponent(
  type: string,
  context: UIContext,
  component: FieldComponent
): void {
  if (!registry[type]) {
    registry[type] = { ...registry.string }
  }
  registry[type][context] = component
}
