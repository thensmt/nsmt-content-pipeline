"""
NSMT Content Pipeline — Contentful Setup Script
Run this ONCE to create the Article content type in your Contentful space.
"""

import requests
import json
import os

SPACE_ID = os.environ.get("CONTENTFUL_SPACE_ID", "d6khuyxovvy4")
CMA_TOKEN = os.environ.get("CONTENTFUL_CMA_TOKEN")

if not CMA_TOKEN:
    print("ERROR: Set your CONTENTFUL_CMA_TOKEN environment variable first.")
    print("  export CONTENTFUL_CMA_TOKEN=your_token_here")
    exit(1)

BASE_URL = f"https://api.contentful.com/spaces/{SPACE_ID}/environments/master"
HEADERS = {
    "Authorization": f"Bearer {CMA_TOKEN}",
    "Content-Type": "application/vnd.contentful.management.v1+json",
}

CONTENT_TYPE = {
    "name": "Article",
    "description": "NSMT sports articles — game recaps, previews, roundups",
    "displayField": "title",
    "fields": [
        {"id": "title",       "name": "Title",        "type": "Symbol",   "required": True},
        {"id": "slug",        "name": "Slug",         "type": "Symbol",   "required": True},
        {"id": "excerpt",     "name": "Excerpt",      "type": "Symbol",   "required": False},
        {"id": "body",        "name": "Body",         "type": "Text",     "required": True},
        {"id": "articleType", "name": "Article Type", "type": "Symbol",   "required": False},
        {"id": "league",      "name": "League",       "type": "Symbol",   "required": False},
        {"id": "team",        "name": "Team",         "type": "Symbol",   "required": False},
        {"id": "gameDate",    "name": "Game Date",    "type": "Date",     "required": False},
        {"id": "author",      "name": "Author",       "type": "Symbol",   "required": False},
    ],
}

def create_content_type():
    url = f"{BASE_URL}/content_types/article"
    resp = requests.put(url, headers=HEADERS, json=CONTENT_TYPE)
    if resp.status_code in (200, 201):
        print("Content type created.")
        return True
    else:
        print(f"Failed to create content type: {resp.status_code}")
        print(resp.text)
        return False

def publish_content_type():
    # Get current version first
    url = f"{BASE_URL}/content_types/article"
    resp = requests.get(url, headers=HEADERS)
    version = resp.json().get("sys", {}).get("version", 1)

    pub_headers = {**HEADERS, "X-Contentful-Version": str(version)}
    pub_url = f"{BASE_URL}/content_types/article/published"
    resp = requests.put(pub_url, headers=pub_headers)
    if resp.status_code in (200, 201):
        print("Content type published.")
        return True
    else:
        print(f"Failed to publish content type: {resp.status_code}")
        print(resp.text)
        return False

if __name__ == "__main__":
    print("Setting up Contentful content model for NSMT...")
    if create_content_type():
        publish_content_type()
        print("\nDone! Your Contentful space is ready.")
        print("Next: run generate_content.py to create your first article draft.")
