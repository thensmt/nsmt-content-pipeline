/* NSMT — Tweak controls (3 expressive axes) */

function NSMTTweaks() {
  const [t, setTweak] = useTweaks(/*EDITMODE-BEGIN*/{
    "mode": "broadsheet",
    "palette": "nsmt",
    "rhythm": "editorial"
  }/*EDITMODE-END*/);

  React.useEffect(() => {
    const root = document.querySelector('.nsmt-root');
    if (!root) return;
    root.dataset.mode = t.mode;
    root.dataset.palette = t.palette;
    root.dataset.rhythm = t.rhythm;
  }, [t.mode, t.palette, t.rhythm]);

  // Render a small "you are here" caption inside the panel to telegraph the combined mood
  const captions = {
    nsmt:      "NSMT Blue — house style.",
    wire:      "Newsstand red + cream — wire-service.",
    night:     "Amber on slate — late-night broadcast.",
  };
  const modes = {
    broadsheet: "Big italic display, broadsheet vibes.",
    control:    "Mono-heavy, technical, control-room.",
    roster:     "Cards & avatars get sports-roster trim.",
  };
  const rhythms = {
    tight:     "Compressed — more content per screen.",
    editorial: "House density.",
    sprawl:    "Editorial whitespace, oversized type.",
  };

  return (
    <TweaksPanel title="Tweaks">
      <TweakSection label="Editorial Mode">
        <TweakRadio
          label="Treatment"
          value={t.mode}
          options={[
            { value: 'broadsheet', label: 'Print' },
            { value: 'control', label: 'Control' },
            { value: 'roster', label: 'Cards' },
          ]}
          onChange={v => setTweak('mode', v)}
        />
        <div className="twk-hint">{modes[t.mode]}</div>
      </TweakSection>

      <TweakSection label="Color Story">
        <TweakRadio
          label="Palette"
          value={t.palette}
          options={[
            { value: 'nsmt',  label: 'NSMT'  },
            { value: 'wire',  label: 'Wire'  },
            { value: 'night', label: 'Night' },
          ]}
          onChange={v => setTweak('palette', v)}
        />
        <div className="twk-palette-row">
          <NSMTSwatch palette="nsmt"  active={t.palette === 'nsmt'}  onClick={() => setTweak('palette','nsmt')}  />
          <NSMTSwatch palette="wire"  active={t.palette === 'wire'}  onClick={() => setTweak('palette','wire')}  />
          <NSMTSwatch palette="night" active={t.palette === 'night'} onClick={() => setTweak('palette','night')} />
        </div>
        <div className="twk-hint">{captions[t.palette]}</div>
      </TweakSection>

      <TweakSection label="Display Rhythm">
        <TweakRadio
          label="Spacing"
          value={t.rhythm}
          options={[
            { value: 'tight',     label: 'Tight'  },
            { value: 'editorial', label: 'Editor' },
            { value: 'sprawl',    label: 'Sprawl' },
          ]}
          onChange={v => setTweak('rhythm', v)}
        />
        <div className="twk-hint">{rhythms[t.rhythm]}</div>
      </TweakSection>

      <style>{`
        .twk-hint {
          font-family: 'JetBrains Mono', ui-monospace, monospace;
          font-size: 10px;
          letter-spacing: 0.5px;
          opacity: 0.55;
          margin: -2px 0 4px;
          line-height: 1.4;
        }
        .twk-palette-row {
          display: grid; grid-template-columns: 1fr 1fr 1fr;
          gap: 6px; margin: 8px 0 4px;
        }
        .twk-pal {
          border: 1.5px solid transparent;
          border-radius: 6px;
          padding: 0;
          cursor: pointer;
          height: 36px;
          display: grid; grid-template-columns: 2fr 1fr 1fr;
          overflow: hidden;
          transition: transform 120ms;
        }
        .twk-pal:hover { transform: translateY(-1px); }
        .twk-pal.active { border-color: #0E80FC; box-shadow: 0 0 0 2px rgba(14,128,252,0.18); }
        .twk-pal span { display: block; height: 100%; }
      `}</style>
    </TweaksPanel>
  );
}

function NSMTSwatch({ palette, active, onClick }) {
  const swatches = {
    nsmt:  ['#0E80FC', '#0B0B0C', '#F4EFE3'],
    wire:  ['#C0252F', '#11254E', '#F1E5CC'],
    night: ['#FFC107', '#F4EFE3', '#0E1218'],
  };
  const [a, b, c] = swatches[palette];
  return (
    <button
      type="button"
      className={`twk-pal ${active ? 'active' : ''}`}
      onClick={onClick}
      aria-label={`${palette} palette`}
      aria-pressed={active}
    >
      <span style={{ background: a }}></span>
      <span style={{ background: b }}></span>
      <span style={{ background: c }}></span>
    </button>
  );
}

window.NSMTTweaks = NSMTTweaks;
