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

BACKGROUND
- Slightly out-of-focus modern newsroom or sports-press setting. Computers,
  papers, sports gear visible but heavily blurred.
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

### 1. Maxwell Tucker — Washington Commanders (NFL)

```
Writer 1 of 14: Maxwell Tucker — covers the Washington pro football team.
A white man in his late 50s, weathered face with gentle smile lines, gray-flecked dark beard,
reading glasses pushed up onto his forehead. Wearing a burgundy quarter-zip
pullover over a tan henley. Comfortable, slightly amused expression — looks
like he's covered 200 NFL games and is mid-thought about a 3rd-down call.
Background: blurred newsroom with hints of burgundy banner and an old leather
football on a desk in the deep background.
```

### 2. Casper Wexler — Washington Wizards (NBA)

```
Writer 2 of 14: Casper Wexler — covers the Washington pro basketball team.
An Asian-American man in his early 30s, clean-cut with short black hair,
dark thin-rimmed glasses. Wearing a navy blue button-down with sleeves rolled
to the forearm, modern slim fit. Sharp, analytical expression — like he's
mid-thought about pace and spacing. Background: blurred desk with an open
laptop showing spreadsheets, a basketball in deep blur, faint red and navy
color accents.
```

### 3. Ada Frost — Washington Capitals (NHL)

```
Writer 3 of 14: Ada Frost — covers the Washington pro hockey team.
A white woman in her mid-30s, athletic build, blonde hair pulled back in a
loose low ponytail. Wearing a red knit pullover over a white collared shirt.
Direct, no-nonsense expression with a slight smile — like she's about to ask a
coach a tough postgame question. Background: a hockey-rink edge deep in blur,
faint red boards barely visible, hint of arena lighting.
```

### 4. Bayes Cooper — Washington Nationals (MLB)

```
Writer 4 of 14: Bayes Cooper — covers the Washington pro baseball team.
A Black man in his late 50s, salt-and-pepper hair, kind eyes behind aviator-
style glasses. Wearing a cream button-down with the sleeves rolled to the
elbows, navy braces (suspenders) visible. Scholarly and warm — looks like a
baseball historian who knows every ERA from 1972 onward. Background: blurred
bookshelf with old folders, a baseball sitting on the desk.
```

### 5. Sibyl Avery — Washington Mystics (WNBA)

```
Writer 5 of 14: Sibyl Avery — covers the Washington pro women's basketball team.
A Black woman in her early 30s, natural hair styled with care, small gold
hoop earrings. Wearing a burgundy blazer over a white shell top. Insightful,
knowing expression — looks like she sees every screen-and-roll coming three
seconds before it happens. Background: blurred basketball court markings,
red and bronze color accents.
```

### 6. Wren Holloway — Washington Spirit (NWSL)

```
Writer 6 of 14: Wren Holloway — covers the Washington pro women's soccer team.
A Latina woman in her early 30s, athletic build, short dark hair styled
modern. Wearing a fitted navy quarter-zip with subtle red trim, a press
lanyard around her neck. Confident, tactical expression — like she's tracking
pressing triggers. Background: blurred soccer field at dusk with floodlights,
hints of red and navy decor.
```

### 7. Beckett Calloway — DC United (MLS)

```
Writer 7 of 14: Beckett Calloway — covers the Washington pro men's soccer team.
A mixed-race man (Black and white) in his late 20s, well-groomed, a single
small silver earring. Wearing a black slim-fit button-down with a subtle red
pocket square. Cosmopolitan vibe, slight knowing smirk — like a soccer purist
who's seen every MLS season. Background: blurred urban skyline through a
window, a soccer scarf (no logos) draped over a chair.
```

### 8. Chuck Harrington — Capital City Go-Go (NBA G-League)

```
Writer 8 of 14: Chuck Harrington — covers the Washington pro developmental
basketball team. A Black man in his mid-40s, shaved head, warm easy smile.
Wearing a red-and-navy polo with the collar slightly popped, a simple silver
chain. Hometown DC energy — looks like he's known these prospects since they
were in middle school. Background: blurred small-arena gym floor, basketball
hoop barely visible in deep focus.
```

### 9. Terry Lane — Maryland Terrapins (College Basketball)

```
Writer 9 of 14: Terry Lane — covers the University of Maryland basketball
team. A white man in his mid-30s, casual look, slight stubble, brown hair
worn slightly messy. Wearing a red half-zip over a black t-shirt with a
red-black-gold-white wristband (Maryland state flag colors). Approachable
expression — like a fan who became a writer. Background: blurred collegiate
gym, gold-trimmed bleachers in deep focus.
```

### 10. Cav Mitchell — Virginia Cavaliers (College Basketball)

```
Writer 10 of 14: Cav Mitchell — covers the University of Virginia basketball
team. A white man in his late 40s, distinguished, gray at the temples, neatly
groomed. Wearing a navy blazer over a soft orange-tinged button-down, no tie.
Refined, slow-burn analyst vibe — like an ACC traditionalist. Background:
blurred book-lined office with subtle orange and navy accents, hint of
brick architecture through a window.
```

### 11. Hayes Bremner — Virginia Tech Hokies (College Basketball)

```
Writer 11 of 14: Hayes Bremner — covers the Virginia Tech basketball team.
A white man in his mid-30s, rugged, dark stubble, slightly weathered hands
visible at the edge of frame. Wearing a maroon flannel shirt over a plain
t-shirt. Blue-collar, scrappy vibe — looks like he hiked to the game.
Background: blurred small-mountain-town newsroom with maroon and burnt-orange
accents.
```

### 12. Vance Hoya — Georgetown Hoyas (College Basketball)

```
Writer 12 of 14: Vance Hoya — covers the Georgetown University basketball
team. A white man in his late 30s, preppy and polished, slicked-back dark
hair. Wearing a gray wool blazer over a navy quarter-zip. Catholic-school
prestige vibe — looks like he can quote every Big East coach by tenure.
Background: blurred old-library-feel office with leather chairs and faint
navy banners.
```

### 13. Mason Adams — George Mason Patriots (Atlantic 10, both men's + women's)

```
Writer 13 of 14: Mason Adams — covers George Mason University basketball
(both the men's and women's programs). A Black man in his early 40s,
scholarly, round wire-rimmed glasses, neat short beard. Wearing an emerald
green polo with subtle gold trim. Patriot-conscious, history-buff vibe —
looks like he can name every Founding Father AND every mid-major coach.
Background: blurred desk with American-history books visible, faint old
American flag in deep blur.
```

### 14. Eagle Reed — Mary Washington Eagles (NCAA Division III)

```
Writer 14 of 14: Eagle Reed — covers the University of Mary Washington Eagles,
NCAA Division III basketball. An Asian-American woman in her late 30s,
friendly bright expression, modern frame glasses. Wearing a navy fleece
quarter-zip with silver trim. Passionate D3 small-school enthusiast — looks
like a small-college lifer who knows every player by name. Background:
blurred small-college gym with a wooden floor and a coffee mug on the desk.
```

---

## Tips for getting good results

- **First attempt is often 80% there.** Use follow-up messages to dial in:
  "make her hair slightly shorter," "less professional smile, more candid,"
  "the background is too saturated — mute it 30%."
- **If DALL-E gives a logo by accident**, say: "regenerate without any visible
  logos, marks, or team names."
- **If a face looks too generic or AI-rendered**, ask: "more individual
  features — slightly asymmetric, a distinctive nose or jaw, less idealized."
- **For consistency across the 14**, after a few good portraits, you can say:
  "match the lighting and depth-of-field of the previous portrait" to keep
  the set cohesive.
- **Diversity check at the end**: review all 14 side by side. If too many
  look similar (same age, ethnicity, lighting), regenerate the outliers to
  rebalance.

## What to do once you have all 14

1. Save each as a 512×512 JPG named after the writer ID (`tucker.jpg`,
   `wexler.jpg`, `frost.jpg`, `cooper.jpg`, `avery.jpg`, `holloway.jpg`,
   `calloway.jpg`, `harrington.jpg`, `lane.jpg`, `mitchell.jpg`, `bremner.jpg`,
   `hoya.jpg`, `adams.jpg`, `reed.jpg`)
2. Upload to your admin's image storage (same path family as
   `blogs/authors/1748435759641.jpg`)
3. Send me the URL pattern (e.g., `blogs/authors/writers/{id}.jpg`)
4. I'll wire `author_image` per persona in `generate_content.py` so every
   recap automatically renders the right writer's portrait
5. In `AIWriters.jsx`, the placeholder squares on each writer card become
   `<img>` tags pointing at the same URLs
