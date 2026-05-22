/* NSMT — main page */

const { useState: useStateA, useEffect: useEffectA, useCallback: useCallbackA } = React;

function AIWriters() {
  const [now, setNow] = useStateA("");
  const [theme, toggleTheme] = useTheme();
  const [poster, setPoster] = useStateA(false);
  const [confetti, setConfetti] = useStateA(0);

  useEffectA(() => {
    const tick = () => {
      const d = new Date();
      const opts = { timeZone: "America/New_York", hour12: false };
      const time = d.toLocaleTimeString("en-US", { ...opts, hour: "2-digit", minute: "2-digit", second: "2-digit" });
      const date = d.toLocaleDateString("en-US", { ...opts, weekday: "short", month: "short", day: "2-digit", year: "numeric" }).toUpperCase();
      setNow(`${date} · ${time} ET`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  useKonami(useCallbackA(() => setConfetti(c => c + 1), []));

  if (poster) return (
    <>
      <PosterMode onClose={() => setPoster(false)} />
    </>
  );

  return (
    <div className="nsmt-root" data-screen-label="01 AI Writers page">
      <Splash />
      <Confetti burst={confetti} onDone={() => {}} key={confetti} />
      <NSMTTweaks />

      <StickyMasthead now={now} />
      <TopBar now={now} theme={theme} onToggleTheme={toggleTheme} onPoster={() => setPoster(true)} />
      <Ticker />

      <Hero now={now} />

      <TodayLineup now={now} />

      <PullStrip
        attrib="NSMT EDITORIAL STANDARD"
        sub="POSTED IN THE MACHINE ROOM"
      >
        We don't hide the machine. Every article carries a robot in the byline —
        because <u>transparency is the only ethical way</u> to do this.
      </PullStrip>

      {/* MASTHEAD GRID */}
      <section className="masthead" id="writers" aria-labelledby="masthead-h">
        <div className="section-head">
          <div className="section-eyebrow">
            <span className="eyebrow-num">§ 01</span>
            <span className="eyebrow-line"></span>
            <span>THE MASTHEAD</span>
          </div>
          <h2 className="section-title" id="masthead-h">
            Meet the <em>staff.</em>
            <span className="section-aside">Fourteen beat writers. Zero pulses. Click a card to copy its link.</span>
          </h2>
        </div>
        <div className="writers-grid">
          {WRITERS.map((w, i) => <WriterCard key={w.id} writer={w} index={i} />)}
        </div>
      </section>

      <EditorialPull
        body={<>The DMV has fourteen pro and college programs worth covering and <b>not nearly enough humans</b> left to cover them.</>}
        attrib="THE PROBLEM WE BUILT THIS FOR"
      />

      {/* HOW IT WORKS */}
      <section className="how" id="how" aria-labelledby="how-h">
        <div className="section-head">
          <div className="section-eyebrow">
            <span className="eyebrow-num">§ 02</span>
            <span className="eyebrow-line"></span>
            <span>THE WIRE</span>
          </div>
          <h2 className="section-title" id="how-h">
            How a recap becomes <em>a recap.</em>
          </h2>
        </div>

        <FlowDiagram />

        <ol className="steps" aria-label="Pipeline steps">
          {PIPELINE.map((s) => (
            <li className="step" key={s.n}>
              <span className="step-n">{s.n}</span>
              <div className="step-body">
                <h3>{s.t}</h3>
                <p>{s.d}</p>
              </div>
            </li>
          ))}
        </ol>

        <AboutDetails />
      </section>

      <CompareModule />

      <EditorialPull
        body={<>A <b>force multiplier</b> for the small outlets the internet keeps trying to kill.</>}
        attrib="HOWE NSMT THINKS ABOUT AI"
      />

      {/* STACK */}
      <section className="stack" id="stack" aria-labelledby="stack-h">
        <div className="section-head">
          <div className="section-eyebrow">
            <span className="eyebrow-num">§ 03</span>
            <span className="eyebrow-line"></span>
            <span>THE EQUIPMENT</span>
          </div>
          <h2 className="section-title" id="stack-h">
            What it's built on.
            <span className="section-aside">Hover any technology for a one-line explainer.</span>
          </h2>
        </div>
        <div className="stack-grid">
          {STACK.map((s) => (
            <div className="stack-row" key={s.k}>
              <span className="stack-k">{s.k}</span>
              <span className="stack-dots" aria-hidden>·····························································</span>
              <span className="stack-v">
                <HasTip tip={s.tip}>{s.v}</HasTip>
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* WHY */}
      <section className="why" id="why" aria-labelledby="why-h">
        <div className="why-grid">
          <div className="why-eyebrow">
            <span className="eyebrow-num">§ 04</span>
            <span className="eyebrow-line"></span>
            <span>EDITORIAL STANCE</span>
          </div>
          <h2 className="why-title" id="why-h">
            Why a <em>solo founder</em> built a robot newsroom.
          </h2>
          <div className="why-cols">
            <p>
              Local sports coverage is collapsing. Beat writers are being cut.
              The DMV has fourteen pro and college programs worth covering and not nearly
              enough humans left to cover them. So we built a machine room — a small,
              cheap, honest one — and put a human at the door.
            </p>
            <p>
              Every NSMT recap is drafted by an AI writer with a name, a voice, and a beat.
              Every recap is reviewed by a person before it goes live. Every byline tells
              you, plainly, that a model wrote the first draft. <b>No pretense, no ghosts.</b>
            </p>
            <p>
              We think this is what AI in journalism should look like: assistive, not
              extractive. Named, not anonymous. Edited, not auto-published. A force
              multiplier for the small outlets the internet keeps trying to kill.
            </p>
          </div>
        </div>
      </section>

      {/* OTHER */}
      <section className="other" aria-labelledby="other-h">
        <div className="section-head">
          <div className="section-eyebrow">
            <span className="eyebrow-num">§ 05</span>
            <span className="eyebrow-line"></span>
            <span>ELSEWHERE IN THE BUILDING</span>
          </div>
          <h2 className="section-title" id="other-h">
            The newsroom is automated in <em>more ways than one.</em>
          </h2>
        </div>
        <ul className="other-list">
          {OTHER.map((line, i) => (
            <li key={i}>
              <span className="other-n">№{String(i + 1).padStart(2, "0")}</span>
              <span className="other-t">{line}</span>
              <span className="other-mark">▢</span>
            </li>
          ))}
        </ul>
      </section>

      {/* META CALLOUT */}
      <section className="meta-callout" aria-label="Meta transparency callout">
        <div className="meta-card">
          <span className="meta-tag">META · TRANSPARENCY</span>
          <p style={{ margin: 0 }}>
            <b>What you're reading right now</b> was designed by an AI too — drafted in
            <i> Claude.ai's design tool</i>, iterated by David, every byte of copy approved by
            a human. The same posture as our recaps: <b>the robot helps, the human ships.</b>
            <br />
            <span style={{ fontFamily: 'var(--ff-mono)', fontSize: 11, letterSpacing: 1.6, color: 'var(--muted)' }}>
              · psst — try ↑ ↑ ↓ ↓ ← → ← → B A ·
            </span>
          </p>
        </div>
      </section>

      {/* CTA */}
      <section className="cta" aria-label="Call to action">
        <div className="cta-inner">
          <div className="cta-left">
            <div className="cta-eyebrow">— END OF DISPATCH —</div>
            <h2 className="cta-title">
              Read the writers.<br/>
              <em>Watch the byline.</em>
            </h2>
          </div>
          <div className="cta-right">
            <a href="https://thensmt.com" className="btn btn--primary" target="_blank" rel="noreferrer">
              <span>VISIT THENSMT.COM</span>
              <Arrow />
            </a>
            <a href="https://twitter.com/the_nsmt" className="btn btn--ghost" target="_blank" rel="noreferrer">
              <span>FOLLOW @THE_NSMT</span>
              <Arrow />
            </a>
            <a href="mailto:david@thensmt.com" className="btn btn--ghost btn--xs">
              <span>HIRE NSMT FOR COVERAGE</span>
              <Arrow />
            </a>
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="foot" role="contentinfo">
        <div className="foot-inner">
          <div className="foot-block">
            <div className="foot-logo"><i>NSMT</i> <span className="b">·</span></div>
            <p>Nova Sports Media Team — an independent DMV sports outlet covering 14 pro and college teams across Washington, Maryland, and Virginia.</p>
            <p style={{ marginTop: 12 }}>
              <b>Built by David Gaylor</b> &nbsp;·&nbsp; <i style={{ color: 'var(--blue)' }}>human + Claude</i>
            </p>
          </div>
          <div className="foot-block">
            <h5>SITE</h5>
            <ul>
              <li><a href="https://thensmt.com">thensmt.com</a></li>
              <li><a href="https://twitter.com/the_nsmt">@the_nsmt</a></li>
              <li><a href="mailto:david@thensmt.com">david@thensmt.com</a></li>
              <li><a href="#" onClick={(e)=>e.preventDefault()}>AI transparency report →</a></li>
            </ul>
          </div>
          <div className="foot-block">
            <h5>POWERED BY</h5>
            <div className="foot-badges">
              <span className="foot-badge">⛁ CLAUDE</span>
              <span className="foot-badge">▶ PYTHON</span>
              <span className="foot-badge">⚡ CF WORKERS</span>
              <span className="foot-badge">⤴ GH ACTIONS</span>
              <span className="foot-badge">◇ AWS</span>
              <span className="foot-badge">💬 DISCORD</span>
              <span className="foot-badge">◢ ESPN API</span>
              <span className="foot-badge">⌬ REACT</span>
            </div>
            <p style={{ marginTop: 14, fontSize: 11, opacity: 0.65, fontFamily: 'var(--ff-mono)', letterSpacing: 1.4 }}>
              SET IN FRAUNCES · ARCHIVO · JETBRAINS MONO
            </p>
          </div>
        </div>
        <div className="foot-bottom">
          <span>© {new Date().getFullYear()} NOVA SPORTS MEDIA TEAM</span>
          <span className="dim">·</span>
          <span>WASHINGTON · MARYLAND · VIRGINIA</span>
          <span className="sp"></span>
          <span className="dim">A HUMAN HIT PUBLISH.</span>
        </div>
      </footer>
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<AIWriters />);
