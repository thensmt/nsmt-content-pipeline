/* NSMT — components & hooks */

const { useState, useEffect, useRef, useMemo, useCallback } = React;

/* ===== Hooks ============================================================ */

function useInView(opts = {}) {
  const ref = useRef(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    if (!ref.current) return;
    const io = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (e.isIntersecting) {
          setInView(true);
          io.disconnect();
        }
      });
    }, { threshold: 0.3, ...opts });
    io.observe(ref.current);
    return () => io.disconnect();
  }, []);
  return [ref, inView];
}

function useCountUp(target, active, duration = 1400) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (!active) return;
    let raf, start;
    const step = (t) => {
      if (!start) start = t;
      const p = Math.min(1, (t - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      setVal(Math.round(target * eased));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, active, duration]);
  return val;
}

function useStickyShow(threshold = 600) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const onScroll = () => setShow(window.scrollY > threshold);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [threshold]);
  return show;
}

function useKonami(onTrigger) {
  useEffect(() => {
    const seq = ['ArrowUp','ArrowUp','ArrowDown','ArrowDown','ArrowLeft','ArrowRight','ArrowLeft','ArrowRight','b','a'];
    let pos = 0;
    const onKey = (e) => {
      const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
      if (k === seq[pos]) {
        pos++;
        if (pos === seq.length) { onTrigger(); pos = 0; }
      } else {
        pos = (k === seq[0]) ? 1 : 0;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onTrigger]);
}

function useTheme() {
  const [theme, setTheme] = useState(() => {
    if (typeof window === 'undefined') return 'light';
    return localStorage.getItem('nsmt-theme') || 'light';
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('nsmt-theme', theme);
  }, [theme]);
  return [theme, () => setTheme(t => t === 'light' ? 'dark' : 'light')];
}

/* ===== Splash =========================================================== */
function Splash() {
  const [gone, setGone] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setGone(true), 2000);
    return () => clearTimeout(t);
  }, []);
  if (gone) return null;
  const today = new Date();
  const dateStr = today.toISOString().slice(0,10);
  return (
    <div className="splash" aria-hidden>
      <div className="splash-inner">
        <div className="splash-big"><i>PRESS</i> <span className="splash-blue">DAY</span></div>
        <div>· {dateStr} · NSMT NEWSROOM ·</div>
        <div className="splash-bar"></div>
        <div style={{ opacity: 0.55 }}>WAKING THE WIRE ROOM</div>
      </div>
    </div>
  );
}

/* ===== Bot mark (used in bylines) ======================================= */
function BotMark({ size = 11, accent = "var(--blue)" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" aria-hidden style={{ flexShrink: 0 }}>
      <rect x="1" y="2" width="12" height="11" rx="2" fill={accent} />
      <rect x="3" y="4" width="8" height="5" fill="#F4EFE3" />
      <circle cx="5" cy="6.5" r="0.9" fill={accent} />
      <circle cx="9" cy="6.5" r="0.9" fill={accent} />
      <rect x="4" y="10" width="6" height="1.6" fill="#F4EFE3" />
      <line x1="7" y1="0" x2="7" y2="2" stroke={accent} strokeWidth="1.2" />
      <circle cx="7" cy="0" r="0.8" fill={accent} />
    </svg>
  );
}

/* ===== Top bar ========================================================== */
function TopBar({ now, theme, onToggleTheme, onPoster }) {
  return (
    <div className="topbar">
      <div className="topbar-inner">
        <span className="dot"></span>
        <span className="topbar-label">NSMT NEWSROOM · LIVE</span>
        <span className="topbar-sep">/</span>
        <span className="topbar-mono">{now || "—"}</span>
        <span className="topbar-sep">/</span>
        <span className="topbar-mono dim">VOL.01 · ISSUE 001</span>
        <span className="topbar-spacer"></span>
        <span className="topbar-actions">
          <button className="topbar-btn" onClick={onPoster} aria-label="Open poster mode for sharing">
            ⌖ POSTER MODE
          </button>
          <button className="topbar-btn" onClick={onToggleTheme} aria-label="Toggle dark mode">
            {theme === 'dark' ? '☀ DAY' : '☾ CONTROL ROOM'}
          </button>
        </span>
      </div>
    </div>
  );
}

/* ===== Ticker =========================================================== */
function Ticker() {
  const items = ["14 AI WRITERS","·","1 SOLO FOUNDER","·","$0 / MONTH","·","08:00 ET DAILY","·","FULL TRANSPARENCY","·","HUMAN IN THE LOOP","·","DMV SPORTS","·","POWERED BY CLAUDE","·"];
  return (
    <div className="ticker" aria-hidden>
      <div className="ticker-track">
        {Array.from({ length: 3 }).map((_, i) => (
          <span className="ticker-row" key={i}>
            {items.map((t, j) => <span className="ticker-item" key={j}>{t}</span>)}
          </span>
        ))}
      </div>
    </div>
  );
}

/* ===== Sticky mini-masthead ============================================= */
function StickyMasthead({ now }) {
  const visible = useStickyShow(640);
  return (
    <div className={`sticky-masthead ${visible ? 'visible' : ''}`} role="navigation" aria-label="Sticky navigation">
      <div className="sticky-inner">
        <a href="#top" className="sticky-logo" style={{ textDecoration: 'none', color: 'inherit' }}>
          <span><i>NSMT</i></span>
          <span className="sticky-logo-blue">·</span>
          <span className="sticky-edition">THE MACHINE ROOM</span>
        </a>
        <nav className="sticky-nav">
          <a href="#writers">THE MASTHEAD</a>
          <a href="#how">THE WIRE</a>
          <a href="#stack">THE EQUIPMENT</a>
          <a href="#why">WHY</a>
        </nav>
        <span className="sticky-clock">{now}</span>
      </div>
    </div>
  );
}

/* ===== Letter-stagger ==================================================== */
function flattenToText(n) {
  if (n == null || n === false || n === true) return '';
  if (typeof n === 'string' || typeof n === 'number') return String(n);
  if (Array.isArray(n)) return n.map(flattenToText).join('');
  if (n.props && n.props.children !== undefined) return flattenToText(n.props.children);
  return '';
}

function StaggerLine({ children, baseDelay = 0, perLetter = 28, indent = false }) {
  // Wrap each character in a span with its own delay; preserve spaces.
  const text = flattenToText(children);
  return (
    <span className={`t-line ${indent ? 't-line--indent' : ''}`}>
      {text.split('').map((c, i) => (
        <span
          key={i}
          className="letter"
          style={{ '--ld': `${baseDelay + i * perLetter}ms`, width: c === ' ' ? '0.32em' : 'auto' }}
        >
          {c === ' ' ? '\u00a0' : c}
        </span>
      ))}
    </span>
  );
}

function StaggerWrap({ children, baseDelay = 0, perLetter = 28, indent = false }) {
  // children is an array of {text, mark, em} fragments; concat with running delays
  let d = baseDelay;
  return (
    <span className={`t-line ${indent ? 't-line--indent' : ''}`}>
      {children.map((seg, segIdx) => {
        const start = d;
        const text = seg.text;
        const spans = text.split('').map((c, i) => {
          const out = (
            <span key={i} className="letter" style={{ '--ld': `${start + i * perLetter}ms`, width: c === ' ' ? '0.32em' : 'auto' }}>
              {c === ' ' ? '\u00a0' : c}
            </span>
          );
          return out;
        });
        d += text.length * perLetter;
        if (seg.em) return <em key={segIdx}>{spans}</em>;
        if (seg.mark) return <mark key={segIdx}>{spans}</mark>;
        return <React.Fragment key={segIdx}>{spans}</React.Fragment>;
      })}
    </span>
  );
}

/* ===== Hero ============================================================= */
function Hero({ now }) {
  const [megaRef, megaIn] = useInView();
  const n14 = useCountUp(14, megaIn, 1200);
  const n800 = useCountUp(800, megaIn, 1400); // shown as 08:00 reveal trick
  const n0 = useCountUp(0, megaIn, 1000);

  return (
    <header className="hero" id="top">
      <div className="hero-meta">
        <div className="kicker">
          <span className="kicker-square"></span>
          <span>A NSMT DISPATCH · MAY 2026 · DMV BUREAU</span>
        </div>
        <div className="hero-edition">EDITION №001 — THE MACHINE ROOM</div>
      </div>

      <h1 className="hero-title" aria-label="We taught 14 AI writers how to cover sports in the DMV.">
        <StaggerLine baseDelay={300}>We taught</StaggerLine>
        <StaggerWrap baseDelay={650} indent>
          {[{ text: "14 ", em: true }, { text: "AI ", em: true }, { text: "writers", em: true }]}
        </StaggerWrap>
        <StaggerLine baseDelay={1050}>how to cover</StaggerLine>
        <StaggerWrap baseDelay={1300}>
          {[{ text: "sports in the DMV.", mark: true }]}
        </StaggerWrap>
      </h1>

      <p className="hero-deck">
        Every morning at <b>8:00 a.m. Eastern</b>, a small Python script wakes up, asks ESPN
        what happened last night, and hands the box scores to a roster of <b>fourteen AI
        sportswriters</b> — each with a name, a beat, and a voice of their own. They file
        drafts. A human edits. We publish, with the byline that always carries a small robot.
      </p>

      <div className="hero-foot">
        <div className="byline">
          <div className="byline-rule"></div>
          <div className="byline-text">
            <span><b>BY DAVID GAYLOR</b></span>
            <span className="byline-sub">FOUNDER · NOVA SPORTS MEDIA TEAM</span>
            <span className="byline-sub">FILED FROM ALEXANDRIA, VA</span>
          </div>
        </div>

        <div className="hero-ctas">
          <a href="https://thensmt.com" target="_blank" rel="noreferrer" className="btn btn--primary">
            <span>READ TODAY'S RECAPS</span>
            <Arrow />
          </a>
          <a href="https://twitter.com/the_nsmt" target="_blank" rel="noreferrer" className="btn">
            <span>FOLLOW @THE_NSMT</span>
            <Arrow />
          </a>
          <a href="mailto:david@thensmt.com?subject=NSMT%20Coverage%20Inquiry" className="btn btn--ghost btn--xs">
            <span>HIRE NSMT FOR COVERAGE</span>
            <Arrow />
          </a>
        </div>
      </div>

      <div className="hero-mega" ref={megaRef}>
        <div className="mega">
          <span className="mega-n">{n14}</span>
          <span className="mega-l"><b>AI WRITERS</b> · ONE PER BEAT</span>
        </div>
        <div className="mega">
          <span className="mega-n tilt">
            {String(Math.min(8, Math.floor(n800/100))).padStart(2,'0')}
            <sup>:{String(Math.min(0, n800 % 100)).padStart(2,'0')==='00' ? '00' : '00'}</sup>
          </span>
          <span className="mega-l"><b>EASTERN</b> · DAILY DROP</span>
        </div>
        <div className="mega">
          <span className="mega-n">${n0}</span>
          <span className="mega-l"><b>PER MONTH</b> · ALL FREE TIERS</span>
        </div>
      </div>

      <RegistrationMark className="reg reg--tl" />
      <RegistrationMark className="reg reg--tr" />
      <RegistrationMark className="reg reg--bl" />
      <RegistrationMark className="reg reg--br" />
    </header>
  );
}

/* ===== Today's Lineup =================================================== */
function TodayLineup({ now }) {
  const writersById = useMemo(() => Object.fromEntries(WRITERS.map(w => [w.id, w])), []);
  const today = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' }).toUpperCase();
  return (
    <section className="lineup" aria-labelledby="lineup-h">
      <div className="lineup-head">
        <div>
          <div className="section-eyebrow">
            <span className="eyebrow-num">§ 00</span>
            <span className="eyebrow-line"></span>
            <span>TODAY'S LINEUP</span>
          </div>
          <h2 className="lineup-title" id="lineup-h">
            On the wire <em>right now</em>.
          </h2>
        </div>
        <div className="lineup-clock">
          <span>NEWSROOM CLOCK</span>
          <b>{now}</b>
          <span>{today}</span>
        </div>
      </div>

      <table className="lineup-table">
        <thead>
          <tr>
            <th>WRITER</th>
            <th>GAME</th>
            <th>FINAL</th>
            <th>STATUS</th>
            <th style={{ textAlign: 'right' }}>STARTED</th>
          </tr>
        </thead>
        <tbody>
          {TODAY_LINEUP.map(row => {
            const w = writersById[row.writer];
            return (
              <tr key={row.writer}>
                <td>
                  <div className="lineup-writer">
                    <div className="lineup-avatar" aria-hidden>
                      <ProceduralAvatar name={w.name} color={w.color} color2={w.color2} size={64} />
                    </div>
                    <div>
                      <div className="lineup-name">{w.first} {w.last}</div>
                      <div className="lineup-team">{w.team}</div>
                    </div>
                  </div>
                </td>
                <td className="lineup-game">{row.game}</td>
                <td className="lineup-game" style={{ fontFeatureSettings: '"tnum"' }}>{row.finalScore}</td>
                <td>
                  <span className="pill" data-status={row.status}>{STATUS_META[row.status].label}</span>
                </td>
                <td style={{ textAlign: 'right', fontFamily: 'var(--ff-mono)', letterSpacing: '1.4px' }}>{row.time} ET</td>
              </tr>
            );
          })}
          <tr>
            <td colSpan="5" style={{ textAlign: 'center', padding: '14px', color: 'var(--muted)', fontFamily: 'var(--ff-mono)', fontSize: '11px', letterSpacing: '2px' }}>
              · 9 OTHER WRITERS IDLE — NO DMV GAMES ON THEIR BEAT LAST NIGHT ·
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  );
}

/* ===== Editorial pull-quote ============================================= */
function EditorialPull({ body, attrib }) {
  return (
    <aside className="editorial-pull">
      <p className="editorial-pull-body">
        <span style={{ fontFamily: 'var(--ff-display)', fontSize: '1.6em', color: 'var(--blue)', verticalAlign: '-0.18em', marginRight: '6px' }}>“</span>
        {body}
        <span style={{ fontFamily: 'var(--ff-display)', fontSize: '1.6em', color: 'var(--blue)', verticalAlign: '-0.18em', marginLeft: '4px' }}>”</span>
        <span className="editorial-pull-attrib">— {attrib}</span>
      </p>
    </aside>
  );
}

function PullStrip({ children, attrib, sub }) {
  return (
    <section className="pullstrip">
      <div className="pullstrip-inner">
        <span className="pull-mark" aria-hidden>“</span>
        <p>{children}</p>
        <div className="pull-attrib">
          <b>{attrib}</b>
          {sub}
        </div>
      </div>
    </section>
  );
}

/* ===== Writer Card ====================================================== */
function WriterCard({ writer, index }) {
  const { name, first, last, team, league, sport, color, color2, voice, tier, headline, id } = writer;
  const [copied, setCopied] = useState(false);
  const cardRef = useRef(null);
  const onShare = (e) => {
    e.stopPropagation();
    const url = `https://thensmt.com/writers/${id}`;
    if (navigator.clipboard) navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  // tilt micro-interaction
  const onMove = (e) => {
    if (!cardRef.current) return;
    const r = cardRef.current.getBoundingClientRect();
    const cx = (e.clientX - r.left) / r.width - 0.5;
    const cy = (e.clientY - r.top) / r.height - 0.5;
    cardRef.current.style.setProperty('--tx', `${-cx * 4}px`);
    cardRef.current.style.setProperty('--ty', `${-cy * 4 - 3}px`);
    cardRef.current.style.setProperty('--rot', `${-cx * 0.6}deg`);
  };
  const onLeave = () => {
    if (!cardRef.current) return;
    cardRef.current.style.removeProperty('--tx');
    cardRef.current.style.removeProperty('--ty');
    cardRef.current.style.removeProperty('--rot');
  };

  return (
    <article
      ref={cardRef}
      className="wc"
      style={{
        '--accent': color,
        '--accent-2': color2 || '#fff',
        '--delay': `${index * 55}ms`,
        transform: 'translate3d(var(--tx,0), var(--ty,0), 0) rotate(var(--rot, -0.4deg))',
      }}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onShare(e); } }}
      aria-label={`${name}, AI writer covering ${team}, ${league}`}
    >
      <div className="wc-top">
        <div className="wc-badge">
          <BotMark accent="#F4EFE3" size={11} />
          <span className="wc-badge-text">AI WRITER · {tier}</span>
        </div>
        <div className="wc-no">№{String(index + 1).padStart(2, "0")}</div>
      </div>

      <div className="wc-avatar">
        <ProceduralAvatar name={name} color={color} color2={color2} />
        <div className="wc-avatar-scan" aria-hidden></div>
        <div className="wc-avatar-corner">PORTRAIT<br/>PROCEDURAL</div>
        <button
          className={`wc-share ${copied ? 'copied' : ''}`}
          onClick={onShare}
          aria-label={`Copy shareable link for ${name}`}
        >
          {copied ? "✓ COPIED" : "↗ SHARE"}
        </button>
      </div>

      <h3 className="wc-name">{first}<br/>{last}</h3>

      <div className="wc-beat">
        <span className="wc-beat-team">{team}</span>
        <span className="wc-beat-tags">
          <span>{league}</span>
          <span className="dot-sm"></span>
          <span>{sport}</span>
        </span>
      </div>

      <p className="wc-voice">"{voice}"</p>

      <div className="wc-sample" aria-hidden>
        <span className="wc-sample-eyebrow">SAMPLE HEADLINE · IN THIS WRITER'S VOICE</span>
        {headline}
      </div>

      <div className="wc-foot">
        <span className="wc-byline">BYLINE</span>
        <span className="wc-byline-text">
          <BotMark size={10} accent={color} />
          {name}, AI Sports Writer
        </span>
      </div>
    </article>
  );
}

/* ===== Flow Diagram ===================================================== */
function FlowDiagram() {
  const [active, setActive] = useState(2); // start on CLAUDE — feels right
  const [wrapRef, inView] = useInView({ threshold: 0.2 });

  const nodes = useMemo(() => ([
    { x: 95,   label: "ESPN",     sub: "BOX SCORES",   step: 0 },
    { x: 280,  label: "PYTHON",   sub: "ORCHESTRATOR", step: 1 },
    { x: 465,  label: "CLAUDE",   sub: "LLM DRAFT",    step: 2 },
    { x: 650,  label: "ADMIN",    sub: "is_active=0",  step: 3 },
    { x: 835,  label: "DISCORD",  sub: "REVIEW",       step: 4 },
    { x: 1020, label: "thensmt",  sub: "PUBLISH",      step: 5 },
  ]), []);

  const step = PIPELINE[active];

  return (
    <div className="flowwrap" ref={wrapRef}>
      <div className="flowwrap-head">
        <span className="lhs">
          <span className="flow-pulse"></span>
          <span className="flow-tag">PIPELINE · LIVE TRACE</span>
          <span style={{ opacity: 0.6 }}>CLICK A NODE</span>
        </span>
        <span style={{ opacity: 0.6, fontFamily: 'var(--ff-mono)' }}>CRON · 0 12 * * * UTC</span>
      </div>

      <svg viewBox="0 0 1120 240" className="flow" preserveAspectRatio="xMidYMid meet"
        role="img" aria-label="Data flow: ESPN box scores → Python orchestrator → Claude LLM draft → Admin staging → Discord review → publish to thensmt.com.">
        <defs>
          <marker id="arrow-blue" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 Z" fill="var(--blue)" />
          </marker>
        </defs>

        {/* spine */}
        <line x1="40" y1="120" x2="1080" y2="120" stroke="var(--rule)" strokeWidth="1" strokeDasharray="2 4" />

        {/* connectors */}
        {nodes.slice(0, -1).map((n, i) => (
          <line
            key={n.label}
            x1={n.x + 36} y1="120"
            x2={nodes[i + 1].x - 36} y2="120"
            stroke="var(--blue)" strokeWidth="1.6"
            markerEnd="url(#arrow-blue)"
            opacity="0.85"
          />
        ))}

        {/* traveling dots (only when in view) */}
        {inView && Array.from({ length: 3 }).map((_, i) => (
          <circle key={i} className="data-dot" cx="60" cy="120" r="4"
            style={{ animationDelay: `${i * 1.8}s` }}
          />
        ))}

        {/* nodes */}
        {nodes.map((n, i) => (
          <g
            key={n.label}
            className={`flow-node ${active === n.step ? 'active' : ''}`}
            transform={`translate(${n.x},120)`}
            onClick={() => setActive(n.step)}
            tabIndex={0}
            role="button"
            aria-label={`Step ${i + 1}: ${n.label} — ${n.sub}`}
            onKeyDown={(e) => { if (e.key === 'Enter') setActive(n.step); }}
          >
            <circle className="bg" r="36" />
            <text textAnchor="middle" y="-54" fontFamily="JetBrains Mono, monospace" fontSize="11" fill="var(--blue)" letterSpacing="1.4">
              0{i + 1}
            </text>
            <text className="label" textAnchor="middle" y="4" fontFamily="Archivo, sans-serif" fontWeight="800" fontSize="12.5" fill="var(--ink)">
              {n.label.toUpperCase()}
            </text>
            <text textAnchor="middle" y="60" fontFamily="JetBrains Mono, monospace" fontSize="10" fill="var(--muted)" letterSpacing="1.2">
              {n.sub}
            </text>
          </g>
        ))}

        {/* loop back arc */}
        <path d="M 1020 84 C 1020 30, 650 30, 650 84" fill="none" stroke="var(--blue)" strokeWidth="1.4" strokeDasharray="3 3" />
        <text x="835" y="22" textAnchor="middle" fontFamily="JetBrains Mono, monospace" fontSize="10" fill="var(--blue)" letterSpacing="1.8">
          HUMAN APPROVES → is_active = 1 → LIVE
        </text>

        {/* footer ribbons */}
        <g transform="translate(40, 210)">
          <rect x="0" y="0" width="180" height="22" fill="var(--blue)" />
          <text x="10" y="15" fontFamily="JetBrains Mono, monospace" fontSize="11" fill="#fff" letterSpacing="1.5">
            08:00 ET · DAILY DROP
          </text>
        </g>
        <g transform="translate(900, 210)">
          <rect x="0" y="0" width="180" height="22" fill="var(--ink)" />
          <text x="10" y="15" fontFamily="JetBrains Mono, monospace" fontSize="11" fill="var(--paper)" letterSpacing="1.5">
            $0 / MONTH · FREE TIER
          </text>
        </g>
      </svg>

      <div className="flow-detail" aria-live="polite">
        <div className="flow-detail-num">{step.n}</div>
        <div className="flow-detail-body">
          <strong>{step.t}</strong>
          <span>{step.long}</span>
        </div>
      </div>
    </div>
  );
}

/* ===== About-the-system details ========================================== */
function AboutDetails() {
  return (
    <details className="about-details">
      <summary>ABOUT THE SYSTEM — WHAT THE AI DOES, WHAT THE HUMAN STILL DOES</summary>
      <div className="about-cols">
        <div className="about-col">
          <h4>WHAT THE AI DOES WELL HERE</h4>
          <ul>
            <li><b>Speed.</b> A 500-word recap in roughly seven seconds — drafted before most beat writers have finished their first coffee.</li>
            <li><b>Consistency.</b> The same persona, the same length budget, the same structural beats. Every day. No off days.</li>
            <li><b>Stamina.</b> Three late games in one night, all on different time zones? It doesn't matter. The pipeline runs identically.</li>
            <li><b>Cost.</b> A penny or two per article. The economics of covering D-III hoops finally make sense.</li>
            <li><b>Coverage breadth.</b> Fourteen beats, simultaneously, without anyone having to choose between Mary Washington and the Wizards.</li>
          </ul>
        </div>
        <div className="about-col">
          <h4>WHAT THE HUMAN STILL DOES</h4>
          <ul>
            <li><b>Editorial review.</b> Every word is read by David before it's flipped live. Tone, facts, voice — all human checks.</li>
            <li><b>Original photography & video.</b> A model can't be on the sideline. We are.</li>
            <li><b>Breaking news & enterprise.</b> Trades, injuries, locker-room scoops, longform — the work that earns the masthead.</li>
            <li><b>Ethical decisions.</b> What to publish, what to hold, how to handle a sensitive story. The robot doesn't get a vote.</li>
            <li><b>Hitting publish.</b> Always. There is no auto-publish path. A human flips <code style={{ fontFamily: 'var(--ff-mono)' }}>is_active = 1</code>, every time.</li>
          </ul>
        </div>
      </div>
    </details>
  );
}

/* ===== Compare module =================================================== */
function CompareModule() {
  return (
    <section className="compare">
      <div className="compare-grid">
        <div className="compare-col">
          <div className="compare-label">
            <span style={{ color: 'var(--muted)' }}>↤ THE OLD MODEL</span>
          </div>
          <h3 className="compare-h">A traditional <em>beat-writer</em> newsroom.</h3>
          <div>
            {COMPARE.traditional.rows.map(([k, v]) => (
              <div className="compare-row" key={k}>
                <span className="compare-k">{k}</span>
                <span className="compare-v">{v}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="compare-col win">
          <div className="compare-label">
            <span className="pill" data-status="published" style={{ background: 'rgba(255,255,255,0.10)', borderColor: 'rgba(255,255,255,0.2)', color: '#fff' }}>NSMT</span>
            <span style={{ color: 'rgba(255,255,255,0.55)' }}>↦ THE MACHINE ROOM</span>
          </div>
          <h3 className="compare-h" style={{ color: '#fff' }}>An AI-drafted, <em>human-finished</em> newsroom.</h3>
          <div>
            {COMPARE.nsmt.rows.map(([k, v]) => (
              <div className="compare-row" key={k}>
                <span className="compare-k">{k}</span>
                <span className="compare-v">{v}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

/* ===== Confetti ========================================================== */
function Confetti({ burst, onDone }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!burst) return;
    const canvas = ref.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = window.innerWidth * dpr;
    canvas.height = window.innerHeight * dpr;
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    const W = window.innerWidth, H = window.innerHeight;
    const colors = ['#0E80FC', '#0E80FC', '#0E80FC', '#1B6FE0', '#fff', '#0B0B0C'];
    const N = 180;
    const ps = Array.from({ length: N }).map(() => ({
      x: W / 2 + (Math.random() - 0.5) * 200,
      y: H / 2 + (Math.random() - 0.5) * 60,
      vx: (Math.random() - 0.5) * 14,
      vy: -Math.random() * 16 - 4,
      g: 0.45 + Math.random() * 0.3,
      r: 4 + Math.random() * 6,
      rot: Math.random() * Math.PI,
      vr: (Math.random() - 0.5) * 0.4,
      c: colors[Math.floor(Math.random() * colors.length)],
      shape: Math.random() < 0.4 ? 'circ' : 'rect',
    }));
    let start;
    const tick = (t) => {
      if (!start) start = t;
      const el = t - start;
      ctx.clearRect(0, 0, W, H);
      ps.forEach(p => {
        p.x += p.vx; p.y += p.vy; p.vy += p.g; p.rot += p.vr;
        ctx.save();
        ctx.translate(p.x, p.y); ctx.rotate(p.rot);
        ctx.fillStyle = p.c;
        if (p.shape === 'circ') {
          ctx.beginPath(); ctx.arc(0, 0, p.r, 0, Math.PI * 2); ctx.fill();
        } else {
          ctx.fillRect(-p.r, -p.r * 0.6, p.r * 2, p.r * 1.2);
        }
        ctx.restore();
      });
      if (el < 3500) requestAnimationFrame(tick);
      else { ctx.clearRect(0, 0, W, H); onDone && onDone(); }
    };
    requestAnimationFrame(tick);
  }, [burst]);
  return <canvas ref={ref} className="confetti-canvas" aria-hidden></canvas>;
}

/* ===== Misc ============================================================== */
function RegistrationMark({ className }) {
  return (
    <svg className={className} width="22" height="22" viewBox="0 0 22 22" aria-hidden>
      <circle cx="11" cy="11" r="9" fill="none" stroke="currentColor" strokeWidth="1" />
      <line x1="11" y1="0" x2="11" y2="22" stroke="currentColor" strokeWidth="1" />
      <line x1="0" y1="11" x2="22" y2="11" stroke="currentColor" strokeWidth="1" />
    </svg>
  );
}

function Arrow() {
  return (
    <svg width="22" height="12" viewBox="0 0 22 12" aria-hidden>
      <path d="M0 6 H20 M14 1 L20 6 L14 11" fill="none" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

function HasTip({ children, tip }) {
  return (
    <span className="has-tip" tabIndex={0}>
      {children}
      <span className="tip-pop" role="tooltip">{tip}</span>
    </span>
  );
}

Object.assign(window, {
  useInView, useCountUp, useStickyShow, useKonami, useTheme,
  Splash, BotMark, TopBar, Ticker, StickyMasthead, StaggerLine, StaggerWrap,
  Hero, TodayLineup, EditorialPull, PullStrip, WriterCard, FlowDiagram,
  AboutDetails, CompareModule, Confetti, RegistrationMark, Arrow, HasTip,
});
