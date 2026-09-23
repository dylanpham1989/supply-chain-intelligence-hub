const currency = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
})
const compact = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 })
const percent = new Intl.NumberFormat('en-US', { style: 'percent', maximumFractionDigits: 1 })
const dateFmt = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium' })

export const money = (value: string | number | null | undefined): string =>
  value == null ? '—' : currency.format(Number(value))

export const compactMoney = (value: string | number | null | undefined): string =>
  value == null ? '—' : `$${compact.format(Number(value))}`

export const rate = (value: number | null | undefined): string =>
  value == null ? '—' : percent.format(value)

export const count = (value: number | null | undefined): string =>
  value == null ? '—' : compact.format(value)

export const day = (value: string | null | undefined): string =>
  value ? dateFmt.format(new Date(value)) : '—'

export const days = (value: number | null | undefined): string =>
  value == null ? '—' : `${value.toFixed(1)}d`
