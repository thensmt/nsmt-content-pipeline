/* NSMT — Poster mode: B&W LinkedIn carousel (10 slides) */

function PosterMode({ onClose }) {
  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = ''; };
  }, []);

  const slides = [
    {
      kind: 'cover',
      kicker: 'A NSMT DISPATCH · 2026',
      title: ['We taught', { em: '14 AI writers' }, 'how to cover', { mark: 'sports in the DMV.' }],
      deck: 'A solo founder. A daily 8am pipeline. Fourteen AI sportswriters with names, beats and voices of their own.',
      footer: 'SWIPE → · 1 of 10',
    },
    {
      kind: 'stat',
      kicker: '§ 01 · THE PROBLEM',
      title: 'Local sports coverage is collapsing.',
      stat: '— BEATS',
      deck: 'The DMV has fourteen pro and college programs worth covering and not enough humans left to cover them.',
      footer: '2 / 10',
    },
    {
      kind: 'megastat',
      kicker: '§ 02 · THE SCALE',
      title: 'Fourteen named AI writers.',
      stat: '14',
      sub: 'one for every NSMT beat',
      deck: 'Each writer has a frozen persona — name, prose tics, length budget, beat-specific instincts. Same byline every day.',
      footer: '3 / 10',
    },
    {
      kind: 'megastat',
      kicker: '§ 03 · THE TIMING',
      title: 'Every morning at eight.',
      stat: '08:00',
      statSup: 'ET',
      sub: 'GitHub Actions cron · 0 12 * * * UTC',
      deck: 'A Python script wakes up, asks ESPN what happened last night, and hands the box scores to the writers.',
      footer: '4 / 10',
    },
    {
      kind: 'megastat',
      kicker: '§ 04 · THE COST',
      title: 'Total monthly infrastructure cost:',
      stat: '$0',
      sub: 'all on free tiers',
      deck: 'Cloudflare Workers. GitHub Actions. AWS free tier. Discord. A few cents per Claude call. That\'s the whole bill.',
      footer: '5 / 10',
    },
    {
      kind: 'list',
      kicker: '§ 05 · THE STAFF',
      title: 'The masthead.',
      items: WRITERS.slice(0, 8).map(w => ({ k: w.tier, v: `${w.name} — ${w.team}` })),
      footer: '6 / 10',
    },
    {
      kind: 'list',
      kicker: '§ 05 · THE STAFF (CONT.)',
      title: 'The college beats.',
      items: WRITERS.slice(8).map(w => ({ k: w.tier, v: `${w.name} — ${w.team}` })),
      footer: '7 / 10',
    },
    {
      kind: 'pipeline',
      kicker: '§ 06 · THE WIRE',
      title: 'How a recap becomes a recap.',
      footer: '8 / 10',
    },
    {
      kind: 'quote',
      kicker: '§ 07 · THE STANDARD',
      quote: 'We don\'t hide the machine. Every article carries a robot in the byline — because transparency is the only ethical way to do this.',
      attrib: 'NSMT EDITORIAL STANDARD',
      footer: '9 / 10',
    },
    {
      kind: 'cta',
      kicker: '— END OF DISPATCH —',
      title: 'Read the writers. Watch the byline.',
      lines: ['thensmt.com', '@the_nsmt', 'BUILT BY DAVID GAYLOR · HUMAN + CLAUDE'],
      footer: '10 / 10',
    },
  ];

  return (
    <div className="poster-overlay" role="dialog" aria-label="Poster mode — LinkedIn carousel slides">
      <div className="poster-bar">
        <span><b>POSTER MODE</b> · B&W · 1:1 · 10 SLIDES · LINKEDIN-READY</span>
        <span style={{ flex: 1 }}></span>
        <button onClick={() => window.print()}>↓ PRINT / SAVE PDF</button>
        <button onClick={onClose}>✕ CLOSE</button>
      </div>
      <div className="poster-grid">
        {slides.map((s, i) => <PosterSlide key={i} slide={s} index={i} />)}
      </div>
    </div>
  );
}

function PosterSlide({ slide, index }) {
  return (
    <article className="poster-slide" data-screen-label={`${String(index + 1).padStart(2, '0')} POSTER`}>
      <div className="poster-head">
        <span>{slide.kicker}</span>
        <span>NSMT · NOVA SPORTS MEDIA TEAM</span>
      </div>

      {slide.kind === 'cover' && (
        <>
          <h2 className="poster-headline" style={{ fontSize: 'clamp(48px, 6vw, 84px)' }}>
            {slide.title.map((t, i) => {
              if (typeof t === 'string') return <span key={i}>{t} </span>;
              if (t.em) return <em key={i}>{t.em} </em>;
              if (t.mark) return <span key={i} style={{ background: '#000', color: '#fff', padding: '0 0.12em' }}>{t.mark}</span>;
              return null;
            })}
          </h2>
          <p className="poster-deck">{slide.deck}</p>
          <div style={{ marginTop: 'auto', display: 'flex', gap: '32px', borderTop: '1px solid #000', paddingTop: '14px' }}>
            <PosterMini stat="14" label="AI WRITERS" />
            <PosterMini stat="08:00" label="ET DAILY" />
            <PosterMini stat="$0" label="PER MONTH" />
          </div>
        </>
      )}

      {slide.kind === 'stat' && (
        <>
          <h2 className="poster-headline">{slide.title}</h2>
          <div className="poster-stat" style={{ marginTop: '-12px' }}>14<sup>{slide.stat}</sup></div>
          <p className="poster-deck">{slide.deck}</p>
        </>
      )}

      {slide.kind === 'megastat' && (
        <>
          <h2 className="poster-headline">{slide.title}</h2>
          <div className="poster-stat">
            {slide.stat}{slide.statSup && <sup>{slide.statSup}</sup>}
          </div>
          <div style={{ fontFamily: 'var(--ff-mono)', fontSize: 13, letterSpacing: 2, opacity: 0.7, marginBottom: 16 }}>
            — {slide.sub}
          </div>
          <p className="poster-deck">{slide.deck}</p>
        </>
      )}

      {slide.kind === 'list' && (
        <>
          <h2 className="poster-headline">{slide.title}</h2>
          <ul className="poster-list" style={{ marginTop: 18 }}>
            {slide.items.map((it, i) => (
              <li key={i}>
                <span className="lab">№{String(i + 1).padStart(2, '0')} · {it.k}</span>
                <span>{it.v}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      {slide.kind === 'pipeline' && (
        <>
          <h2 className="poster-headline">{slide.title}</h2>
          <div style={{ marginTop: 24 }}>
            {PIPELINE.map((s, i) => (
              <div key={s.n} style={{
                display: 'grid', gridTemplateColumns: '80px 1fr',
                borderTop: i === 0 ? '1px solid #000' : '0',
                borderBottom: '1px solid #000',
                padding: '14px 0',
                gap: 18,
              }}>
                <div style={{ fontFamily: 'var(--ff-display)', fontStyle: 'italic', fontWeight: 900, fontSize: 36, lineHeight: 1, letterSpacing: '-0.04em' }}>{s.n}</div>
                <div>
                  <div style={{ fontFamily: 'var(--ff-mono)', fontSize: 10, letterSpacing: 2, fontWeight: 700, marginBottom: 3 }}>{s.t}</div>
                  <div style={{ fontFamily: 'var(--ff-display)', fontSize: 16, lineHeight: 1.35 }}>{s.d}</div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {slide.kind === 'quote' && (
        <div style={{ margin: 'auto 0', paddingLeft: 32, borderLeft: '6px solid #000' }}>
          <div style={{ fontFamily: 'var(--ff-display)', fontStyle: 'italic', fontSize: 'clamp(34px, 4vw, 56px)', lineHeight: 1.18, letterSpacing: '-0.02em' }}>
            “{slide.quote}”
          </div>
          <div style={{ fontFamily: 'var(--ff-mono)', fontSize: 11, letterSpacing: 2.4, marginTop: 24, opacity: 0.7 }}>
            — {slide.attrib}
          </div>
        </div>
      )}

      {slide.kind === 'cta' && (
        <>
          <h2 className="poster-headline" style={{ fontSize: 'clamp(52px, 7vw, 96px)' }}>{slide.title}</h2>
          <div style={{ marginTop: 'auto' }}>
            {slide.lines.map((l, i) => (
              <div key={i} style={{
                fontFamily: 'var(--ff-display)', fontWeight: 900, fontStyle: 'italic',
                fontSize: i === 0 ? 52 : (i === 1 ? 32 : 14),
                lineHeight: 1.05,
                marginBottom: 8,
                letterSpacing: '-0.02em',
                fontFamilyOverride: i === 2 ? 'var(--ff-mono)' : undefined,
                fontStyleOverride: undefined,
              }}>
                <span style={i === 2 ? { fontFamily: 'var(--ff-mono)', fontStyle: 'normal', fontWeight: 700, letterSpacing: '2.4px' } : {}}>
                  {l}
                </span>
              </div>
            ))}
          </div>
        </>
      )}

      <div className="poster-footer">
        <span>{slide.footer || ''}</span>
        <span>NSMT · {new Date().getFullYear()} · DMV</span>
      </div>
    </article>
  );
}

function PosterMini({ stat, label }) {
  return (
    <div>
      <div style={{ fontFamily: 'var(--ff-display)', fontWeight: 900, fontStyle: 'italic', fontSize: 52, lineHeight: 0.95, letterSpacing: '-0.05em' }}>{stat}</div>
      <div style={{ fontFamily: 'var(--ff-mono)', fontSize: 10, letterSpacing: 2, opacity: 0.7, marginTop: 4 }}>{label}</div>
    </div>
  );
}

window.PosterMode = PosterMode;
