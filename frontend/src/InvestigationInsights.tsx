import { useEffect, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import './investigation-insights.css';

type Api = (path: string, options?: RequestInit) => Promise<any>;
type User = { role: string } | null;
type Adjudication = { id: number; incident_id: number | null; outcome: string; reason: string; reviewer: string; reviewed_at: string; source: string; correction_of: number | null };
type CorrelatedEvent = { event_id: string; event_type: string; event_time: string; subscriber_id: string; device_id: string | null; network_token: string | null; risk_score: number; model_version: string; decision: string };
type Consolidation = { id: number; source_id: number; target_id: number; reason: string; actor: string; active: boolean; reversed_by: string | null; reversal_reason: string | null };
type Timeline = {
  events: CorrelatedEvent[];
  adjudications: Adjudication[];
  consolidations: Consolidation[];
  notes: { id: number; incident_id: number; author: string; body: string }[];
  actions: { id: number; incident_id: number; actor: string; action: string; reverses_id: number | null }[];
  truncated: boolean;
};
type ReviewQueueResult = {
  population: number;
  eligible_low_risk: number;
  events: { event_id: string; risk_score: number; sampling: string }[];
};
type Metrics = {
  investigations: number; cases_per_1000_events: number; false_positive_cases: number;
  unlabeled_cases: number; fraud_episodes_detected: number; fraud_episodes_total: number;
  fraud_episodes_at_budget: number; reviewed_cases: number; labeled_reviewed_cases: number;
  precision_at_budget: number | null; median_seconds_to_first_alert: number | null;
  cases_spanning_multiple_episodes: number;
  by_fraud_family: Record<string, { episodes: number; detected: number; recall: number; at_budget: number }>;
};
type Impact = {
  event_count: number; alerts_evaluated: number; duplicate_alert_reduction: number | null;
  one_alert_per_event: Metrics; correlated: Metrics; episode_definition: string;
  review_definition: string; sample_truncated: boolean;
  live_resolution: { case_count: number; median_seconds: number | null };
};

const reviewRoles = ['Administrator', 'Fraud Analyst', 'Investigator'];
const changeRoles = ['Administrator', 'Investigator'];
const outcomes = {
  confirmed_fraud: 'Confirmed synthetic fraud',
  legitimate: 'Legitimate activity',
  false_positive: 'False-positive disposition',
  inconclusive: 'Inconclusive',
  duplicate: 'Duplicate',
};

function failure(error: unknown) {
  return error instanceof Error ? error.message : 'Request failed.';
}

function useResource<T>(api: Api, path: string | null, version: number) {
  const [state, setState] = useState<{ data: T | null; error: string; path: string | null; version: number }>({
    data: null, error: '', path: null, version: 0,
  });
  useEffect(() => {
    if (!path) return;
    let active = true;
    const controller = new AbortController();
    api(path, { signal: controller.signal }).then(
      data => { if (active) setState({ data, error: '', path, version }); },
      error => { if (active) setState({ data: null, error: failure(error), path, version }); },
    );
    return () => { active = false; controller.abort(); };
  }, [api, path, version]);
  if (state.path !== path || state.version !== version) return { data: null, error: '' };
  return state;
}

function AdjudicationForm({ submit, latest, disabled }: {
  submit: (body: { outcome: string; reason: string; correction_of?: number; request_id: string }) => Promise<void>;
  latest?: Adjudication; disabled?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState<{ id: string; fingerprint: string } | null>(null);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    const outcome = String(fields.get('outcome'));
    const reason = String(fields.get('reason')).trim();
    const fingerprint = JSON.stringify([outcome, reason, latest?.id]);
    const id = retry?.fingerprint === fingerprint ? retry.id : crypto.randomUUID();
    setRetry({ id, fingerprint });
    setBusy(true);
    setError('');
    try {
      await submit({ outcome, reason, correction_of: latest?.id, request_id: id });
      form.reset();
      setRetry(null);
    } catch (err) { setError(failure(err)); }
    finally { setBusy(false); }
  }
  return <form className="insight-form" onSubmit={save}>
    {latest && <p className="muted">This corrects adjudication {latest.id} recorded by {latest.reviewer}.</p>}
    <label>Reviewed outcome <select name="outcome" defaultValue="" required>
      <option value="">Choose outcome</option>
      {Object.entries(outcomes).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
    </select></label>
    <label>Evidence or rationale <textarea name="reason" rows={2} required minLength={5} maxLength={1000}/></label>
    <button className="secondary" disabled={busy || disabled}>{busy ? 'Saving…' : latest ? 'Record correction' : 'Record adjudication'}</button>
    {error && <p className="error" role="alert">{error}</p>}
  </form>;
}

function ReviewHistory({ reviews }: { reviews: Adjudication[] }) {
  if (!reviews.length) return <p className="muted">No adjudication has been recorded.</p>;
  return <ul className="insight-list">{reviews.map(review => <li key={review.id}>
    <strong>{outcomes[review.outcome as keyof typeof outcomes] ?? review.outcome}</strong>
    <span>{review.reason}</span>
    <small>{review.reviewer} · {new Date(review.reviewed_at).toLocaleString()}{review.correction_of ? ` · Corrects ${review.correction_of}` : ''}</small>
  </li>)}</ul>;
}

export function InvestigationInsights({ api, incidentId, status, user, onChanged }: {
  api: Api; incidentId: number; status: string; user: User; onChanged: () => void;
}) {
  const [selectedEvent, setSelectedEvent] = useState('');
  const [version, setVersion] = useState(0);
  const [change, setChange] = useState('');
  const [busy, setBusy] = useState(false);
  const [changeError, setChangeError] = useState('');
  const [notice, setNotice] = useState('');
  const path = `/incidents/${incidentId}`;
  const timeline = useResource<Timeline>(api, `${path}/timeline`, version);
  const eventPath = selectedEvent ? `/predictions/${encodeURIComponent(selectedEvent)}/adjudications` : null;
  const eventReviews = useResource<Adjudication[]>(api, eventPath, version);
  const reviews = selectedEvent ? eventReviews.data : timeline.data?.adjudications.filter(review => review.incident_id === incidentId);
  const canReview = reviewRoles.includes(user?.role ?? '');
  const canChangeCase = changeRoles.includes(user?.role ?? '');
  const activeSources = (timeline.data?.consolidations ?? []).filter(item => item.active && item.target_id === incidentId);
  const activeParent = (timeline.data?.consolidations ?? []).find(item => item.active && item.source_id === incidentId);
  async function changeCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    const reason = String(fields.get('reason')).trim();
    setChangeError('');
    setBusy(true);
    try {
      if (change === 'merge') {
        await api(`${path}/merge`, { method: 'POST', body: JSON.stringify({ source_id: Number(fields.get('source')), reason }) });
      } else if (change === 'unmerge') {
        await api(`/incidents/${Number(fields.get('source'))}/unmerge`, { method: 'POST', body: JSON.stringify({ reason }) });
      } else if (change === 'reopen') {
        await api(`${path}/reopen`, { method: 'POST', body: JSON.stringify({ reason }) });
      }
      setVersion(value => value + 1);
      onChanged();
      form.reset();
      setChange('');
      setNotice('Case change recorded.');
    } catch (error) { setChangeError(failure(error)); }
    finally { setBusy(false); }
  }
  return <div className="investigation-insights">
    <h3>Correlated event timeline</h3>
    {timeline.error && <p className="error" role="alert">{timeline.error} <button type="button" className="text-btn" onClick={() => setVersion(value => value + 1)}>Retry</button></p>}
    {!timeline.error && !timeline.data && <p role="status">Loading case evidence…</p>}
    {timeline.data && <>
      {!timeline.data.events.length && <p className="muted">This case has no linked evidence.</p>}
      <ol className="insight-list">{timeline.data.events.map(item => <li key={item.event_id}>
        <div className="insight-row"><strong>{item.event_type} · {item.event_id}</strong><span>{(item.risk_score * 100).toFixed(0)}% risk</span></div>
        <span>{item.subscriber_id} · {item.decision.replaceAll('_', ' ')}</span>
        <small>{new Date(item.event_time).toLocaleString()} · {item.model_version}
          {item.device_id ? ` · Device ${item.device_id}` : ''}{item.network_token ? ` · Network ${item.network_token}` : ''}</small>
      </li>)}</ol>
      {timeline.data.truncated && <p className="muted">Additional evidence is available on linked source cases.</p>}
      <h3>Analyst adjudication</h3>
      <div className="insight-form">
        <label>Review scope <select value={selectedEvent} onChange={event => setSelectedEvent(event.target.value)}>
          <option value="">Case disposition</option>
          {timeline.data.events.map(event => <option key={event.event_id}>{event.event_id}</option>)}
        </select></label>
      </div>
      {selectedEvent && eventReviews.error && <p className="error" role="alert">{eventReviews.error}</p>}
      {reviews && <><ReviewHistory reviews={reviews}/>
        {canReview && <AdjudicationForm key={selectedEvent || 'case'} latest={reviews[0]}
          submit={async body => {
            await api(eventPath ?? `${path}/adjudications`, { method: 'POST', body: JSON.stringify(body) });
            setVersion(value => value + 1);
          }}/>}
      </>}
      {timeline.data.consolidations.length > 0 && <>
        <h3>Consolidation history</h3>
        <ul className="insight-list">{timeline.data.consolidations.map(item => <li key={item.id}>
          <strong>Case {item.source_id} → Case {item.target_id}</strong>
          <span>{item.reason} · {item.actor}</span>
          <small>{item.active ? 'Active' : `Reversed by ${item.reversed_by} · ${item.reversal_reason}`}</small>
        </li>)}</ul>
        {timeline.data.notes.filter(note => note.incident_id !== incidentId).map(note => <p className="note" key={note.id}>
          Case {note.incident_id} · {note.author} — {note.body}
        </p>)}
        {timeline.data.actions.filter(action => action.incident_id !== incidentId).map(action => <p className="note" key={action.id}>
          Case {action.incident_id} · {action.actor} — {action.action}{action.reverses_id ? ` · Reverses action ${action.reverses_id}` : ''}
        </p>)}
      </>}
      {canChangeCase && <form className="insight-form" onSubmit={changeCase}>
        <label>Case operation <select value={change} onChange={event => setChange(event.target.value)}>
          <option value="">Choose operation</option>
          {!activeParent && <option value="merge">Consolidate a related case</option>}
          {(activeSources.length > 0 || activeParent) && <option value="unmerge">Reverse consolidation</option>}
          {['Resolved', 'False Positive'].includes(status) && !activeParent && <option value="reopen">Reopen closed case</option>}
        </select></label>
        {change === 'merge' && <label>Source case ID <input name="source" type="number" min={1} required/></label>}
        {change === 'unmerge' && <label>Consolidated source <select name="source">
          {(activeParent ? [activeParent] : activeSources).map(item => <option key={item.id} value={item.source_id}>Case {item.source_id}</option>)}
        </select></label>}
        {change && <><label>Reason <textarea name="reason" rows={2} required minLength={5} maxLength={1000}/></label>
          <button type="submit" className="secondary" disabled={busy}>Apply case change</button></>}
        {changeError && <p className="error" role="alert">{changeError}</p>}
        {notice && <p role="status">{notice}</p>}
      </form>}
    </>}
  </div>;
}

export function ReviewSampling({ api, user }: { api: Api; user: User }) {
  const canReview = reviewRoles.includes(user?.role ?? '');
  const [open, setOpen] = useState(false);
  const [version, setVersion] = useState(0);
  const [selected, setSelected] = useState('');
  const [notice, setNotice] = useState('');
  const queue = useResource<ReviewQueueResult>(api, open && canReview ? '/review/queue' : null, version);
  const selectedRow = queue.data?.events.find(row => row.event_id === selected);
  if (!canReview) return null;
  return <section className="panel insights-panel">
    <div className="panel-head"><div><h2>Feedback review sample</h2><p>Review seeded low-risk samples and events near the alert threshold.</p></div>
      <button className="secondary" type="button" aria-expanded={open} onClick={() => setOpen(value => !value)}>{open ? 'Hide sample' : 'Load review sample'}</button>
    </div>
    {open && <div className="insights-body">
      {queue.error && <p className="error" role="alert">{queue.error}</p>}
      {!queue.data && !queue.error && <p role="status">Loading review sample…</p>}
      {queue.data && <>
        <p>{queue.data.population.toLocaleString()} eligible predictions · {queue.data.eligible_low_risk.toLocaleString()} low-risk predictions</p>
        {queue.data.events.length > 0 ? <div className="insight-form"><label>Sampled event <select value={selected} onChange={event => setSelected(event.target.value)}>
          <option value="">Choose event</option>
          {queue.data.events.map(item => <option key={item.event_id} value={item.event_id}>{item.event_id} · {item.sampling.replaceAll('_', ' ')} · {(item.risk_score * 100).toFixed(0)}% risk</option>)}
        </select></label></div> : <p className="muted">No eligible events are available for review.</p>}
        {selectedRow && <AdjudicationForm key={selectedRow.event_id} submit={async body => {
          await api(`/predictions/${encodeURIComponent(selectedRow.event_id)}/adjudications`, { method: 'POST', body: JSON.stringify(body) });
          setSelected('');
          setVersion(value => value + 1);
          setNotice('Event adjudication recorded.');
        }}/>}
      </>}
      {notice && <p role="status">{notice}</p>}
    </div>}
  </section>;
}

function formatNumber(value: number | null, decimals = 0) {
  return value == null ? 'Unavailable' : value.toLocaleString(undefined, { maximumFractionDigits: decimals });
}
function percentage(value: number | null) {
  return value == null ? 'Unavailable' : `${(100 * value).toFixed(1)}%`;
}

export function InvestigationImpact({ api }: { api: Api }) {
  const [dataset, setDataset] = useState('');
  const [budget, setBudget] = useState(100);
  const [version, setVersion] = useState(0);
  const params = new URLSearchParams({ review_budget: String(budget) });
  if (dataset) params.set('dataset_version', dataset);
  const { data, error } = useResource<Impact>(api, `/analytics/impact?${params}`, version);
  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    setDataset(String(values.get('dataset') ?? '').trim());
    setBudget(Number(values.get('budget')));
    setVersion(value => value + 1);
  }
  const comparisons: [string, (metric: Metrics) => ReactNode][] = [
    ['Investigations', metric => formatNumber(metric.investigations)],
    ['Cases per 1,000 events', metric => formatNumber(metric.cases_per_1000_events, 1)],
    ['Confirmed false-positive cases', metric => formatNumber(metric.false_positive_cases)],
    ['Cases with unknown outcome', metric => formatNumber(metric.unlabeled_cases)],
    ['Fraud episodes detected', metric => `${formatNumber(metric.fraud_episodes_detected)} / ${formatNumber(metric.fraud_episodes_total)}`],
    ['Fraud episodes covered at budget', metric => formatNumber(metric.fraud_episodes_at_budget)],
    ['Precision at review budget', metric => percentage(metric.precision_at_budget)],
    ['Reviewed cases with known outcome', metric => `${formatNumber(metric.labeled_reviewed_cases)} / ${formatNumber(metric.reviewed_cases)}`],
    ['Median seconds to first alert', metric => formatNumber(metric.median_seconds_to_first_alert, 1)],
    ['Cases spanning multiple episodes', metric => formatNumber(metric.cases_spanning_multiple_episodes)],
  ];
  return <section className="panel insights-panel">
    <div className="panel-head"><div><h2>Investigation impact</h2><p>Compare both alert policies on identical persisted synthetic events.</p></div></div>
    <div className="insights-body">
      <form className="insight-form insight-filter" onSubmit={applyFilters}>
        <label>Dataset version <input name="dataset" placeholder="All datasets" maxLength={120}/></label>
        <label>Review budget <input name="budget" type="number" min={1} max={10000} defaultValue={budget} required/></label>
        <button className="secondary">Run comparison</button>
      </form>
      {error && <p role="alert" className="error">{error}</p>}
      {!error && !data && <p role="status">Calculating investigation workload…</p>}
      {data && data.event_count === 0 && <p className="muted">No persisted predictions match this filter.</p>}
      {data && data.event_count > 0 && <>
        <p>{formatNumber(data.event_count)} scored events{data.sample_truncated ? ' in the latest bounded sample' : ''} · {percentage(data.duplicate_alert_reduction)} fewer investigations in correlated replay</p>
        <div className="table-wrap"><table><thead><tr><th>Measure</th><th>One alert per event</th><th>Correlated</th></tr></thead>
          <tbody>{comparisons.map(([label, show]) => <tr key={label}><th scope="row">{label}</th><td>{show(data.one_alert_per_event)}</td><td>{show(data.correlated)}</td></tr>)}</tbody></table></div>
        <p>Median persisted resolution time {formatNumber(data.live_resolution.median_seconds, 1)} seconds across {formatNumber(data.live_resolution.case_count)} resolved cases.</p>
        {Object.keys(data.correlated.by_fraud_family).length > 0 && <>
          <h3>Episode coverage by family</h3>
          <div className="table-wrap"><table><thead><tr><th>Family</th><th>Episodes</th><th>Baseline detected</th><th>Correlated detected</th><th>Correlated at budget</th></tr></thead>
            <tbody>{Object.entries(data.correlated.by_fraud_family).map(([family, values]) => <tr key={family}>
              <th scope="row">{family.replaceAll('_', ' ')}</th>
              <td>{formatNumber(values.episodes)}</td>
              <td>{formatNumber(data.one_alert_per_event.by_fraud_family[family].detected)}</td>
              <td>{formatNumber(values.detected)} ({percentage(values.recall)})</td>
              <td>{formatNumber(values.at_budget)}</td>
            </tr>)}</tbody></table></div>
        </>}
        <p className="muted">{data.episode_definition}. {data.review_definition}.</p>
      </>}
    </div>
  </section>;
}
