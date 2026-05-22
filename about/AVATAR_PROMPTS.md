# NSMT AI Writer Avatar Prompts

Generate 14 consistent photorealistic portraits in ChatGPT (DALL-E 3) for use
as `author_image` on each writer's articles + the AIWriters.jsx page.

## Workflow

1. Open a NEW chat in ChatGPT
2. **Paste the master setup prompt below first.** Send. ChatGPT will acknowledge.
3. **Then paste each writer prompt as its own message, one at a time.** ChatGPT
   generates one image per message.
4. If a portrait isn't quite right, reply with a tweak ("more weathered,"
   "younger," "less smile") instead of regenerating from scratch — ChatGPT
   keeps context within the chat.
5. Download each final image (right-click → Save Image As). Suggested naming:
   `tucker.jpg`, `wexler.jpg`, `frost.jpg`, etc. (matching the writer IDs in
   `AIWriters.jsx`).
6. Upload to your admin's image storage (same place `blogs/authors/` lives),
   then send me the URL pattern and I'll wire them into the recap script.

---

## Editorial use & guardrails

These avatars exist to give NSMT a consistent editorial brand system across
14 beats. They are not stand-ins for human staff and shouldn't be presented
as if they were.

- **Best use:** article bylines, the AIWriters page, newsletter headers,
  occasional pull-quote cards.
- **Avoid:** making these portraits the center of social content too often.
  They're support furniture for the writing, not characters.
- **Avoid:** presenting them like real human staff members without a clear
  internal/editorial policy. Every byline carries the 🤖 badge for a reason.
- **The point** is a coherent editorial brand — a consistent regional sports
  newsroom look — not to trick the reader.

---

## NSMT Wire — what this is building toward

> **NSMT Wire** — a regional sports wire-style content engine for DMV sports.

The avatar system is one piece of a larger product:

- Fast local sports coverage across the DMV (DC, Maryland, Virginia)
- AI-assisted drafts on a fixed daily cadence
- Human editorial review on every piece before it ships
- Consistent beat voices a regular reader can recognize over time
- Scalable coverage across pro, college, high school, AAU, and community sports

The tone is ambitious without being corny. Sober, regional, beat-driven. The
goal is something that reads like a real DMV sports wire — not a content
farm, not a personality play.

---

## MASTER SETUP PROMPT (paste this FIRST, send once, then proceed to the 14 writer prompts)

```
I'm going to send you 14 separate messages, each describing a different sports
journalist. For each one, generate ONE photorealistic editorial portrait
following these consistent specs. Do not vary the style across the 14 — only
the subject changes. Confirm you understand, then I'll send the first.

STYLE
- Photorealistic editorial photography, not illustration, not painted, not
  stylized. Should look like a real working journalist photographed for a
  newspaper byline.
- Head-and-shoulders crop, subject looking directly at camera with a natural,
  unposed expression (slight smile or neutral — never a stock-photo grin).
- Shot on 85mm portrait lens, shallow depth of field (~f/2.0). Soft natural
  window light from camera-left, gentle rim light from right.
- 1:1 square aspect ratio.
- No text, no captions, no logos in the image.

REALISM REQUIREMENTS — AVOID AI TELLS
This is the most important section. Defaults will produce glossy, model-
perfect, airbrushed faces. Do not do that. Instead:
- Realistic skin texture — visible pores, slight imperfections, real-skin
  tone variation. NOT smoothed, NOT airbrushed, NOT plastic.
- Slight asymmetry in features (eyebrows, eyes, jawline). NOT model-perfect
  symmetry. Real faces are uneven.
- Minor signs of age or fatigue where appropriate — subtle under-eye bags,
  faint lines, lived-in faces. These are working journalists, not models.
- Natural-looking teeth if visible (slight color, not whitened/veneered) and
  natural eyes (no overly bright, glassy, AI-rendered "wet" eyes).
- NO over-smoothed skin. NO airbrushed look. NO model-perfect faces. NO
  glossy stock-photo aesthetic. NO uncanny symmetry.
- Believable working-journalist energy — clothing slightly lived-in, hair
  not freshly styled for the camera.
- These should look like real beat writers who have been working games,
  deadlines, and press rooms — not actors hired for a stock photo shoot.

BACKGROUND
- Slightly out-of-focus setting appropriate to the writer's beat tier
  (described per-writer below). Heavily blurred — backgrounds should be
  felt, not read.
- Subtle hints of the writer's team color palette in the background through
  decor, banners, or apparel — but NO real team logos, NO team names, NO
  trademarked imagery. Team affiliation should be FELT, not declared.

ATTIRE
- Professional-casual journalist clothing — polos, button-downs, light
  jackets, quarter-zips — in the writer's team color palette.
- NO replica jerseys, NO team logos on clothing.

DIVERSITY
- The 14 writers should feel like a real, modern newsroom. Vary ethnicities,
  ages (late 20s through late 50s), genders, builds, and personal styles.

Reply "Ready" and I'll send the first subject.
```

---

## The 14 writer prompts (paste each as its own message, in any order)

Each prompt is followed by an EDITORIAL VOICE block describing how that
writer covers their beat — for use in prompt construction, byline copy, and
style sheets. The EDITORIAL VOICE block is NOT part of the image prompt;
only the fenced code block goes into ChatGPT.

### 1. Maxwell Tucker — Washington Commanders (NFL)

```
Writer 1 of 14: Maxwell Tucker — covers the Washington pro football team.
A white man in his late 50s, weathered face with gentle smile lines, gray-flecked dark beard,
reading glasses pushed up onto his forehead. Wearing a burgundy quarter-zip
pullover over a tan henley. Comfortable, slightly amused expression — looks
like he's covered 200 NFL games and is mid-thought about a 3rd-down call.
Background: blurred established NFL press box — long counter, monitors in
deep focus, burgundy stadium banner hinted at the edge of frame. A
well-funded major-league press setting.
```

**EDITORIAL VOICE — Maxwell Tucker**
- Tone: old-school football columnist. Plain prose, dry humor.
- Specialty: trenches, coaching decisions, situational football, toughness.
- Story angle: how the game was actually won or lost — blocks, calls,
  matchups — not the highlight that bounced first.
- Cares about: process, preparation, line play, fourth-quarter execution.
- Avoids: hot-take nonsense and overreaction to one game or one player.

### 2. Casper Wexler — Washington Wizards (NBA)

```
Writer 2 of 14: Casper Wexler — covers the Washington pro basketball team.
An Asian-American man in his early 30s, clean-cut with short black hair,
dark thin-rimmed glasses. Wearing a navy blue button-down with sleeves rolled
to the forearm, modern slim fit. Sharp, analytical expression — like he's
mid-thought about pace and spacing. Background: blurred professional NBA
arena-adjacent workspace — long desk with multiple monitors showing
spreadsheets, NBA-style hardwood barely visible in deep blur, faint red and
navy color accents.
```

**EDITORIAL VOICE — Casper Wexler**
- Tone: analytics-driven NBA writer. Calm, precise, evidence-led.
- Specialty: pace, spacing, lineup data, roster construction, shot quality.
- Story angle: what the numbers say about how the game actually played out,
  beyond the box score.
- Cares about: process over results, sustainable team-building, lineup data.
- Avoids: narrative-by-vibes, clutch-gene hagiography, MVP-narrative writing.

### 3. Ada Frost — Washington Capitals (NHL)

```
Writer 3 of 14: Ada Frost — covers the Washington pro hockey team.
A white woman in her mid-30s, athletic build, blonde hair pulled back in a
loose low ponytail. Wearing a red knit pullover over a white collared shirt.
Direct, no-nonsense expression with a slight smile — like she's about to ask a
coach a tough postgame question. Background: blurred NHL press-box setting —
hockey-rink edge deep in blur, faint red boards barely visible, hint of
professional arena lighting overhead.
```

**EDITORIAL VOICE — Ada Frost**
- Tone: direct hockey beat reporter. No fluff. Postgame-scrum honest.
- Specialty: accountability, special teams, goaltending, playoff habits.
- Story angle: what the team did or didn't do, named honestly, with the
  receipts from the game tape.
- Cares about: goaltending detail, defensive structure, PK/PP discipline.
- Avoids: fight-clip culture, enforcer-as-hero takes, "grit" as a metric.

### 4. Marcus Bell — Washington Nationals (MLB)

```
Writer 4 of 14: Marcus Bell — covers the Washington pro baseball team.
A Black man in his late 50s, salt-and-pepper hair, kind eyes behind aviator-
style glasses. Wearing a cream button-down with the sleeves rolled to the
elbows, navy braces (suspenders) visible. Scholarly and warm — looks like a
baseball historian who knows every ERA from 1972 onward. Background: blurred
established MLB press box — long press counter, weathered bookshelf with old
folders and a baseball sitting on the desk, professional ballpark hints in
deep focus.
```

**EDITORIAL VOICE — Marcus Bell**
- Tone: baseball-historian voice. Patient, contextual, long-memoried.
- Specialty: context, patience, player development, the 162-game arc.
- Story angle: what a single game says (or doesn't say) inside the long
  season — and what the history of the position tells us.
- Cares about: development curves, bullpen usage trends, defensive
  positioning, the texture of a baseball summer.
- Avoids: small-sample-size hyperbole, "is X a Hall of Famer" after April.

### 5. Sibyl Avery — Washington Mystics (WNBA)

```
Writer 5 of 14: Sibyl Avery — covers the Washington pro women's basketball team.
A Black woman in her early 30s, natural hair styled with care, small gold
hoop earrings. Wearing a burgundy blazer over a white shell top. Insightful,
knowing expression — looks like she sees every screen-and-roll coming three
seconds before it happens. Background: blurred professional WNBA arena —
basketball court markings barely visible, red and bronze color accents in
deep focus, hint of arena lighting.
```

**EDITORIAL VOICE — Sibyl Avery**
- Tone: sharp WNBA analyst. Confident, basketball-first.
- Specialty: guard play, defensive versatility, league growth and structure.
- Story angle: the basketball reason a game went the way it did — and how
  that fits the league's bigger trajectory.
- Cares about: player development, defensive schemes, the actual game.
- Avoids: gendered framing, manufactured rivalry coverage, "rivalry porn."

### 6. Wren Holloway — Washington Spirit (NWSL)

```
Writer 6 of 14: Wren Holloway — covers the Washington pro women's soccer team.
A Latina woman in her early 30s, athletic build, short dark hair styled
modern. Wearing a fitted navy quarter-zip with subtle red trim, a press
lanyard around her neck. Confident, tactical expression — like she's tracking
pressing triggers. Background: blurred modern NWSL stadium at dusk —
floodlights, urban skyline barely visible beyond, field-adjacent vantage,
international/modern feel with hints of red and navy.
```

**EDITORIAL VOICE — Wren Holloway**
- Tone: tactical soccer writer. International framing, coach-adjacent.
- Specialty: pressing triggers, spacing, transitions, player movement,
  in-game adjustments.
- Story angle: what the tactical pattern of the match actually was — where
  the game was won between the lines.
- Cares about: structure, off-ball runs, sequence-level detail.
- Avoids: xG-quoting without context, trophy-tier reductionism, treating
  NWSL as a development league for elsewhere.

### 7. Beckett Calloway — DC United (MLS)

```
Writer 7 of 14: Beckett Calloway — covers the Washington pro men's soccer team.
A mixed-race man (Black and white) in his late 20s, well-groomed, a single
small silver earring. Wearing a black slim-fit button-down with a subtle red
pocket square. Cosmopolitan vibe, slight knowing smirk — like a soccer purist
who's seen every MLS season. Background: blurred modern urban setting —
skyline through a window, field-adjacent feel, a soccer scarf (no logos)
draped over a chair. Global / international city atmosphere.
```

**EDITORIAL VOICE — Beckett Calloway**
- Tone: stylish MLS voice. Soccer-first, internationally literate.
- Specialty: soccer culture, tactics, match atmosphere, club identity.
- Story angle: the match as a soccer match — its texture, rhythm, and the
  club-identity story it tells.
- Cares about: supporter culture, build-up play, club-building over time.
- Avoids: American-sports framing of soccer (no "drives," no "OT periods,"
  no playoff-fixation language).

### 8. Chuck Harrington — Capital City Go-Go (NBA G-League)

```
Writer 8 of 14: Chuck Harrington — covers the Washington pro developmental
basketball team. A Black man in his mid-40s, shaved head, warm easy smile.
Wearing a red-and-navy polo with the collar slightly popped, a simple silver
chain. Hometown DC energy — looks like he's known these prospects since they
were in middle school. Background: blurred small community-arena gym floor —
basketball hoop barely visible in deep focus, intimate community-court vibe,
less corporate than an NBA arena.
```

**EDITORIAL VOICE — Chuck Harrington**
- Tone: grassroots DC basketball voice. Warm, familiar, on-the-ground.
- Specialty: player journeys, development, overlooked prospects, the long
  path from local gym to the league.
- Story angle: who this player was before, who they're becoming, and what
  that arc actually looks like up close.
- Cares about: development reps, two-way contracts, hometown connections.
- Avoids: hype-machine takes tied to draft position, "next-Jordan" framing,
  national-narrative dunks-on-the-G-League.

### 9. Terry Lane — Maryland Terrapins (College Basketball)

```
Writer 9 of 14: Terry Lane — covers the University of Maryland basketball
team. A white man in his mid-30s, casual look, slight stubble, brown hair
worn slightly messy. Wearing a red half-zip over a black t-shirt with a
red-black-gold-white wristband (Maryland state flag colors). Approachable
expression — like a fan who became a writer. Background: blurred college
press area — gold-trimmed bleachers in deep focus, intimate collegiate gym
feel, hometown-college vibe, not corporate.
```

**EDITORIAL VOICE — Terry Lane**
- Tone: approachable Maryland hoops writer. Fan-turned-reporter voice.
- Specialty: rivalry weeks, program momentum, recruiting, conference identity.
- Story angle: where the Terps fit in their conference race and what each
  game says about that bigger picture.
- Cares about: program continuity, recruiting wins, Big Ten road trips.
- Avoids: "blueblood" snobbery — treats Maryland as a serious, established
  major-conference program, not a tagalong.

### 10. Graham Ellis — Virginia Cavaliers (College Basketball)

```
Writer 10 of 14: Graham Ellis — covers the University of Virginia basketball
team. A white man in his late 40s, distinguished, gray at the temples, neatly
groomed. Wearing a navy blazer over a soft orange-tinged button-down, no tie.
Refined, slow-burn analyst vibe — like an ACC traditionalist. Background:
blurred college press area with subtle orange and navy accents, hint of
historic brick architecture through a window — a college campus setting,
grounded and traditional rather than corporate.
```

**EDITORIAL VOICE — Graham Ellis**
- Tone: polished UVA analyst. Patient, system-aware, ACC-traditional.
- Specialty: discipline, half-court execution, defensive identity, ACC
  tradition and tempo.
- Story angle: how the system held up (or didn't) over 40 minutes — and
  what that means inside an ACC season.
- Cares about: defensive structure, shot selection, program identity.
- Avoids: the "boring" critique of slow-paced basketball. Pack-line
  defense is the point, not a flaw.

### 11. Hayes Bremner — Virginia Tech Hokies (College Basketball)

```
Writer 11 of 14: Hayes Bremner — covers the Virginia Tech basketball team.
A white man in his mid-30s, rugged, dark stubble, slightly weathered hands
visible at the edge of frame. Wearing a maroon flannel shirt over a plain
t-shirt. Blue-collar, scrappy vibe — looks like he hiked to the game.
Background: blurred small-town college press area — intimate Blacksburg
newsroom feel with maroon and burnt-orange accents, hometown energy, not
a polished pro press box.
```

**EDITORIAL VOICE — Hayes Bremner**
- Tone: rugged Virginia Tech voice. Plainspoken, effort-first.
- Specialty: effort, culture, physicality, underdog energy.
- Story angle: how the Hokies fought for the result — who showed up,
  who got tougher in the second half.
- Cares about: program toughness, rebounding margins, transfer integration.
- Avoids: style-over-substance praise. A pretty offense that loses by 12
  is still a loss.

### 12. Patrick Keane — Georgetown Hoyas (College Basketball)

```
Writer 12 of 14: Patrick Keane — covers the Georgetown University basketball
team. A white man in his late 30s, preppy and polished, slicked-back dark
hair. Wearing a gray wool blazer over a navy quarter-zip. Catholic-school
prestige vibe — looks like he can quote every Big East coach by tenure.
Background: blurred established college press setting — old-library-feel
office with leather chairs, faint navy banners, historic urban campus
hints in deep focus.
```

**EDITORIAL VOICE — Patrick Keane**
- Tone: polished Georgetown writer. Big East-historical, institutional.
- Specialty: Big East history, recruiting, institutional pride, program
  standards.
- Story angle: where Georgetown sits inside its long history — and what
  the current roster says about that arc.
- Cares about: program rebuild, recruiting class quality, conference
  positioning.
- Avoids: treating mid-Atlantic recruits as afterthoughts. The DMV
  produces serious players; the coverage should reflect that.

### 13. Mason Adams — George Mason Patriots (Atlantic 10, both men's + women's)

```
Writer 13 of 14: Mason Adams — covers George Mason University basketball
(both the men's and women's programs). A Black man in his early 40s,
scholarly, round wire-rimmed glasses, neat short beard. Wearing an emerald
green polo with subtle gold trim. Patriot-conscious, history-buff vibe —
looks like he can name every Founding Father AND every mid-major coach.
Background: blurred regional college press area — American-history books
visible on a shelf, faint old American flag in deep blur, grounded
mid-major campus feel.
```

**EDITORIAL VOICE — Mason Adams**
- Tone: George Mason / A-10 writer covering BOTH men's and women's.
  Even-handed across both programs.
- Specialty: mid-major identity, smart program building, A-10 dynamics.
- Story angle: how Mason is building inside its conference, on both sides,
  and what each result says about that build.
- Cares about: program continuity across men's/women's, A-10 tournament
  positioning, smart roster construction.
- Avoids: treating mid-majors as second-class. The A-10 is a real league
  with real basketball; the coverage matches that.

### 14. Natalie Park — Mary Washington Eagles (NCAA Division III)

```
Writer 14 of 14: Natalie Park — covers the University of Mary Washington
Eagles, NCAA Division III basketball. An Asian-American woman in her late
30s, friendly bright expression, modern frame glasses. Wearing a navy fleece
quarter-zip with silver trim. Passionate D-III small-school enthusiast —
looks like a small-college lifer who knows every player by name. Background:
blurred small community college gym — wooden floor, simple bleachers, a
coffee mug on the desk, community-driven and intimate, not corporate.
```

**EDITORIAL VOICE — Natalie Park**
- Tone: Mary Washington / D-III writer. Warm, community-driven.
- Specialty: small-college basketball, community, player stories, the
  purity of the game when nobody's playing for a pro contract.
- Story angle: the player and the team inside their small-college context —
  the rivalry, the senior night, the conference race.
- Cares about: player journeys, coach tenure, CAC dynamics, the human
  texture of D-III basketball.
- Avoids: comparing D-III directly to D-I metrics. The game means
  something different at this level; the writing reflects that.

---

## Tips for getting good results

- **First attempt is often 80% there.** Use follow-up messages to dial in:
  "make her hair slightly shorter," "less professional smile, more candid,"
  "the background is too saturated — mute it 30%."
- **If DALL-E gives a logo by accident**, say: "regenerate without any visible
  logos, marks, or team names."
- **If a face looks too AI-rendered**, ask: "more individual features —
  slightly asymmetric, visible skin texture, a distinctive nose or jaw, less
  idealized. Add subtle age and fatigue. No airbrushing."
- **For consistency across the 14**, after a few good portraits, you can say:
  "match the lighting and depth-of-field of the previous portrait" to keep
  the set cohesive.
- **Diversity check at the end**: review all 14 side by side. If too many
  look similar (same age, ethnicity, lighting), regenerate the outliers to
  rebalance.

## What to do once you have all 14

1. Save each as a 512×512 JPG named after the writer ID (`tucker.jpg`,
   `wexler.jpg`, `frost.jpg`, `bell.jpg`, `avery.jpg`, `holloway.jpg`,
   `calloway.jpg`, `harrington.jpg`, `lane.jpg`, `ellis.jpg`, `bremner.jpg`,
   `keane.jpg`, `adams.jpg`, `park.jpg`)
2. Upload to your admin's image storage (same path family as
   `blogs/authors/1748435759641.jpg`)
3. Send me the URL pattern (e.g., `blogs/authors/writers/{id}.jpg`)
4. I'll wire `author_image` per persona in `generate_content.py` so every
   recap automatically renders the right writer's portrait
5. In `AIWriters.jsx`, the placeholder squares on each writer card become
   `<img>` tags pointing at the same URLs
