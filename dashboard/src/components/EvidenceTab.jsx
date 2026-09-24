import { sourceBadgeClass } from '../data';

export default function EvidenceTab({ record }) {
  const items = record.case?.evidence ?? [];

  if (items.length === 0) {
    return (
      <p className="text-gray-500 text-sm">No evidence items collected for this case.</p>
    );
  }

  return (
    <div className="space-y-4">
      {items.map((item, idx) => (
        <div
          key={`${item.ref}-${idx}`}
          className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-2"
        >
          <p className="text-gray-100 font-medium leading-snug">{item.claim}</p>
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`text-xs px-2 py-0.5 rounded uppercase tracking-wide ${sourceBadgeClass(item.source)}`}
            >
              {item.source}
            </span>
            <span className="text-xs font-mono text-gray-500">{item.ref}</span>
          </div>
          {(item.entity_ids?.length ?? 0) > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {item.entity_ids.map((eid) => (
                <span
                  key={eid}
                  className="text-xs font-mono px-2 py-0.5 rounded bg-gray-800 text-gray-300 border border-gray-600"
                >
                  {eid}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
