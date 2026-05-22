# NSMT Content Pipeline

Automated sports article generator for thensmt.com.
Fetches DC/MD/VA game results → generates drafts via Claude → saves to Contentful for review.

---

## How It Works

1. GitHub Actions runs every morning at 8am ET
2. Script fetches yesterday's scores from ESPN for all tracked teams
3. Claude writes a game recap for each team that played
4. Drafts appear in Contentful — **not published yet**
5. You review in Contentful and click Publish when ready
6. React site (thensmt.com) displays the article automatically

---

## Your Daily Workflow

1. Open https://app.contentful.com
2. Go to **Content** → filter by Status: Draft
3. Click an article, read it, make any edits
4. Click **Publish** — it goes live on the site
5. Or click **Archive** to discard it

---

## Story Packet Ingestion (MVP)

The ingestion layer builds a validated, public-source JSON story packet that can
later be added to the Claude prompt. It is additive: it does not publish,
does not call Claude, and is not wired into `generate_content.py` yet.

Run it for the Mystics:
```bash
python -m ingestion.generate_story_packet --team mystics
python -m ingestion.generate_story_packet --team mystics --dry-run
python -m ingestion.generate_story_packet --team mystics --date 2026-05-21
```

Default output is `data/packets/mystics_<YYYY-MM-DD>.json`. `--dry-run`
prints validated JSON and does not write a file. Source responses are cached
under `cache/` with short per-source TTLs.

To extend this to another team, add the team metadata and KB slug mapping in
the ingestion builder, add source-specific fetcher support for that team's
public endpoints, and add tests that prove both game-day and off-day packets
validate and are consumable by `consume_story_packet()`.

Status: Mystics only. Consumer hookup is deferred; a later change should load
`data/packets/{slug}_{date}.json`, call `consume_story_packet(packet)`, and add
that block to the article prompt beside the existing KB context.

---

## Setup (One-Time)

### 1. Add GitHub Secrets
In your GitHub repo → Settings → Secrets and Variables → Actions → New repository secret:

| Name | Value |
|------|-------|
| `ANTHROPIC_API_KEY` | Your Claude API key |
| `CONTENTFUL_CMA_TOKEN` | Your Contentful management token |
| `CONTENTFUL_SPACE_ID` | `d6khuyxovvy4` |

### 2. Run the Contentful Setup Script (once)
```bash
export CONTENTFUL_CMA_TOKEN=your_token
export CONTENTFUL_SPACE_ID=d6khuyxovvy4
python setup_contentful.py
```

### 3. Test Manually
```bash
export ANTHROPIC_API_KEY=your_key
export CONTENTFUL_CMA_TOKEN=your_token
python generate_content.py
```

To generate articles for a specific date:
```bash
python generate_content.py 2026-03-13
```

---

## Teams Covered

**Pro:** Commanders (NFL), Wizards (NBA), Capitals (NHL), Nationals (MLB),
Mystics (WNBA), Washington Spirit (NWSL), DC United (MLS), Capital City Go-Go (G-League)

**College:** Maryland Terrapins, Virginia Cavaliers, Virginia Tech Hokies, Georgetown Hoyas

---

## For Quincy (Developer)

See the separate note — Quincy needs to connect the React frontend to Contentful
so articles display on thensmt.com. See `FOR_QUINCY.md`.
