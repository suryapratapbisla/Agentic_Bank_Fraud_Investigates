function FraudGauge({ value = 0 }) {
  const pct = Math.min(1, Math.max(0, value));
  const r = 54;
  const cx = 60;
  const cy = 60;
  const startAngle = -210;
  const endAngle = 30;
  const angle = startAngle + (endAngle - startAngle) * pct;
  const toRad = (deg) => (deg * Math.PI) / 180;
  const arcPoint = (deg) => ({
    x: cx + r * Math.cos(toRad(deg)),
    y: cy + r * Math.sin(toRad(deg)),
  });
  const start = arcPoint(startAngle);
  const end = arcPoint(endAngle);
  const needle = arcPoint(angle);
  const largeArc = endAngle - startAngle > 180 ? 1 : 0;
  const trackPath = `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 1 ${end.x} ${end.y}`;
  const color =
    pct < 0.3 ? '#34d399' : pct <= 0.7 ? '#fbbf24' : '#ef4444';

  return (
    <svg viewBox="0 0 120 80" className="w-full max-w-[200px] mx-auto">
      <path
        d={trackPath}
        fill="none"
        stroke="rgb(55 65 81)"
        strokeWidth="10"
        strokeLinecap="round"
      />
      <path
        d={trackPath}
        fill="none"
        stroke={color}
        strokeWidth="10"
        strokeLinecap="round"
        strokeDasharray={`${pct * 100} 100`}
        pathLength="100"
      />
      <line
        x1={cx}
        y1={cy}
        x2={needle.x}
        y2={needle.y}
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
      />
      <circle cx={cx} cy={cy} r="4" fill={color} />
      <text
        x={cx}
        y={78}
        textAnchor="middle"
        className="fill-gray-300 text-[11px] font-semibold"
      >
        {(pct * 100).toFixed(0)}%
      </text>
    </svg>
  );
}

export default FraudGauge;
