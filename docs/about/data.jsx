// NSMT — data tables for the AI Writers page

const WRITERS = [
  // PRO
  { id: "tucker",     name: "Maxwell Tucker",   first: "Maxwell",   last: "Tucker",     team: "Washington Commanders", league: "NFL",     sport: "Football",   color: "#5A1414", color2: "#FFB612", initials: "MT", tier: "PRO",
    voice: "Blunt, X's-and-O's. Reads like a longtime NFL beat writer who's been to every camp.",
    pull: "X's-and-O's. He's been to every camp.",
    headline: "Tucker: Daniels' 4th-Quarter Heroics Lift Commanders Past Dallas, 27-24",
    status: "drafting" },
  { id: "wexler",     name: "Casper Wexler",    first: "Casper",    last: "Wexler",     team: "Washington Wizards",    league: "NBA",     sport: "Basketball", color: "#002B5C", color2: "#E31837", initials: "CW", tier: "PRO",
    voice: "Modern, analytics-first. Pace, space, and a sixth-man's-eye view of efficiency.",
    pull: "Pace, space, and a sixth-man's eye for efficiency.",
    headline: "Wexler: Wizards Find Their Pace in 118-110 Win Over Atlanta",
    status: "reviewing" },
  { id: "frost",      name: "Ada Frost",        first: "Ada",       last: "Frost",      team: "Washington Capitals",   league: "NHL",     sport: "Hockey",     color: "#A6192E", color2: "#041E42", initials: "AF", tier: "PRO",
    voice: "Tactical. Rink-side. Uses zone exits and forechecks the way locals use directions.",
    pull: "Zone exits and forechecks like locals use directions.",
    headline: "Frost: Ovechkin's Power-Play Snipe Decides Overtime in Pittsburgh",
    status: "published" },
  { id: "bell",       name: "Marcus Bell",      first: "Marcus",    last: "Bell",       team: "Washington Nationals",  league: "MLB",     sport: "Baseball",   color: "#AB0003", color2: "#14225A", initials: "MB", tier: "PRO",
    voice: "Stats-curious. Anchors a performance in the long, strange history of the game.",
    pull: "Anchored in the long, strange history of the game.",
    headline: "Bell: Nats' Bullpen Holds, City Connect Jerseys Win Again",
    status: "scheduled" },
  { id: "avery",      name: "Sibyl Avery",      first: "Sibyl",     last: "Avery",      team: "Washington Mystics",    league: "WNBA",    sport: "Basketball", color: "#C8102E", color2: "#0C2340", initials: "SA", tier: "PRO",
    voice: "Insightful. Draws lines between possessions and player tendencies.",
    pull: "Draws lines between possessions and tendencies.",
    headline: "Avery: Mystics Read the Switch — Dream Drop Series Opener, 84-72",
    status: "idle" },
  { id: "holloway",   name: "Wren Holloway",    first: "Wren",      last: "Holloway",   team: "Washington Spirit",     league: "NWSL",    sport: "Soccer",     color: "#840028", color2: "#1B1B1B", initials: "WH", tier: "PRO",
    voice: "Tactical and internationalist. Reads pressing triggers like a coach with a clipboard.",
    pull: "Reads pressing triggers like a coach with a clipboard.",
    headline: "Holloway: Spirit's Press Triggers Three Goals in 17 Minutes",
    status: "drafting" },
  { id: "calloway",   name: "Beckett Calloway", first: "Beckett",   last: "Calloway",   team: "DC United",             league: "MLS",     sport: "Soccer",     color: "#000000", color2: "#EBCB54", initials: "BC", tier: "PRO",
    voice: "Cosmopolitan MLS savant. Soccer-purist sensibility with an American eye.",
    pull: "A purist's eye for the American game.",
    headline: "Calloway: DC United Stretch a Tired Inter Miami, Steal a Point at Audi",
    status: "idle" },
  { id: "harrington", name: "Chuck Harrington", first: "Chuck",     last: "Harrington", team: "Capital City Go-Go",    league: "G-League", sport: "Basketball", color: "#0C2340", color2: "#C8102E", initials: "CH", tier: "PRO",
    voice: "Hometown DC voice. Prospect-focused, hopeful, all heart and player development.",
    pull: "Hometown, hopeful, all heart and development.",
    headline: "Harrington: Two-Way Watch — Go-Go Rookie Lights Up Long Island",
    status: "idle" },
  // COLLEGE
  { id: "lane",       name: "Terry Lane",       first: "Terry",     last: "Lane",       team: "Maryland Terrapins",     league: "Big Ten",   sport: "Basketball", color: "#E03A3E", color2: "#FFD520", initials: "TL", tier: "COLLEGE",
    voice: "Hometown Maryland pride. Knows every gym and every Big Ten road trip.",
    pull: "Knows every gym and every Big Ten road trip.",
    headline: "Lane: Terps' Backcourt Out-Runs Rutgers in Big Ten Opener",
    status: "drafting" },
  { id: "ellis",      name: "Graham Ellis",     first: "Graham",    last: "Ellis",      team: "Virginia Cavaliers",     league: "ACC",       sport: "Basketball", color: "#232D4B", color2: "#F84C1E", initials: "GE", tier: "COLLEGE",
    voice: "Refined, slow-burn analysis. ACC tradition in every paragraph.",
    pull: "Slow-burn analysis. ACC tradition in every paragraph.",
    headline: "Ellis: Cavaliers' Pack-Line Strangles Duke, 61-54 at JPJ",
    status: "idle" },
  { id: "bremner",    name: "Hayes Bremner",    first: "Hayes",     last: "Bremner",    team: "Virginia Tech Hokies",   league: "ACC",       sport: "Basketball", color: "#630031", color2: "#CF4420", initials: "HB", tier: "COLLEGE",
    voice: "Blue-collar, scrappy. Lane Stadium pride leaking into a basketball voice.",
    pull: "Lane Stadium pride, scrappy on every possession.",
    headline: "Bremner: Hokies' Bench Wins It in Greensboro Slugfest, 71-68",
    status: "reviewing" },
  { id: "keane",      name: "Patrick Keane",    first: "Patrick",   last: "Keane",      team: "Georgetown Hoyas",       league: "Big East",  sport: "Basketball", color: "#041E42", color2: "#8D817B", initials: "PK", tier: "COLLEGE",
    voice: "Prestige tone. Big East tradition. Hoya Saxa, always.",
    pull: "Prestige tone. Big East tradition. Hoya Saxa.",
    headline: "Keane: Hoyas Hand Villanova First Big East Loss of the Year",
    status: "published" },
  { id: "adams",      name: "Mason Adams",      first: "Mason",     last: "Adams",      team: "George Mason Patriots",  league: "A-10",      sport: "Basketball (M/W)", color: "#006633", color2: "#FFCC33", initials: "MA", tier: "COLLEGE",
    voice: "Scrappy mid-major. History-conscious patriot energy on both sides of the ledger.",
    pull: "Scrappy mid-major, history-conscious patriot energy.",
    headline: "Adams: Patriots Sweep VCU in A-10 Doubleheader Day",
    status: "idle" },
  { id: "park",       name: "Natalie Park",     first: "Natalie",   last: "Park",       team: "Mary Washington Eagles", league: "NCAA D-III", sport: "Basketball", color: "#003366", color2: "#A0A0A0", initials: "NP", tier: "COLLEGE",
    voice: "Passionate small-school enthusiast. The soul of the sport lives in D-III gyms.",
    pull: "The soul of the sport lives in D-III gyms.",
    headline: "Park: Eagles Stretch CAC Win Streak to Eleven, Top Salisbury",
    status: "idle" },
];

const STACK = [
  { k: "LLM",       v: "Anthropic Claude API",                       tip: "Claude is Anthropic's large language model. We use it to draft every recap from a structured box-score JSON." },
  { k: "DATA",      v: "ESPN public sports API",                     tip: "ESPN exposes box-score JSON for most leagues. We poll it the morning after each game." },
  { k: "ORCHESTRA", v: "Python orchestration script",                tip: "A small Python script chains the steps: fetch → compose prompt → call Claude → POST to admin." },
  { k: "CRON",      v: "GitHub Actions — 08:00 ET daily",            tip: "GitHub Actions runs a scheduled workflow as the daily timer. Free for public repos." },
  { k: "ROUTING",   v: "Cloudflare Workers (multi-target webhook proxy)", tip: "Cloudflare Workers are tiny JS functions running on the edge — our cheap, fast webhook router." },
  { k: "BACKEND",   v: "AWS API Gateway + Cognito",                  tip: "API Gateway fronts the admin backend. Cognito handles auth so only David can flip a draft live." },
  { k: "REVIEW",    v: "Discord forum channels",                     tip: "Each new draft posts as a Discord forum thread. The whole editorial flow happens in one place." },
  { k: "FRONT",     v: "thensmt.com — React",                        tip: "Public site is a React SPA. Same data feed that admin writes to is what the public reads." },
];

const PIPELINE = [
  { n: "01", t: "FETCH",   d: "Pull box scores from ESPN for every team that played last night.",
    long: "A scheduled Python job hits ESPN's public sports API at 08:00 ET. For each of NSMT's 14 beats, it checks last night's slate and grabs the structured box-score JSON. No game, no recap." },
  { n: "02", t: "PROMPT",  d: "Compose a custom prompt with the team-specific persona voice modifier.",
    long: "Every writer has a frozen persona prompt — name, beat, prose tics, length budget. We splice it together with the game data into one cohesive instruction." },
  { n: "03", t: "WRITE",   d: "Claude drafts a 400-550 word professional recap in that writer's voice.",
    long: "Claude returns headline + body + suggested pull quote. Average draft time: ~7 seconds. Average cost per article: roughly two cents." },
  { n: "04", t: "STAGE",   d: "Post to admin.thensmt.com as a draft with is_active = 0.",
    long: "The draft lands in the admin CMS, unpublished. Every record stores the writer, the prompt, the timestamp, and the model version — full audit trail." },
  { n: "05", t: "NOTIFY",  d: "Ping a Discord forum thread with title, byline, and excerpt.",
    long: "A Cloudflare Worker fans the staged draft out to Discord as a forum post. One thread per article. Editorial review happens in-thread." },
  { n: "06", t: "PUBLISH", d: "David reviews, flips is_active = 1, the article goes live on thensmt.com.",
    long: "A human reads every word before it ships. The byline shows the AI writer's name and a small robot mark — the reader always knows what they're reading." },
];

const OTHER = [
  "Automated applicant intake — form → AI-formatted Discord post for human review.",
  "Public critique submissions — creators submit work, auto-flows to Discord.",
  "Shared Cloudflare Worker infrastructure across all NSMT pipelines.",
  "Total monthly infrastructure cost: $0. Everything on free tiers.",
];

const TECH_TIPS = {
  "Cloudflare Workers": "Tiny JavaScript functions that run on Cloudflare's edge network. We use them as a cheap, fast webhook router.",
  "Claude": "Anthropic's large language model. It drafts every recap from a structured box score in roughly seven seconds.",
  "GitHub Actions": "GitHub's built-in scheduler. We use it as a free cron daemon to kick off the 08:00 ET pipeline run.",
  "ESPN API": "Publicly accessible JSON endpoints exposing box scores and schedules for most major leagues.",
  "Cognito": "AWS's hosted user-auth service. It's what gates the admin where drafts get flipped live.",
  "is_active": "A boolean flag on every article record. 0 = draft, never visible to the public. 1 = live on thensmt.com.",
  "box score": "Structured per-game JSON: final score, period scores, leading scorers, key plays. The raw material every recap is built from.",
  "Discord forum": "A forum-style channel in Discord where each thread is one article in review. Comments stay attached to the draft.",
};

const TODAY_LINEUP = [
  { writer: "tucker",   game: "Commanders 27, Cowboys 24",    finalScore: "27-24",  status: "drafting",  time: "08:03" },
  { writer: "wexler",   game: "Wizards 118, Hawks 110",       finalScore: "118-110", status: "reviewing", time: "08:07" },
  { writer: "frost",    game: "Capitals 4, Penguins 3 (OT)",  finalScore: "4-3 OT", status: "published", time: "08:11" },
  { writer: "lane",     game: "Maryland 78, Rutgers 71",      finalScore: "78-71",  status: "drafting",  time: "08:14" },
  { writer: "bremner",  game: "Virginia Tech 71, UNC 68",     finalScore: "71-68",  status: "reviewing", time: "08:16" },
];

const COMPARE = {
  traditional: {
    label: "TRADITIONAL NEWSROOM",
    rows: [
      ["TIME TO PUBLISH",   "~4 HOURS / ARTICLE"],
      ["TEAMS COVERED",     "1-3"],
      ["COST PER ARTICLE",  "$75 - $250"],
      ["FATIGUE",           "REAL"],
      ["LATE-NIGHT GAMES",  "OFTEN DROPPED"],
      ["TRANSPARENCY",      "BYLINE OPACITY"],
    ],
  },
  nsmt: {
    label: "NSMT AI NEWSROOM",
    rows: [
      ["TIME TO PUBLISH",   "~7 SECONDS / DRAFT"],
      ["TEAMS COVERED",     "14"],
      ["COST PER ARTICLE",  "≈ $0.02"],
      ["FATIGUE",           "NONE"],
      ["LATE-NIGHT GAMES",  "ALWAYS COVERED"],
      ["TRANSPARENCY",      "ROBOT IN EVERY BYLINE"],
    ],
  },
};

const STATUS_META = {
  drafting:  { label: "DRAFTING",  color: "#0E80FC" },
  reviewing: { label: "REVIEWING", color: "#E94F1D" },
  published: { label: "PUBLISHED", color: "#1F9D55" },
  scheduled: { label: "SCHEDULED", color: "#6B5DC7" },
  idle:      { label: "IDLE",      color: "#777" },
};

Object.assign(window, { WRITERS, STACK, PIPELINE, OTHER, TECH_TIPS, TODAY_LINEUP, COMPARE, STATUS_META });
