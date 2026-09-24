import { getCasePackMeta } from '../data/casePack';

export default function TimelineTab({ record }) {
  const pack = getCasePackMeta(record.case_id);
  const c = record.case ?? {};
  const evidenceCount = c.evidence?.length ?? 0;
  const hasRequests = (record.evidence_requests?.length ?? 0) > 0;
  const initial = record.next_best_actions?.initial ?? [];
  const final = record.next_best_actions?.final ?? [];

  const steps = [
    {
      key: 'trigger',
      title: 'Trigger',
      body: pack?.trigger_text ?? 'Case opened.',
      meta: pack?.opened_at,
    },
    {
      key: 'gathered',
      title: 'Evidence Gathered',
      body: `${evidenceCount} evidence item(s) from graph and related sources.`,
    },
  ];

  if (hasRequests) {
    steps.push({
      key: 'requested',
      title: 'Evidence Requested',
      body: record.evidence_requests
        .map(
          (r) =>
            `${r.type}: ${r.assumed_response ?? 'Pending'} (after step ${r.asked_after_step})`
        )
        .join(' · '),
    });
  }

  steps.push(
    {
      key: 'initial',
      title: 'Initial Action',
      body:
        initial.length > 0
          ? initial.map((a) => `${a.action} (${a.route})`).join(', ')
          : 'No initial actions recorded.',
    },
    {
      key: 'final',
      title: 'Final Action',
      body:
        final.length > 0
          ? final.map((a) => `${a.action} (${a.route})`).join(', ')
          : 'Pending final disposition.',
    },
    {
      key: 'closed',
      title: 'Case Closed',
      body: record.stop_reason ?? c.summary ?? 'Investigation in progress.',
    }
  );

  return (
    <div className="relative pl-6 border-l-2 border-gray-700 space-y-8">
      {steps.map((step, i) => (
        <div
          key={step.key}
          className="relative timeline-step"
          style={{ animationDelay: `${i * 80}ms` }}
        >
          <span
            className={`absolute -left-[calc(1.5rem+5px)] top-1.5 w-3 h-3 rounded-full border-2 border-gray-950 ${
              i === 0 ? 'bg-violet-500' : 'bg-gray-600'
            }`}
          />
          <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4">
            <h3 className="text-sm font-semibold text-gray-200">{step.title}</h3>
            {step.meta && (
              <p className="text-xs text-gray-500 mt-0.5 font-mono">{step.meta}</p>
            )}
            <p className="text-sm text-gray-400 mt-2 leading-relaxed">{step.body}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
