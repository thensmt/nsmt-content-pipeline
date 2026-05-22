// NSMT — Procedural geometric avatars, seeded by writer name.
// Style: 5-column grid, mirrored horizontally, mixed shapes (squares, circles,
// triangles, half-circles). Two colors per writer (team primary + secondary).
// Feels like a printer's color-block test pattern, not slop.

function strHash(s) {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h >>> 0;
}

function makeRng(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 0x100000000;
  };
}

function ProceduralAvatar({ name, color, color2, ink = "#0B0B0C", paper = "#F6F2EA", size = 220, monochrome = false }) {
  const rng = React.useMemo(() => makeRng(strHash(name)), [name]);
  const cols = 5;
  const rows = 5;
  const cell = size / cols;

  // Build a 3-wide pattern, then mirror to 5 columns
  const pattern = React.useMemo(() => {
    const r = makeRng(strHash(name));
    const halfCols = Math.ceil(cols / 2);
    const grid = [];
    for (let y = 0; y < rows; y++) {
      const row = [];
      for (let x = 0; x < halfCols; x++) {
        const roll = r();
        let kind;
        if (roll < 0.32) kind = 0;          // empty
        else if (roll < 0.62) kind = 1;     // square
        else if (roll < 0.80) kind = 2;     // circle
        else if (roll < 0.92) kind = 3;     // triangle
        else kind = 4;                       // half-circle
        const colorRoll = r();
        const fill = colorRoll < 0.55 ? "primary" : (colorRoll < 0.85 ? "secondary" : "ink");
        const rotate = Math.floor(r() * 4) * 90;
        row.push({ kind, fill, rotate });
      }
      grid.push(row);
    }
    // mirror
    return grid.map(row => {
      const full = [...row];
      for (let i = halfCols - 2; i >= 0; i--) full.push(row[i]);
      return full;
    });
  }, [name]);

  // Pick a "stripe" — one row gets the team accent as a solid band, like a uniform stripe
  const stripeRow = strHash(name + "stripe") % rows;

  const colorFor = (fill) => {
    if (monochrome) return fill === "primary" ? ink : (fill === "secondary" ? "#555" : ink);
    if (fill === "primary") return color;
    if (fill === "secondary") return color2 || ink;
    return ink;
  };

  const bg = monochrome ? paper : "#F1ECDE";

  return (
    <svg viewBox={`0 0 ${size} ${size}`} width="100%" height="100%" preserveAspectRatio="xMidYMid meet" aria-hidden>
      <rect x="0" y="0" width={size} height={size} fill={bg} />
      {/* faint registration grid */}
      <g opacity="0.06" stroke={ink} strokeWidth="0.6">
        {Array.from({ length: cols + 1 }).map((_, i) => (
          <line key={"v" + i} x1={i * cell} y1="0" x2={i * cell} y2={size} />
        ))}
        {Array.from({ length: rows + 1 }).map((_, i) => (
          <line key={"h" + i} x1="0" y1={i * cell} x2={size} y2={i * cell} />
        ))}
      </g>

      {/* uniform stripe */}
      <rect
        x="0"
        y={stripeRow * cell}
        width={size}
        height={cell}
        fill={monochrome ? "#000" : color}
        opacity={monochrome ? 0.85 : 0.92}
      />

      {/* pattern */}
      {pattern.map((row, y) => row.map((c, x) => {
        if (c.kind === 0) return null;
        const cx = x * cell + cell / 2;
        const cy = y * cell + cell / 2;
        const fill = colorFor(c.fill);
        const inset = cell * 0.08;
        const w = cell - inset * 2;
        const key = `${x}-${y}`;
        switch (c.kind) {
          case 1: // square
            return <rect key={key} x={x * cell + inset} y={y * cell + inset} width={w} height={w} fill={fill} />;
          case 2: // circle
            return <circle key={key} cx={cx} cy={cy} r={w / 2} fill={fill} />;
          case 3: // triangle, oriented by rotate
            return (
              <polygon
                key={key}
                points={`${cx},${cy - w/2} ${cx + w/2},${cy + w/2} ${cx - w/2},${cy + w/2}`}
                fill={fill}
                transform={`rotate(${c.rotate} ${cx} ${cy})`}
              />
            );
          case 4: // half-circle (quarter rotated)
            return (
              <path
                key={key}
                d={`M ${cx - w/2} ${cy} A ${w/2} ${w/2} 0 0 1 ${cx + w/2} ${cy} L ${cx + w/2} ${cy + 0.01} Z`}
                fill={fill}
                transform={`rotate(${c.rotate} ${cx} ${cy})`}
              />
            );
          default:
            return null;
        }
      }))}

      {/* corner registration mark */}
      <g stroke={ink} strokeWidth="0.8" fill="none" opacity="0.55">
        <circle cx={size - 14} cy={size - 14} r="6" />
        <line x1={size - 14} y1={size - 22} x2={size - 14} y2={size - 6} />
        <line x1={size - 22} y1={size - 14} x2={size - 6} y2={size - 14} />
      </g>
    </svg>
  );
}

window.ProceduralAvatar = ProceduralAvatar;
