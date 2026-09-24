import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  cases,
  getDashboardStats,
  getAgentStats,
  verdictStyles,
  probabilityColor,
  formatUsd,
} from '../data';

export default function Dashboard() {
  const navigate = useNavigate();
  const stats = getDashboardStats();
  const agentStats = getAgentStats();
  const [sortKey, setSortKey] = useState('case_id');
  const [sortDir, setSortDir] = useState('asc');

  const sorted = useMemo(() => {
    const list = [...cases];
    list.sort((a, b) => {
      let av;
      let bv;
      switch (sortKey) {
        case 'exposure':
          av = a.case?.exposure_usd ?? 0;
          bv = b.case?.exposure_usd ?? 0;
          break;
        case 'probability':
          av = a.case?.fraud_probability ?? 0;
          bv = b.case?.fraud_probability ?? 0;
          break;
        case 'verdict':
          av = a.case?.verdict ?? '';
          bv = b.case?.verdict ?? '';
          break;
        default:
          av = a.case_id;
          bv = b.case_id;
      }
      if (av < bv) return sortDir === 'asc' ? -1 : 1;
      if (av > bv) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
    return list;
  }, [sortKey, sortDir]);

  function toggleSort(key) {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else {
      setSortKey(key);
      setSortDir('asc');
    }
  }

  const statCards = [
    { label: 'Total Cases', value: stats.total, accent: 'text-gray-100' },
    { label: 'Fraud', value: stats.fraud, accent: 'text-red-400' },
    { label: 'Legitimate', value: stats.legitimate, accent: 'text-emerald-400' },
    { label: 'Uncertain', value: stats.uncertain, accent: 'text-amber-300' },
    {
      label: 'Total Exposure',
      value: formatUsd(stats.totalExposure),
      accent: 'text-blue-400',
    },
  ];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-100">Case Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">
          Agentic fraud investigations — {stats.total} open cases
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {statCards.map((card) => (
          <div
            key={card.label}
            className="rounded-xl border border-gray-700 bg-gray-800/60 p-4"
          >
            <p className="text-xs uppercase tracking-wide text-gray-500">{card.label}</p>
            <p className={`text-2xl font-bold mt-1 ${card.accent}`}>{card.value}</p>
          </div>
        ))}
      </div>

      <div>
        <h2 className="text-sm font-medium text-gray-400 mb-3">Agent stats</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="rounded-xl border border-gray-700 bg-gray-800/60 p-4">
            <p className="text-xs uppercase tracking-wide text-gray-500">Total tool calls</p>
            <p className="text-2xl font-bold mt-1 text-violet-300">
              {agentStats.totalToolCalls.toLocaleString()}
            </p>
          </div>
          <div className="rounded-xl border border-gray-700 bg-gray-800/60 p-4">
            <p className="text-xs uppercase tracking-wide text-gray-500">Total tokens</p>
            <p className="text-2xl font-bold mt-1 text-cyan-300">
              {agentStats.totalTokens.toLocaleString()}
            </p>
          </div>
          <div className="rounded-xl border border-gray-700 bg-gray-800/60 p-4">
            <p className="text-xs uppercase tracking-wide text-gray-500">Avg latency</p>
            <p className="text-2xl font-bold mt-1 text-amber-300">
              {agentStats.avgLatencyS.toFixed(1)}s
            </p>
          </div>
        </div>
        <p className="text-xs text-gray-600 mt-2">
          From agent run metadata in case JSON ({agentStats.casesWithMetrics} cases)
        </p>
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/50 px-4 py-3 text-sm text-gray-400 flex flex-wrap gap-x-4 gap-y-1">
        <span>
          <span className="text-red-400 font-medium">{stats.fraud}</span> fraud
        </span>
        <span className="text-gray-600">|</span>
        <span>
          <span className="text-emerald-400 font-medium">{stats.legitimate}</span>{' '}
          legitimate
        </span>
        <span className="text-gray-600">|</span>
        <span>
          <span className="text-amber-300 font-medium">{stats.uncertain}</span> uncertain
        </span>
        <span className="text-gray-600">|</span>
        <span>
          <span className="text-blue-400 font-medium">{formatUsd(stats.totalExposure)}</span>{' '}
          exposure
        </span>
      </div>

      <div className="rounded-xl border border-gray-700 bg-gray-800/40 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="bg-gray-900/80 text-gray-400 uppercase text-xs">
              <tr>
                <th className="px-4 py-3 cursor-pointer hover:text-gray-200" onClick={() => toggleSort('case_id')}>
                  Case ID
                </th>
                <th className="px-4 py-3 cursor-pointer hover:text-gray-200" onClick={() => toggleSort('verdict')}>
                  Verdict
                </th>
                <th className="px-4 py-3">Pattern</th>
                <th className="px-4 py-3 cursor-pointer hover:text-gray-200" onClick={() => toggleSort('exposure')}>
                  Exposure
                </th>
                <th className="px-4 py-3 cursor-pointer hover:text-gray-200" onClick={() => toggleSort('probability')}>
                  Fraud Probability
                </th>
                <th className="px-4 py-3">SAR Filed</th>
                <th className="px-4 py-3">Actions</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700/80">
              {sorted.map((record) => {
                const c = record.case ?? {};
                const prob = c.fraud_probability ?? 0;
                const actionsCount =
                  (record.next_best_actions?.initial?.length ?? 0) +
                  (record.next_best_actions?.final?.length ?? 0);
                return (
                  <tr
                    key={record.case_id}
                    className="hover:bg-gray-800/60 cursor-pointer transition-colors"
                    onClick={() => navigate(`/case/${record.case_id}`)}
                  >
                    <td className="px-4 py-3 font-mono text-violet-300">{record.case_id}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex px-2 py-0.5 rounded border text-xs font-medium capitalize ${verdictStyles(c.verdict)}`}
                      >
                        {c.verdict ?? '—'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-300 capitalize">
                      {(c.pattern ?? '—').replace(/_/g, ' ')}
                    </td>
                    <td className="px-4 py-3 text-gray-200">{formatUsd(c.exposure_usd)}</td>
                    <td className="px-4 py-3 min-w-[140px]">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 rounded-full bg-gray-700 overflow-hidden">
                          <div
                            className={`h-full rounded-full ${probabilityColor(prob)}`}
                            style={{ width: `${Math.min(100, prob * 100)}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-400 w-10 text-right">
                          {(prob * 100).toFixed(0)}%
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {record.sar?.file ? (
                        <span className="text-xs px-2 py-0.5 rounded bg-red-500/20 text-red-300 border border-red-500/30">
                          Filed
                        </span>
                      ) : (
                        <span className="text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-400">
                          No
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-400">{actionsCount}</td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        className="text-xs px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white font-medium"
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/case/${record.case_id}`);
                        }}
                      >
                        View
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
