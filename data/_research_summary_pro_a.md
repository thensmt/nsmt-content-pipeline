# DC Pro Teams Research Summary — Batch A
**Date:** 2026-05-21
**Files produced:** 4/4

## Teams Completed
| Team | File | Status |
|------|------|--------|
| Washington Commanders (NFL) | `teams/commanders.json` | Complete |
| Washington Wizards (NBA) | `teams/wizards.json` | Complete with caveats |
| Washington Capitals (NHL) | `teams/capitals.json` | Complete |
| Washington Nationals (MLB) | `teams/nationals.json` | Complete |

## Authoritative Sources Used (in priority order)
1. **ESPN team pages** (`espn.com/{league}/team/...`) — primary source for records, rosters, schedules
2. **League official sites** (`nhl.com/capitals`, `mlb.com/nationals`) — used for executive announcements, coaching staffs
3. **Team-specific beat coverage** — Russian Machine Never Breaks (Caps), District on Deck / Federal Baseball / TalkNats (Nats), Bullets Forever (Wizards), Commanders.com
4. **Wikipedia** — only as cross-reference for ownership and founding dates
5. **Sports Illustrated team verticals** — used for coaching-staff confirmations on Nats

## Major Storyline Verified
**Nationals had a full front-office and dugout cleanout in 2025:**
- President of Baseball Ops Mike Rizzo: fired July 2025
- Manager Dave Martinez: fired July 2025
- Interim manager Miguel Cairo: 29-43, not retained
- **NEW leadership (in place for 2026 season):** Pres. of Baseball Ops Paul Toboni (from Boston), GM Ani Kilambi (from Philadelphia), Manager Blake Butera (age 33, from Rays minor-league system)
- David should DOUBLE-CHECK these spellings/titles before any recap publishes. The Butera/Toboni/Kilambi trio is the single biggest "if we get this wrong, it's embarrassing" item in this batch.

**Commanders coaching turnover (Jan 2026):**
- Dan Quinn (HC) and Adam Peters (GM) RETAINED by owner Josh Harris despite 5-12 season
- OC Kliff Kingsbury and DC Joe Whitt Jr. were FIRED
- New OC: David Blough (promoted from assistant QBs coach)
- New DC: Daronte Jones (external hire)
- STC Larry Izzo carries over from 2025 staff per available sources; verify before training camp.

## Gaps and Soft Data (per team)

### Commanders
- Stadium capacity for Northwest Stadium: NOT confirmed — left null
- Stadium opening year: NOT confirmed — left null
- Several duplicate jersey numbers on ESPN roster page (likely mid-season churn / camp body overlap): #11 (Van Jefferson + Luke McCaffrey), #61, #79, #90 — flagged in verification_notes
- Career record of Dan Quinn WITH Washington specifically: not pulled (left null) — easily derivable: Year 1 was 12-5, Year 2 was 5-12, so 17-17 through two regular seasons + 2024 playoff run

### Wizards
- Coaching staff beyond head coach Brian Keefe: NOT verified — left as null placeholder. NBA assistant coach lineups are not well-published on ESPN.
- Two duplicate jersey numbers on ESPN roster (#5 D'Angelo Russell + Jamir Watkins; #12 Tre Johnson + Leaky Black) — likely two-way / G League contract overlaps. RE-VERIFY before recap.
- One search result said "16-55 / 17-64"; ESPN consistently says 17-65. Used 17-65.
- Note: Wizards WON the 2026 NBA Draft Lottery per ownership social media — worth tracking for offseason coverage.

### Capitals
- Stanley Cup elimination date: April 13, 2026 (per Flyers shootout win vs. Hurricanes)
- Ovechkin's final regular-season game noted as "could be his final NHL game" in coverage — no retirement confirmation, but flag for editorial sensitivity
- Coaching staff assistant Corey Schueneman shares #64 with David Kampf on ESPN page — Schueneman omitted from roster as the duplicate likely reflects a late callup

### Nationals
- Stadium capacity for Nationals Park: left null (true value is ~41,000 per general knowledge, but Wikipedia fetch did not return it, so omitted per never-fabricate rule). David can manually backfill if desired.
- Roster is current as of 2026-05-21 mid-season — will need monthly refresh during the active season
- 2026 record of 25-25 (2nd in NL East) is genuinely competitive for a team in its second rebuild year — could be a feature angle for NSMT

## Inconsistencies Encountered
1. Wizards record: one search-result snippet conflated end-of-season records (16-55 vs 17-65). ESPN's 17-65 used.
2. Nationals leadership: most search results before October 2025 still reference Rizzo/Martinez. Only post-Oct 2025 sources reflect the actual current chain of command. Be wary of stale cached pages.
3. Wikipedia did NOT consistently return capacity figures for any venue in this batch — opted not to fabricate.
4. Several roster jersey-number collisions on ESPN are an artifact of ESPN merging in-season transactions; this is a known data-quality issue, not a sign of wrong data per se.

## Recommendations for David
1. **Before any Nationals recap publishes**, manually verify spellings: **Blake Butera**, **Paul Toboni**, **Ani Kilambi** (full name **Anirudh Kilambi**), **Matt Borgschulte**, **Simon Mathews**, **Victor Estevez**.
2. **Before any Commanders recap**, confirm the 2026 coordinator names (David Blough OC, Daronte Jones DC) — they were just hired in January 2026 and may not be in stale pre-built templates.
3. **Capitals**: any Ovechkin recap should be careful with retirement language — he had a strong final regular-season game (PPA on game-winner) but his future is unconfirmed in public reporting.
4. **Wizards coaching staff** is a gap — recommend a one-time manual sweep of `nba.com/wizards/team/staff` or similar to populate assistant coaches.
5. **Stadium capacities** for all four venues are currently null. If recaps need them, pull from official team sites in a focused follow-up.
6. **Refresh cadence:** Nationals roster will need refreshing weekly during the season. The other three are in offseason and stable until training camps open (NFL/NHL/NBA late summer-fall 2026).
