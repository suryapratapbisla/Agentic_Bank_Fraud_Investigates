import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import ForceGraph2D from 'react-force-graph-2d';
import {
  fetchEvidenceBundle,
  isLiveGraphEnabled,
  loadOfflineGraphPayload,
} from '../api/tigergraph';
import { getCaseById, getCasePackMeta } from '../data';
import {
  NODE_COLORS,
  buildGraphFromCase,
  buildGraphFromEvidenceBundle,
  cloneGraphForRender,
} from '../utils/graphBuilder';

const SOURCE_LABELS = {
  live: { text: 'Live TigerGraph', className: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' },
  bundle: { text: 'Cached bundle', className: 'bg-blue-500/20 text-blue-300 border-blue-500/40' },
  case: { text: 'Case JSON only', className: 'bg-gray-600/30 text-gray-400 border-gray-600' },
};

export default function GraphView() {
  const { id } = useParams();
  const record = getCaseById(id);
  const pack = getCasePackMeta(id);
  const fgRef = useRef();
  const containerRef = useRef(null);
  const hasAutoFitRef = useRef(false);
  const [selected, setSelected] = useState(null);
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [source, setSource] = useState('case');
  const [loading, setLoading] = useState(true);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  useEffect(() => {
    hasAutoFitRef.current = false;
  }, [id]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return undefined;

    const updateSize = () => {
      const { width, height } = el.getBoundingClientRect();
      if (width >= 80 && height >= 80) {
        setDimensions({ width: Math.floor(width), height: Math.floor(height) });
      }
    };

    updateSize();
    const ro = new ResizeObserver(updateSize);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const fitGraphToCanvas = useCallback(() => {
    const fg = fgRef.current;
    if (!fg || dimensions.width < 80 || dimensions.height < 80) return;
    requestAnimationFrame(() => {
      fg.zoomToFit(500, 64);
    });
  }, [dimensions.width, dimensions.height]);

  useEffect(() => {
    const rec = getCaseById(id);
    const pk = getCasePackMeta(id);
    if (!rec || !pk) {
      setGraphData({ nodes: [], links: [] });
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function load() {
      setLoading(true);

      let evidenceBundle = null;
      let src = 'case';

      if (isLiveGraphEnabled() && pk.flagged_txn_id && pk.customer_id) {
        try {
          evidenceBundle = await fetchEvidenceBundle({
            flaggedTxnId: pk.flagged_txn_id,
            customerId: pk.customer_id,
          });
          src = 'live';
        } catch {
          /* fall through to offline sources */
        }
      }

      if (!evidenceBundle) {
        const offline = await loadOfflineGraphPayload(rec.case_id);
        evidenceBundle = offline.evidenceBundle;
        src = offline.source;
      }

      if (cancelled) return;

      setSource(src);
      const built = evidenceBundle
        ? buildGraphFromEvidenceBundle(evidenceBundle, pk, rec)
        : buildGraphFromCase(rec, pk);
      setGraphData(cloneGraphForRender(built));
      hasAutoFitRef.current = false;
      setLoading(false);
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const paintNode = useCallback((node, ctx, globalScale) => {
    const type = node.type ?? 'txn';
    const color = NODE_COLORS[type] ?? '#6b7280';
    const r = Math.sqrt(node.val ?? 4) * 3;
    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = '#111827';
    ctx.lineWidth = 1 / globalScale;
    ctx.stroke();

    const label = node.label ?? node.id;
    const fontSize = type === 'flagged_txn' ? 12 / globalScale : 10 / globalScale;
    ctx.font = `${type === 'flagged_txn' ? 'bold ' : ''}${fontSize}px Inter, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillStyle = '#e5e7eb';
    const short = String(label).length > 28 ? `${String(label).slice(0, 26)}…` : label;
    ctx.fillText(short, node.x, node.y + r + 2);
  }, []);

  const handleZoom = (factor) => {
    const fg = fgRef.current;
    if (!fg) return;
    fg.zoom(fg.zoom() * factor, 400);
  };

  if (!record) {
    return (
      <div className="p-8 text-center text-gray-400">
        Case not found. <Link to="/" className="text-violet-400">Dashboard</Link>
      </div>
    );
  }

  const badge = SOURCE_LABELS[source] ?? SOURCE_LABELS.case;

  return (
    <div className="h-[calc(100vh-3.5rem)] flex flex-col lg:flex-row">
      <div
        ref={containerRef}
        className="flex-1 relative bg-gray-950 border-b lg:border-b-0 lg:border-r border-gray-800 min-h-[400px] min-h-0 w-full overflow-hidden"
      >
        <div className="absolute top-4 left-4 z-10 flex flex-wrap gap-2 items-center">
          <Link
            to={`/case/${id}`}
            className="px-3 py-1.5 text-xs rounded-lg bg-gray-800 border border-gray-600 text-gray-300 hover:bg-gray-700"
          >
            ← Case
          </Link>
          <button
            type="button"
            onClick={() => handleZoom(1.3)}
            className="px-3 py-1.5 text-xs rounded-lg bg-gray-800 border border-gray-600 text-gray-300 hover:bg-gray-700"
          >
            Zoom in
          </button>
          <button
            type="button"
            onClick={() => handleZoom(0.75)}
            className="px-3 py-1.5 text-xs rounded-lg bg-gray-800 border border-gray-600 text-gray-300 hover:bg-gray-700"
          >
            Zoom out
          </button>
          <button
            type="button"
            onClick={fitGraphToCanvas}
            className="px-3 py-1.5 text-xs rounded-lg bg-violet-600 text-white hover:bg-violet-500"
          >
            Recenter
          </button>
          <span
            className={`px-2 py-1 text-xs rounded border ${badge.className}`}
          >
            {badge.text}
          </span>
        </div>
        <p className="absolute top-4 right-4 z-10 text-xs text-gray-500 font-mono">
          {id} · {graphData.nodes.length} nodes
        </p>
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-950/80 z-20 text-sm text-gray-400">
            Loading investigation graph…
          </div>
        )}
        <ForceGraph2D
          ref={fgRef}
          width={dimensions.width}
          height={dimensions.height}
          graphData={graphData}
          backgroundColor="#030712"
          linkDistance={90}
          nodeRelSize={6}
          d3VelocityDecay={0.35}
          warmupTicks={40}
          cooldownTicks={120}
          nodeCanvasObject={paintNode}
          nodePointerAreaPaint={(node, color, ctx) => {
            const r = Math.sqrt(node.val ?? 4) * 3 + 4;
            ctx.beginPath();
            ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
            ctx.fillStyle = color;
            ctx.fill();
          }}
          linkColor={(l) => l.color ?? '#4b5563'}
          linkWidth={1.5}
          linkLineDash={(l) => (l.dashed ? [4, 4] : null)}
          onNodeClick={(node) => setSelected(node)}
          onBackgroundClick={() => setSelected(null)}
          onEngineStop={() => {
            if (loading || hasAutoFitRef.current || graphData.nodes.length === 0) return;
            hasAutoFitRef.current = true;
            fitGraphToCanvas();
          }}
        />
      </div>

      <aside className="w-full lg:w-80 shrink-0 bg-gray-900/80 p-5 border-t lg:border-t-0 border-gray-800 overflow-y-auto">
        <h2 className="text-sm font-semibold text-gray-300 mb-4">Node inspector</h2>
        {selected ? (
          <div className="space-y-3 text-sm">
            <div>
              <p className="text-xs text-gray-500">ID</p>
              <p className="font-mono text-violet-300 break-all">{selected.id}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Type</p>
              <p className="capitalize text-gray-200">
                {(selected.type ?? 'unknown').replace(/_/g, ' ')}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Label</p>
              <p className="text-gray-300">{selected.label}</p>
            </div>
            {selected.meta && Object.keys(selected.meta).length > 0 && (
              <div>
                <p className="text-xs text-gray-500 mb-1">Attributes</p>
                <dl className="text-xs space-y-1 text-gray-400">
                  {Object.entries(selected.meta)
                    .slice(0, 8)
                    .map(([k, v]) => (
                      <div key={k} className="flex gap-2">
                        <dt className="text-gray-500 shrink-0">{k}:</dt>
                        <dd className="break-all">{String(v)}</dd>
                      </div>
                    ))}
                </dl>
              </div>
            )}
            <div
              className="w-4 h-4 rounded-full border border-gray-600"
              style={{ backgroundColor: NODE_COLORS[selected.type] ?? '#6b7280' }}
            />
          </div>
        ) : (
          <p className="text-sm text-gray-500">Click a node to inspect attributes.</p>
        )}

        <div className="mt-8 pt-4 border-t border-gray-800">
          <p className="text-xs text-gray-500 mb-2">Legend</p>
          <ul className="space-y-1.5 text-xs text-gray-400">
            {Object.entries(NODE_COLORS).map(([type, color]) => (
              <li key={type} className="flex items-center gap-2 capitalize">
                <span
                  className="w-2.5 h-2.5 rounded-full shrink-0"
                  style={{ backgroundColor: color }}
                />
                {type.replace(/_/g, ' ')}
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}
