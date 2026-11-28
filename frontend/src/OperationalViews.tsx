import { useEffect, useState } from 'react';

type Props = { api: (path: string, options?: RequestInit) => Promise<any>; token: string; user: { role: string } | null; setError: (message: string) => void; view: 'Data observatory' | 'Live monitoring'; onNavigate: (view: string) => void };
const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
function safeUploadError(status: number) {
  if (status === 401) return 'Your session is invalid or expired. Sign in again.'
  if (status === 403) return 'You do not have permission to upload events.'
  if (status === 409) return 'The upload conflicts with existing event IDs. No conflicting batch was accepted.'
  if (status === 413) return 'The selected file exceeds the upload limit.'
  if (status === 422) return 'The CSV was rejected. Check its event-v1 fields and allowed values.'
  if (status >= 500) return 'The upload service is temporarily unavailable. Retry later.'
  return 'The CSV upload could not be completed.'
}

export function OperationalViews({ api, token, user, setError, view, onNavigate }: Props) {
  const [data, setData] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [metrics, setMetrics] = useState<any>(null);
  const [job, setJob] = useState<any>(null);
  const [starting, setStarting] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const admin = user?.role === 'Administrator';
  const canIngest = ['Administrator', 'Fraud Analyst', 'Investigator', 'ML Engineer'].includes(user?.role || '');
  async function load() {
    try {
      if (view === 'Data observatory') setData(await api('/data/observatory'));
      else { const [h, m] = await Promise.all([api('/system/health'), api('/system/metrics')]); setHealth(h); setMetrics(m); }
    } catch (e: any) { setError(e.message); }
  }
  useEffect(() => { load(); const timer = window.setInterval(load, 5000); return () => window.clearInterval(timer); }, [view]);
  useEffect(() => {
    if (!job || ['succeeded', 'failed', 'stopped'].includes(job.status)) return;
    const timer = window.setInterval(async () => { try { const next = await api(`/jobs/${job.id}`); setJob(next); if (['succeeded', 'failed', 'stopped'].includes(next.status)) load(); } catch (e: any) { setError(e.message); } }, 2000);
    return () => window.clearInterval(timer);
  }, [job?.id, job?.status]);
  async function seed() { setStarting(true); try { const queued = await api('/datasets/seed', { method: 'POST', body: JSON.stringify({ count: 150000, seed: 20261119 }) }); setJob(await api(`/jobs/${queued.job_id}`)); } catch (e: any) { setError(e.message); } finally { setStarting(false); } }
  async function control(action: string) { if (!job) return; try { await api(`/jobs/${job.id}/control`, { method: 'POST', body: JSON.stringify({ action }) }); setJob(await api(`/jobs/${job.id}`)); } catch (e: any) { setError(e.message); } }
  async function upload() { if (!file) return; try { let res: Response; try { res = await fetch(`${API}/events/upload-csv`, { method: 'POST', headers: { 'Content-Type': 'text/csv', Authorization: `Bearer ${token}` }, body: file }); } catch { throw Error('The API service cannot be reached. Check connectivity or retry.'); } if (!res.ok) throw Error(safeUploadError(res.status)); setData(await api('/data/observatory')); setFile(null); } catch (e: any) { setError(e instanceof Error ? e.message : 'The CSV upload could not be completed.'); } }
  return <>
    <section className="panel"><div className="panel-head"><div><h2>Operational data and service status</h2><p>Counts and health are read from persisted PostgreSQL and service heartbeat data.</p></div><select aria-label="Operational view" value={view} onChange={e => onNavigate(e.target.value)}><option>Data observatory</option><option>Live monitoring</option></select></div>
      {view === 'Data observatory' && <>
        {data && <><div className="metrics"><div className="metric"><span>Persisted events</span><strong>{data.events.toLocaleString()}</strong></div><div className="metric"><span>Predictions</span><strong>{data.predictions.toLocaleString()}</strong></div><div className="metric"><span>Incidents</span><strong>{data.incidents.toLocaleString()}</strong></div><div className="metric"><span>Dataset versions</span><strong>{data.datasets.length}</strong></div></div>
        <h3>Versioned datasets</h3><div className="table-wrap"><table><thead><tr><th>Version</th><th>Kind</th><th>Rows / target</th><th>Status</th><th>Seed</th></tr></thead><tbody>{data.datasets.map((d: any) => <tr key={d.version}><td className="mono">{d.version}</td><td>{d.kind}</td><td>{d.rows.toLocaleString()} / {d.target_rows.toLocaleString()}</td><td>{d.status}</td><td>{d.seed}</td></tr>)}</tbody></table>{!data.datasets.length && <p>No operational dataset version has been generated yet.</p>}</div>
        <h3>Event types and labels</h3><div className="table-wrap"><table><thead><tr><th>Event type</th><th>Rows</th></tr></thead><tbody>{data.event_types.map((x: any) => <tr key={x.event_type}><td>{x.event_type}</td><td>{x.rows.toLocaleString()}</td></tr>)}</tbody></table></div>
        <h3>Missing-value rates</h3><div className="table-wrap"><table><thead><tr><th>Field</th><th>Missing rows</th><th>Rate</th></tr></thead><tbody>{Object.entries(data.missing_values).map(([key, v]: any) => <tr key={key}><td>{key}</td><td>{v.count.toLocaleString()}</td><td>{(v.rate * 100).toFixed(2)}%</td></tr>)}</tbody></table></div></>}
        {admin && <><h3>Initial dataset generation</h3><p>Create a reproducible 150,000-event dataset, persist and score it in batches, and train/register a candidate from that exact dataset.</p><button className="primary" disabled={starting || (job && !['succeeded', 'failed', 'stopped'].includes(job.status))} onClick={seed}>{starting ? 'Queueing…' : 'Generate 150,000 events'}</button>{job && <div className="evidence"><b>Job {job.status}</b><small>{job.progress_current?.toLocaleString()} / {job.progress_total?.toLocaleString()} rows {job.error ? `· ${job.error}` : ''}</small>{job.progress_current >= job.progress_total && job.status === 'running' && <small>Data is persisted; model training and registration are running.</small>}{!['succeeded','failed','stopped'].includes(job.status) && job.progress_current < job.progress_total && <span><button className="secondary" onClick={() => control(job.status === 'paused' ? 'resume' : 'pause')}>{job.status === 'paused' ? 'Resume' : 'Pause'}</button> <button className="secondary" onClick={() => control('stop')}>Stop</button></span>}</div>}</>}
        {canIngest && <><h3>CSV event ingestion</h3><p>Upload UTF-8 CSV with event-v1 fields; file limit 25 MB and 5,000 validated rows per request.</p><input type="file" accept=".csv,text/csv" onChange={e => setFile(e.target.files?.[0] || null)}/><button className="secondary" disabled={!file} onClick={upload}>Validate, score and persist CSV</button></>}
      </>}
      {view === 'Live monitoring' && <>{health && <><div className="metrics">{['api','database','worker','mlflow'].map(k => <div className="metric" key={k}><span>{k}</span><strong>{health[k]?.status}</strong></div>)}</div><p>Overall status: <b>{health.status}</b>{health.worker?.last_seen_seconds != null ? ` · worker heartbeat ${health.worker.last_seen_seconds.toFixed(1)}s ago` : ''}</p></>}{metrics && <><h3>Persisted totals</h3><pre>{JSON.stringify(metrics.persisted, null, 2)}</pre><h3>Ingestion and API process</h3><pre>{JSON.stringify({ ingestion: metrics.ingestion, api_process: metrics.api_process }, null, 2)}</pre></>}</>}
    </section>
  </>;
}
