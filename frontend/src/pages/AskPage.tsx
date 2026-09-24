import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { insights } from '../api'
import { Badge, Button, Card, EmptyState, Input, Skeleton } from '../components/ui'
import { ShipmentStatusBadge } from '../components/ui/status'
import { useAuth } from '../hooks/auth-context'
import { can } from '../lib/permissions'
import { day, money } from '../lib/format'
import { qk } from '../lib/query-keys'
import type { AskResponse } from '../types'

const EXAMPLES = [
  'What is the penalty for late delivery?',
  'What are the payment terms?',
  'How many shipments were delayed?',
  'Show all late deliveries to the EU',
]

export default function AskPage() {
  const { user } = useAuth()
  const client = useQueryClient()
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<AskResponse | null>(null)

  const ask = useMutation({
    mutationFn: (q: string) => insights.ask(q),
    onSuccess: (result) => {
      setAnswer(result)
      void client.invalidateQueries({ queryKey: ['insights'] })
    },
  })

  const history = useQuery({ queryKey: qk.insights(1), queryFn: () => insights.history(1) })
  const allowed = can(user?.role, 'insight:create')

  function submit(event: FormEvent) {
    event.preventDefault()
    if (question.trim().length >= 3) ask.mutate(question.trim())
  }

  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">Ask</h1>
        <p className="text-sm text-(--color-ink-muted)">
          Questions about wording are answered from the documents. Questions that count something
          are answered from the shipment table.
        </p>
      </header>

      <Card>
        <form onSubmit={submit} className="flex flex-wrap gap-2">
          <Input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="What is the penalty for late delivery?"
            maxLength={1000}
            className="min-w-60 flex-1"
            disabled={!allowed}
          />
          <Button type="submit" disabled={!allowed || ask.isPending || question.trim().length < 3}>
            {ask.isPending ? 'Searching' : 'Ask'}
          </Button>
        </form>

        {!allowed && (
          <p className="mt-3 text-sm text-(--color-ink-muted)">
            Your role can read past answers but not ask new ones.
          </p>
        )}

        <div className="mt-3 flex flex-wrap gap-2">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              disabled={!allowed}
              onClick={() => {
                setQuestion(example)
                ask.mutate(example)
              }}
              className="rounded-full bg-black/5 px-3 py-1 text-xs text-(--color-ink-muted) hover:bg-black/10 disabled:opacity-50 dark:bg-white/10 dark:hover:bg-white/15"
            >
              {example}
            </button>
          ))}
        </div>
      </Card>

      {ask.isPending && (
        <Card>
          <p className="mb-3 text-sm text-(--color-ink-muted)">Searching the indexed documents…</p>
          <Skeleton className="h-4 w-full" />
          <Skeleton className="mt-2 h-4 w-4/5" />
        </Card>
      )}

      {ask.isError && (
        <Card>
          <p role="alert" className="text-sm text-(--color-bad)">
            {(ask.error as Error).message}
          </p>
        </Card>
      )}

      {answer && !ask.isPending && <AnswerCard answer={answer} />}

      <Card title="Recent questions">
        {history.isPending ? (
          <Skeleton className="h-20 w-full" />
        ) : !history.data?.items.length ? (
          <EmptyState title="Nothing asked yet" hint="Try one of the examples above." />
        ) : (
          <ul className="flex flex-col divide-y divide-black/5">
            {history.data.items.slice(0, 8).map((item) => (
              <li key={item.id} className="flex items-baseline justify-between gap-3 py-2 text-sm">
                <span>{item.question}</span>
                <span className="shrink-0 text-xs text-(--color-ink-muted)">
                  {item.route} · {item.latency_ms ?? 0}ms
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}

function AnswerCard({ answer }: { answer: AskResponse }) {
  return (
    <Card
      title="Answer"
      action={
        <div className="flex items-center gap-2">
          <Badge tone={answer.route === 'structured' ? 'ok' : 'neutral'}>{answer.route}</Badge>
          <span className="text-xs text-(--color-ink-muted)">{answer.total_ms}ms</span>
        </div>
      }
    >
      {/* Plain text, deliberately. Rendering model output as html would let an
          uploaded document decide what runs in the browser. */}
      <p className="whitespace-pre-wrap">{answer.answer}</p>

      {answer.citations.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-2 text-xs tracking-wide text-(--color-ink-muted) uppercase">Sources</h3>
          <ul className="flex flex-wrap gap-2">
            {answer.citations.map((citation) => (
              <li
                key={citation.number}
                className="rounded-lg bg-(--color-surface) px-2 py-1 text-xs ring-1 ring-black/10"
              >
                <span className="font-medium">[{citation.number}]</span> {citation.filename}
                {citation.page_no ? ` · p${citation.page_no}` : ''}
                {citation.section ? ` · ${citation.section}` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}

      {answer.shipments.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-black/10 text-left text-xs text-(--color-ink-muted) uppercase">
                <th scope="col" className="px-2 py-1.5">
                  Reference
                </th>
                <th scope="col" className="px-2 py-1.5">
                  Lane
                </th>
                <th scope="col" className="px-2 py-1.5">
                  ETA
                </th>
                <th scope="col" className="px-2 py-1.5 text-right">
                  Value
                </th>
                <th scope="col" className="px-2 py-1.5">
                  Status
                </th>
              </tr>
            </thead>
            <tbody>
              {answer.shipments.slice(0, 25).map((shipment) => (
                <tr key={shipment.id} className="border-b border-black/5">
                  <td className="px-2 py-1.5 font-medium">{shipment.reference}</td>
                  <td className="px-2 py-1.5">
                    {shipment.origin_country} → {shipment.dest_country}
                  </td>
                  <td className="px-2 py-1.5">{day(shipment.eta)}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">
                    {money(shipment.value_usd)}
                  </td>
                  <td className="px-2 py-1.5">
                    <ShipmentStatusBadge status={shipment.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {answer.shipments.length > 25 && (
            <p className="mt-2 text-xs text-(--color-ink-muted)">
              Showing 25 of {answer.shipments.length}.
            </p>
          )}
        </div>
      )}
    </Card>
  )
}
