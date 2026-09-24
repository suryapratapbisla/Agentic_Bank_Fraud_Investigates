import { formatUsd } from '../data';

export default function SARTab({ record }) {
  const sar = record.sar ?? {};

  if (!sar.file) {
    return (
      <div className="rounded-xl border border-gray-700 bg-gray-800/40 p-8 text-center max-w-lg">
        <p className="text-gray-400 text-sm">SAR not filed for this case.</p>
        {sar.reason && (
          <p className="text-gray-500 text-sm mt-3">{sar.reason}</p>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-700 bg-gray-900/60 p-6 space-y-5 max-w-3xl">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-lg font-semibold text-gray-100">Suspicious Activity Report</h3>
        <span className="text-xs px-2 py-1 rounded border border-red-500/40 bg-red-500/15 text-red-300">
          L2 Approval Required
        </span>
      </div>

      {(sar.subjects?.length ?? 0) > 0 && (
        <div>
          <p className="text-xs text-gray-500 mb-2">Subjects</p>
          <div className="flex flex-wrap gap-2">
            {sar.subjects.map((s) => (
              <span
                key={s}
                className="text-sm px-3 py-1 rounded-full bg-gray-800 border border-gray-600 text-gray-200"
              >
                {s}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="grid sm:grid-cols-2 gap-4 text-sm">
        <div>
          <p className="text-xs text-gray-500">Total amount</p>
          <p className="text-gray-200 font-medium">
            {formatUsd(sar.total_amount_usd)}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Activity dates</p>
          <p className="text-gray-200">
            {(sar.activity_dates ?? []).join(', ') || '—'}
          </p>
        </div>
      </div>

      {sar.narrative && (
        <div>
          <p className="text-xs text-gray-500 mb-2">Narrative</p>
          <div className="rounded-lg bg-gray-950/50 border border-gray-700 p-4 text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">
            {sar.narrative}
          </div>
        </div>
      )}

      <button
        type="button"
        disabled
        className="px-4 py-2 rounded-lg bg-gray-700 text-gray-500 text-sm font-medium cursor-not-allowed"
      >
        File SAR (disabled — L2 approval)
      </button>
    </div>
  );
}
