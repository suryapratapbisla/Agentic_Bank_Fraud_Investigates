import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { getCaseById, getCasePackMeta, verdictStyles, formatUsd } from '../data';
import { formatConnectedCard } from '../utils/cardLabel';
import FraudGauge from './FraudGauge';
import EvidenceTab from './EvidenceTab';
import TimelineTab from './TimelineTab';
import ActionsTab from './ActionsTab';
import SARTab from './SARTab';

const TABS = [
  { id: 'evidence', label: 'Evidence' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'actions', label: 'Next Actions' },
  { id: 'sar', label: 'SAR Report' },
];

export default function CaseDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const record = getCaseById(id);
  const [tab, setTab] = useState('evidence');

  if (!record) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-16 text-center">
        <p className="text-gray-400">Case {id} not found.</p>
        <Link to="/" className="text-violet-400 mt-4 inline-block">
          Back to dashboard
        </Link>
      </div>
    );
  }

  const c = record.case ?? {};
  const pack = getCasePackMeta(record.case_id);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6 flex flex-col lg:flex-row gap-6 min-h-[calc(100vh-3.5rem)]">
      <aside className="w-full lg:w-[280px] shrink-0 space-y-4">
        <div className="rounded-xl border border-gray-700 bg-gray-800/60 p-5 space-y-4">
          <div className="flex items-center justify-between gap-2">
            <h1 className="font-mono text-lg text-violet-300">{record.case_id}</h1>
            <span className="text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-300 capitalize">
              {c.status ?? 'open'}
            </span>
          </div>
          <span
            className={`inline-flex px-2 py-1 rounded border text-sm font-medium capitalize ${verdictStyles(c.verdict)}`}
          >
            {c.verdict ?? 'uncertain'}
          </span>
          <div>
            {c.written_to_graph ? (
              <div className="space-y-1">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/15 text-emerald-300 border border-emerald-500/40">
                  <svg
                    className="w-3.5 h-3.5"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2.5}
                    aria-hidden
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                  In TigerGraph
                </span>
                {c.graph_case_id && (
                  <p className="text-xs font-mono text-gray-500">{c.graph_case_id}</p>
                )}
              </div>
            ) : (
              <span className="inline-flex px-2 py-1 rounded text-xs text-gray-500 bg-gray-800/80 border border-gray-700">
                Not written to graph
              </span>
            )}
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-1">Fraud probability</p>
            <FraudGauge value={c.fraud_probability ?? 0} />
          </div>
          <div>
            <p className="text-xs text-gray-500">Pattern</p>
            <p className="text-sm text-gray-200 capitalize">
              {(c.pattern ?? '—').replace(/_/g, ' ')}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Exposure</p>
            <p className="text-2xl font-bold text-blue-400">{formatUsd(c.exposure_usd)}</p>
          </div>
          {(c.similar_prior_cases?.length ?? 0) > 0 && (
            <div>
              <p className="text-xs text-gray-500 mb-2">Similar prior cases</p>
              <div className="flex flex-wrap gap-1.5">
                {c.similar_prior_cases.map((pc) => (
                  <span
                    key={pc}
                    className="text-xs font-mono px-2 py-0.5 rounded-full bg-red-950/50 text-red-300 border border-red-900/50"
                  >
                    {pc}
                  </span>
                ))}
              </div>
            </div>
          )}
          {(c.connected_card_ids?.length ?? 0) > 0 && (
            <div>
              <p className="text-xs text-gray-500 mb-2">
                Connected cards
                <span className="text-gray-600"> · {c.connected_card_ids.length}</span>
              </p>
              <ul className="space-y-1.5 max-h-52 overflow-y-auto pr-1">
                {c.connected_card_ids.map((cardId) => {
                  const card = formatConnectedCard(cardId);
                  return (
                    <li
                      key={cardId}
                      title={card.full}
                      className="rounded-md border border-pink-900/40 bg-pink-950/30 px-2.5 py-1.5"
                    >
                      <p className="text-xs font-medium text-pink-200">{card.title}</p>
                      {card.detail && (
                        <p className="text-[11px] text-pink-300/70">{card.detail}</p>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
          {record.stop_reason && (
            <div>
              <p className="text-xs text-gray-500">Stop reason</p>
              <p className="text-sm text-gray-400">{record.stop_reason}</p>
            </div>
          )}
          <button
            type="button"
            onClick={() => navigate(`/graph/${record.case_id}`)}
            className="w-full py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-sm font-medium text-white"
          >
            View Graph
          </button>
        </div>
        {pack && (
          <div className="rounded-xl border border-gray-700 bg-gray-900/40 p-4 text-xs text-gray-500">
            <p>
              Customer{' '}
              <span className="font-mono text-gray-400">{pack.customer_id}</span>
            </p>
            <p className="mt-1">
              Card <span className="font-mono text-gray-400">{pack.card_id}</span>
            </p>
          </div>
        )}
      </aside>

      <div className="flex-1 min-w-0 flex flex-col rounded-xl border border-gray-700 bg-gray-800/30 overflow-hidden">
        <div className="flex border-b border-gray-700 overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`px-5 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                tab === t.id
                  ? 'border-violet-500 text-violet-300 bg-gray-900/40'
                  : 'border-transparent text-gray-500 hover:text-gray-300'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex-1 p-5 overflow-y-auto">
          {tab === 'evidence' && <EvidenceTab record={record} />}
          {tab === 'timeline' && <TimelineTab record={record} />}
          {tab === 'actions' && <ActionsTab record={record} />}
          {tab === 'sar' && <SARTab record={record} />}
        </div>
      </div>
    </div>
  );
}
