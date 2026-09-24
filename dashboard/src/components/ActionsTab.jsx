import { routePillClass } from '../data';

function ActionCard({ action }) {
  return (
    <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-semibold text-gray-100">{action.action}</span>
        <span
          className={`text-xs px-2 py-0.5 rounded border uppercase ${routePillClass(action.route)}`}
        >
          {action.route}
        </span>
      </div>
      <p className="text-sm text-gray-400">{action.reason}</p>
    </div>
  );
}

export default function ActionsTab({ record }) {
  const nba = record.next_best_actions ?? {};
  const initial = nba.initial ?? [];
  const final = nba.final ?? [];
  const whatChanged = nba.what_changed;

  return (
    <div className="grid md:grid-cols-[1fr_auto_1fr] gap-4 items-start">
      <div className="space-y-3">
        <h3 className="text-xs uppercase tracking-wide text-gray-500">Initial</h3>
        {initial.length === 0 ? (
          <p className="text-sm text-gray-500">None</p>
        ) : (
          initial.map((a, i) => <ActionCard key={i} action={a} />)
        )}
      </div>

      <div className="hidden md:flex flex-col items-center justify-center py-8 px-2">
        <span className="text-3xl text-violet-500">→</span>
        {whatChanged && (
          <div className="mt-4 max-w-[200px] rounded-lg border border-gray-600 bg-gray-900/80 p-3 text-xs text-gray-400 italic text-center">
            &ldquo;{whatChanged}&rdquo;
          </div>
        )}
      </div>

      <div className="space-y-3">
        <h3 className="text-xs uppercase tracking-wide text-gray-500">Final</h3>
        {final.length === 0 ? (
          <p className="text-sm text-gray-500">None</p>
        ) : (
          final.map((a, i) => <ActionCard key={i} action={a} />)
        )}
      </div>

      {whatChanged && (
        <div className="md:hidden col-span-full rounded-lg border border-gray-600 bg-gray-900/80 p-3 text-sm text-gray-400 italic">
          What changed: {whatChanged}
        </div>
      )}
    </div>
  );
}
