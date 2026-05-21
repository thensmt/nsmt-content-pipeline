# College Basketball Knowledge Base — Research Summary

**Date built:** 2026-05-21
**Researcher:** Claude (NSMT content pipeline)
**Programs built:** 7 (6 men's + 1 women's)
**Output directory:** `/Users/david/Downloads/Claude/NSMT/content-pipeline/data/teams/`

---

## Programs Successfully Built

| Slug | Program | Conference | 2025-26 Record | Postseason |
|---|---|---|---|---|
| `maryland` | Maryland Terrapins (M) | Big Ten | 12-21 (4-16) | None |
| `virginia` | Virginia Cavaliers (M) | ACC | 30-6 (15-3) | NCAA R32 (3 seed) |
| `virginia-tech` | Virginia Tech Hokies (M) | ACC | 19-13 (8-10) | Declined NIT |
| `georgetown` | Georgetown Hoyas (M) | Big East | 16-18 (6-14) | Big East SF |
| `george-mason` | George Mason Patriots (M) | Atlantic 10 | 23-10 (11-7) | NIT R1 |
| `george-mason-women` | George Mason Patriots (W) | Atlantic 10 | 23-10 (16-2) | WBIT R1 — won A-10 reg season |
| `mary-washington` | Mary Washington Eagles (M) | Coast-to-Coast (D3) | 30-3 | **D3 NATIONAL CHAMPIONS** |

---

## Major Storylines / Coaching Changes Since Season Ended

These will materially affect any recap, preview, or analysis content NSMT publishes between now and the 2026-27 season tip-off:

1. **Maryland — first-year Buzz Williams coaching disaster.** Buzz Williams was hired April 1, 2025 from Texas A&M after Kevin Willard left for Villanova following a Sweet 16. The first season was 12-21, fewest wins since 1992. Williams is rebuilding aggressively via transfer portal (DJ Wagner from Arkansas, Tomislav Buljan from New Mexico, Robert Jennings from Oklahoma State, Bishop Boswell from Tennessee, freshman Baba Oladotun). Only 4 returners from 2025-26 squad. He is NOT fired — still HC.

2. **Virginia — Ryan Odom's debut went the opposite way.** Hired March 22, 2025, Odom's first Virginia team went 30-6, finished 2nd in the ACC, made the NCAA Tournament as a 3 seed, beat Wright State, lost to 6-seed Tennessee in R32. The John Paul Jones Arena playing surface was named "Tony Bennett Court" on February 21, 2026. Owen Odom (Ryan's son) is on the roster.

3. **Virginia Tech AD transition.** Whit Babcock announced April 23, 2026 he will step down as AD effective June 30, 2026 after 12 years. Transitions to "AD Emeritus" advisory role July 1, 2026. No successor publicly named as of 2026-05-21. Mike Young remains HC.

4. **Mary Washington wins 2026 NCAA D3 National Championship.** Defeated Emory 75-73 on April 5, 2026 on a Colin Mitchell buzzer-beating putback. First national title in program history. Marcus Kahn (12th year) won 2026 Glenn Robinson National Coach of the Year. This is a flagship NSMT-region story.

5. **George Mason men.** Tony Skinn (alum, member of 2006 Final Four team) finished 23-10, started 18-1 — best start in program history. Lost to St. Bonaventure in A-10 R2, then to Liberty in NIT R1. Signed a contract extension per NBC Sports. Already added 3 confirmed 2026-27 transfers via gomason.com news releases.

6. **George Mason women won A-10 regular season title.** Vanessa Blair-Lewis (6th year) led the Patriots to their FIRST EVER A-10 regular season championship (16-2). Despite this, did not receive NCAA Tournament bid (notable snub). Lost in WBIT R1 to Quinnipiac 64-71.

7. **Georgetown.** Ed Cooley's third year ended 16-18 (6-14 Big East). Bright spot: as 11 seed in Big East Tournament, beat DePaul and Villanova before losing to UConn in semifinals.

---

## Hardest-to-Verify Data

### Mary Washington (D3) — Highest Verification Risk
- **Venue capacity & opening year** could not be confirmed from authoritative sources. The William M. Anderson Center is the listed home venue, but capacity is unverified. Set to null.
- **Conference record** is shown as 0-0 in d3hoops.com data — this is likely an artifact of how D3 conference games are categorized for a championship team that played a national-tournament-heavy schedule. Recommend verifying the actual C2C conference record before any "conference record" claim is published.
- **Roster anomalies:** Preston White's height not listed on the official UMW roster. Owen Pottenburgh's hometown (Jacksonville FL) does not match his listed high school (Hayfield, which is in Fairfax VA) — likely a data entry inconsistency on the UMW roster page.
- **Career records for Marcus Kahn** at UMW and across his career — not surfaced through any source we accessed. Left null.

### Coaching Career Records (All Programs)
- Career win/loss totals for head coaches (Buzz Williams, Ryan Odom, Mike Young, Ed Cooley, Tony Skinn, Vanessa Blair-Lewis, Marcus Kahn) — none verified to a specific number. All set to null. Sports-Reference.com/cbb has these for D1 coaches; manual scrape recommended.

### George Mason Women's Roster
- Wikipedia lists "Louis Volker" as a forward on the women's roster. Name appears atypical for a women's team — verify against the official gomason.com page before publication.

### Capital One Arena Capacity (Georgetown)
- Stated 20,356 is the standard NBA/concert config; Georgetown's typical game-day basketball setup is sometimes a reduced configuration. The 20,356 figure is published as the standard but may not reflect Georgetown's announced attendance capacity.

### Maryland Coaching Staff
- Wikipedia listed 5 assistant coaches (Devin Johnson, Lyle Wolf, Steve Roccaforte, Wabissa Bede, Aki Collins) without specifying roles (associate HC vs assistant). The official umterps.com 2026-27 coaches page may reflect changes; verify before publishing.

---

## Sources Used (Top-Level)

- **Wikipedia season pages** (2025-26 team pages) — primary structured source for rosters, records, postseason results
- **Official athletics sites** — umterps.com, virginiasports.com, hokiesports.com, guhoyas.com, gomason.com, umweagles.com — used for verification and AD/coach bios
- **d3hoops.com** — Mary Washington tournament results
- **WSLS / regional media** — Whit Babcock retirement announcement
- **NBC Sports / SI / On3 / DBK News** — coaching changes, transfer portal news, contract extensions
- **Sports-Reference.com/cbb** — referenced but not deeply scraped (recommend follow-up for career coaching records)

---

## Recommendations Before Publishing Any Article

1. **Pull current 2026-27 rosters in August 2026.** All current rosters are season-end 2025-26. By summer's end, the rosters will be substantially different — especially Maryland (only 4 returners), and any team with graduate transfers.
2. **Verify Maryland assistant coach roles** against umterps.com/sports/mens-basketball/coaches before any "associate head coach" attribution.
3. **Verify Virginia Tech AD** if any article runs after June 30, 2026 — Babcock's successor will be the active AD.
4. **For Mary Washington stories** (national title is a major NSMT-region story): manually verify roster details against the umweagles.com page and call Patrick Catullo's office if any claim is load-bearing. D3 coverage online is sparse and error-prone.
5. **Don't publish coaching career records** from this dataset — all are null. Pull from Sports-Reference.com/cbb manually.
6. **Capital One Arena capacity** — for any Georgetown attendance/sellout content, use Georgetown-specific announced capacity, not the 20,356 NBA-config number.
7. **Cross-check all player name spellings** — international players (Avdalas, Halaifonua, Iwuchukwu, Grünloh, Sivka, Adebayo) have non-standard spellings that auto-correct will mangle. Lock these into NSMT's CMS dictionary.
8. **Confirm George Mason women's "Louis Volker"** name against official roster before any reference.

---

## Files Created

```
/Users/david/Downloads/Claude/NSMT/content-pipeline/data/teams/maryland.json
/Users/david/Downloads/Claude/NSMT/content-pipeline/data/teams/virginia.json
/Users/david/Downloads/Claude/NSMT/content-pipeline/data/teams/virginia-tech.json
/Users/david/Downloads/Claude/NSMT/content-pipeline/data/teams/georgetown.json
/Users/david/Downloads/Claude/NSMT/content-pipeline/data/teams/george-mason.json
/Users/david/Downloads/Claude/NSMT/content-pipeline/data/teams/george-mason-women.json
/Users/david/Downloads/Claude/NSMT/content-pipeline/data/teams/mary-washington.json
```
