# For Quincy — Articles on thensmt.com

Hey Quincy,

**Update: we are NOT using Contentful.** The plan changed — the content pipeline now pushes articles directly to the existing NSMT admin backend. No new CMS needed.

Your job is to wire up the React frontend to fetch and display articles from the same API the admin portal already uses.

---

## The API

**Base URL:** `https://rjl5qaqz7k.execute-api.us-east-1.amazonaws.com/prod`

Articles are stored as blog entries. The endpoint you need:

```
GET /blogs
```

This returns all active (published) blog entries. No auth required for public reads — confirm with David if you get a 401.

---

## Blog Object Shape

```json
{
  "blogId": "BLOG#e4aed01d-...",
  "title": "Mary Washington Advances to Sweet 16 With 73-68 Thriller",
  "slug": "mary-washington-sweet-16-recap-2026-03-14",
  "description": "<p>Full article body in HTML...</p>",
  "author": "NSMT Staff",
  "author_image": "blogs/authors/1748435759641.jpg",
  "image": "",
  "category_id": 10,
  "categoryId": "CAT#10",
  "is_active": 1,
  "is_popular": 1,
  "created_at": "2026-03-15 02:21:46.000000"
}
```

**Key fields:**
| Field | Description |
|-------|-------------|
| `title` | Article headline |
| `slug` | URL identifier — use for routing |
| `description` | Full article body — already formatted as HTML `<p>` tags, render with `dangerouslySetInnerHTML` |
| `author` | Byline |
| `image` | Featured image URL (may be empty) |
| `category_id` | `10` = College, `19` = Pro sports |
| `is_active` | Only show entries where `is_active === 1` |
| `created_at` | Publication date |

---

## What to Build

A **news/articles listing page** on thensmt.com. No individual article pages needed.

Each article card should show:
- Thumbnail image (`image` field — may be empty, use a placeholder)
- Title
- Author + date
- Full article body (`description` — render as HTML)
- Category badge (College / Pro)

Filter or group by `category_id` if it makes sense for the layout.

---

## Notes

- Only show entries where `is_active === 1` — David reviews and activates each article before it goes live
- The `description` field contains full HTML — safe to render with `dangerouslySetInnerHTML`, it only contains `<p>` tags
- `image` is added manually by David before publishing — have a fallback/placeholder ready
- New drafts are auto-generated every morning for any DC/MD/VA team that played the night before

Questions? Reach out to David.
