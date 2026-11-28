import { useCallback, useEffect, useState } from 'react'

type Api = (path: string, options?: RequestInit) => Promise<unknown>
type Run = {
  id: string
  status: string
  scored: number
  cursor: number
  quarantined: number
  configuration: { event_limit: number }
}
type Window = {
  id: string
  cohort: string
  start: string
  model_version: string
  sample_count: number
  status: string
  performance_degraded: boolean
  quality_rejections: number
  performance: { coverage: number; recall: number | null; false_positive_rate: number | null }
  features: Record<string, { psi: number }>
}
type Allocation = {
  configured_percent: number
  subscribers: number
  assigned_subscribers: number
  events: number
  assigned_events: number
  served_events: number
  fallback_events: number
}
type TrainingJob = {
  id: string
  kind: string
  status: string
  progress_current: number
  progress_total: number
  result?: { stage?: string; model_version?: string; decision?: string; training?: unknown }
}
type Lifecycle = { canary_allocation: Allocation; jobs: TrainingJob[] }

function percent(value: number | null) {
  return value === null ? 'Pending support' : `${(value * 100).toFixed(1)}%`
}

export function ContinuousOperations({ api, role }: { api: Api; role?: string }) {
  const [runs, setRuns] = useState<Run[] | null>(null)
  const [windows, setWindows] = useState<Window[]>([])
  const [lifecycle, setLifecycle] = useState<Lifecycle | null>(null)
  const [problems, setProblems] = useState<string[]>([])
  const [actionError, setActionError] = useState('')
  const [busy, setBusy] = useState(false)
  const [selected, setSelected] = useState('')
  const canManage = role === 'Administrator' || role === 'ML Engineer'

  const refresh = useCallback(async () => {
    const [simulator, monitor, models] = await Promise.allSettled([
      api('/simulator/runs'),
      api(`/monitoring/windows${selected ? `?cohort=${encodeURIComponent(selected)}` : ''}`),
      api('/mlops'),
    ])
    if (simulator.status === 'fulfilled') setRuns(simulator.value as Run[])
    if (monitor.status === 'fulfilled') setWindows(monitor.value as Window[])
    if (models.status === 'fulfilled') setLifecycle(models.value as Lifecycle)
    setProblems([
      ...(simulator.status === 'rejected' ? ['Simulator status unavailable'] : []),
      ...(monitor.status === 'rejected' ? ['Monitoring windows unavailable'] : []),
      ...(models.status === 'rejected' ? ['Model operations unavailable'] : []),
    ])
  }, [api, selected])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => void refresh(), 10_000)
    return () => window.clearInterval(timer)
  }, [refresh])

  async function submit(path: string, values?: object) {
    setBusy(true)
    setActionError('')
    try {
      await api(path, { method: 'POST', body: values === undefined ? undefined : JSON.stringify(values) })
      await refresh()
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'The action failed')
    } finally {
      setBusy(false)
    }
  }

  const allocation = lifecycle?.canary_allocation
  const active = runs?.some(run => ['running', 'paused'].includes(run.status))
  const durableJobs = lifecycle?.jobs.filter(job => job.kind === 'research_training' || job.kind.startsWith('retrain_'))

  return <>
    {(actionError || problems.length > 0) && <section className="panel" role="alert">
      {actionError && <p>{actionError}</p>}
      {problems.map(message => <p key={message}>{message}</p>)}
      <button type="button" className="secondary" onClick={() => void refresh()}>Refresh status</button>
    </section>}
    <section className="panel">
      <h2>Virtual telecom network</h2>
      <p>Generate synthetic events through the same validation, scoring and investigation pipeline as imported events.</p>
      {canManage && <form className="title-actions" onSubmit={event => {
        event.preventDefault()
        const form = new FormData(event.currentTarget)
        const drift = form.get('drift') === 'on'
        void submit('/simulator/runs', {
          seed: Number(form.get('seed')),
          population: Number(form.get('population')),
          rate: Number(form.get('rate')),
          event_limit: 1500,
          logical_interval_seconds: 45,
          prevalence: Number(form.get('prevalence')) / 100,
          monitor_minimum: 50,
          ...(drift ? { drift_at: 450, recover_at: 1100 } : {}),
        })
      }}>
        <label>Seed <input name="seed" type="number" min="0" max="4294967295" defaultValue="20261128" required /></label>
        <label>Subscribers <input name="population" type="number" min="24" max="20000" defaultValue="500" required /></label>
        <label>Events per tick <input name="rate" type="number" min="1" max="20" defaultValue="5" required /></label>
        <label>Experimental fraud (%) <input name="prevalence" type="number" min="0" max="20" step="0.5" defaultValue="5" required /></label>
        <label><input name="drift" type="checkbox" defaultChecked /> Schedule drift and recovery</label>
        <button className="primary" disabled={busy || active}>Start synthetic run</button>
      </form>}
      {!canManage && <p>Simulator controls require an Administrator or ML Engineer.</p>}
      {runs === null && !problems.includes('Simulator status unavailable') && <p role="status">Loading simulator runs…</p>}
      {runs?.length === 0 && <p>No synthetic runs yet.</p>}
      {!!runs?.length && <div className="table-wrap"><table>
        <thead><tr><th>Run</th><th>Status</th><th>Processed</th><th>Scored</th><th>Quarantined</th><th>Controls</th></tr></thead>
        <tbody>{runs.map(run => <tr key={run.id}>
          <td><button className="text-btn" onClick={() => setSelected(run.id)}>{run.id.slice(0, 8)}</button></td>
          <td>{run.status}</td><td>{run.cursor} / {run.configuration.event_limit}</td><td>{run.scored}</td><td>{run.quarantined}</td>
          <td>{canManage && ['running', 'paused'].includes(run.status) && <>
            <button className="secondary" disabled={busy} onClick={() => void submit(`/simulator/runs/${run.id}/${run.status === 'running' ? 'pause' : 'resume'}`)}>
              {run.status === 'running' ? 'Pause' : 'Resume'}
            </button>
            <button className="secondary" disabled={busy} onClick={() => void submit(`/simulator/runs/${run.id}/stop`)}>Stop</button>
          </>}</td>
        </tr>)}</tbody>
      </table></div>}
    </section>
    <section className="panel">
      <h2>Served-traffic monitoring</h2>
      <label>Traffic cohort <select value={selected} onChange={event => setSelected(event.target.value)}>
        <option value="">All cohorts</option><option value="live">Live API</option><option value="csv">CSV imports</option>
        {runs?.map(run => <option key={run.id} value={run.id}>Simulator {run.id.slice(0, 8)}</option>)}
      </select></label>
      {!windows.length && <p>No completed windows for this selection.</p>}
      {!!windows.length && <div className="table-wrap"><table>
        <thead><tr><th>Window start</th><th>Model</th><th>Samples</th><th>Distribution</th><th>Highest PSI</th><th>Label coverage</th><th>Recall</th><th>Quality rejects</th></tr></thead>
        <tbody>{windows.map(item => <tr key={item.id}>
          <td>{new Date(item.start).toLocaleString()}</td><td>{item.model_version}</td><td>{item.sample_count}</td>
          <td>{item.status.replaceAll('_', ' ')}{item.performance_degraded && ' · supported degradation'}</td>
          <td>{Object.values(item.features).length ? Math.max(...Object.values(item.features).map(feature => feature.psi)).toFixed(3) : 'Unavailable'}</td>
          <td>{percent(item.performance.coverage)}</td><td>{percent(item.performance.recall)}</td><td>{item.quality_rejections}</td>
        </tr>)}</tbody>
      </table></div>}
    </section>
    <section className="panel">
      <h2>Training and rollout</h2>
      {canManage && <button className="secondary" disabled={busy} onClick={() => void submit('/datasets/research-training', { seed: 20261128 })}>Queue research training</button>}
      {allocation && <p>
        Canary configured {allocation.configured_percent}%. Assigned {allocation.assigned_subscribers} of {allocation.subscribers} eligible subscribers.
        {' '}Assigned {allocation.assigned_events} of {allocation.events} events, served {allocation.served_events}, fell back {allocation.fallback_events}.
      </p>}
      {!!durableJobs?.length && <ul>{durableJobs.map(job => <li key={job.id}>
        {job.kind.replaceAll('_', ' ')} · {job.status} · {job.result?.stage ?? 'Waiting'} · {job.progress_current}/{job.progress_total}
        {job.result?.decision && ` · ${job.result.decision.replaceAll('_', ' ')}`}
        {canManage && ['Administrator', 'ML Engineer'].includes(role || '') &&
          ['queued', 'running', 'paused'].includes(job.status) &&
          <button className="secondary" disabled={busy} onClick={() => void submit(`/jobs/${job.id}/control`, { action: 'stop' })}>Cancel before publish</button>}
      </li>)}</ul>}
    </section>
  </>
}
