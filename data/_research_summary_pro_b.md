# NSMT Pro Teams Knowledge Base — Research Summary (Batch B)

Built 2026-05-21 by Claude (Opus 4.7).

## Teams successfully built

| Team | File | Confidence |
|------|------|------------|
| Washington Mystics | `teams/mystics.json` | High (roster + coach verified across 2 sources) |
| Washington Spirit | `teams/spirit.json` | High (full 27-player roster + coach verified) |
| D.C. United | `teams/dc-united.json` | Medium-High (roster solid; assistants unknown; recent-game dates inferred) |
| Capital City Go-Go | `teams/go-go.json` | Medium (coaching staff strong; roster jersey numbers partial for reserves) |

## Hardest-to-verify data per team

**Mystics**
- Conflicting assistant-coach lists: an early search result named Shelley Patterson / Ashley McGee; Wikipedia (more recent) named Jessie Miller / Emre Vatansever / Barbara Turner. Wikipedia used as authoritative — flag for manual confirmation.
- CareFirst Arena capacity and exact rebrand date not located.

**Spirit**
- Two slightly different records cited: ESPN/search said 5-2-3 (18 pts) NWSL-only; team site `/schedule/` said 6-2-3 with the extra "W" being a Concacaf W Champions Cup semifinal. NWSL standings only count NWSL play. Both are documented in the JSON `verification_notes`.
- GM "Nathan Minion" sourced only from Wikipedia — verify.
- Multiple international players with diacritics (Élisabeth Tsé, Lucia Di Guglielmo, Rosemonde Kouassi, Claudia Martínez, Leicy Santos, Adrián González) — preserved exactly as ESPN/Wikipedia rendered them.

**DC United**
- Coaching staff (assistants) NOT available on official roster page or Wikipedia; left empty array.
- Recent-game dates not captured by Wikipedia narrative — only opponents and scores. Marked `date: null` and noted in `verification_notes`. Upcoming games unavailable (ESPN MLS schedule URL returned 404).
- Wikipedia article on D.C. United contained an apparently stale paragraph saying the club was 15th/30th and missed the 2025 playoffs — that appears to describe an older season. Used the dedicated `2026 D.C. United season` Wikipedia article for current standings (4-5-5, 17 pts, 5th East as of May 17).
- One player (Andre Dozzell) listed on roster without a jersey number on the official page.

**Go-Go**
- Several reserve players (Christopher Mantis, Akoldah Gak, Damari Monsanto, Trae Hannibal, Alondes Williams) have no jersey numbers in available sources.
- Playoff opponent / bracket details for the Conference Quarterfinal loss not captured — would be needed for any retrospective recap.
- Player Tristan Vukčević's name is rendered both with and without diacritics across sources; kept the diacritic version (Serbian standard).
- No designated rivalry documented in the franchise's brief 7-year history.

## Authoritative sources used

- ESPN team pages (rosters, schedules, fixtures) — most reliable for current squads
- Wikipedia team articles (ownership, founding, arena, current-season summary)
- Wikipedia season-specific articles (`2026 D.C. United season`) for in-season records
- Official team sites: `dcunited.com/roster` worked; `mystics.wnba.com/roster` and `capitalcity.gleague.nba.com/roster` timed out; `washingtonspirit.com/schedule/` worked
- MLSSoccer.com and washingtonpost.com (for René Weiler hire confirmation)
- OurSportsCentral mirror (for Go-Go coaching staff press release after the original capitalcity.gleague.nba.com URL timed out)
- usbasket.com for Go-Go roster details

## Inconsistencies encountered

1. **Spirit record discrepancy (5-2-3 vs 6-2-3):** Concacaf W Champions Cup semifinal win on 5/20 inflates the all-comps record vs NWSL-only standings. Both documented; NWSL-only is the correct figure for league standing references.
2. **Mystics assistant coaches:** Two different lists across sources (see above).
3. **DC United standings:** Stale-looking paragraph in main Wikipedia article contradicted the season-specific article. Used the season article.
4. **DC United head coach in early search snippet:** One ESPN search snippet implied Troy Lesesne might still be coach — confirmed via multiple subsequent sources that Weiler replaced Lesesne in July 2025.
5. **Go-Go career record:** "80-58" cited in search was Toppert's three-season total, not just 2025-26 alone. Stored in `career_record_with_team` accordingly.

## Recommendations for manual verification

1. **Spirit:** Confirm GM Nathan Minion via the official club staff page (not fetched).
2. **Mystics:** Confirm exact assistant coach roster via `mystics.wnba.com` staff page once it loads.
3. **DC United:** Manually pull assistant coaches from the official site; pull recent-game dates from `mlssoccer.com/clubs/dc-united/schedule/` (was 404 today, may be regional/temporary).
4. **DC United:** Refresh current record before publishing any recap — by 2026-05-21 they likely have more games than the 5/17 snapshot captures.
5. **Go-Go:** Verify end-of-season roster jersey numbers for reserve players and capture the Conference Quarterfinal opponent + score for any postseason retrospectives.
6. **Mystics:** Refresh record after any game played on 5/19 or 5/20 (not seen in ESPN snapshot).
7. **All teams:** Re-verify head-coach names quarterly — coaching changes mid-season aren't rare (Lesesne fired mid-2025 is a recent example).

## Process notes

- Several official team sites timed out under WebFetch (60s ceiling). Mirrors and ESPN often filled the gap.
- ESPN MLS team page IDs: DC United = 586 on schedule URL but the path with `/dc-united` slug returned 404; root-id path worked for some endpoints.
- All player names with diacritics were preserved character-for-character from the source that rendered them; if a downstream renderer is ASCII-only it must be aware these characters exist.
