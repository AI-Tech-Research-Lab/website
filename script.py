"""Refresh the lab bibliography from OpenAlex and supplementary Scholar records."""

import argparse
from collections import Counter
from datetime import date
from html import escape
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unicodedata
from urllib.parse import urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
START_MARKER = "<!-- PUBLICATIONS_START -->"
END_MARKER = "<!-- PUBLICATIONS_END -->"
SCHOLAR_ID = "j2NbakMAAAAJ"


def title_key(title):
    title = re.sub(r"^the\s+", "", title, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower())


def get(session, url, **params):
    response = session.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response


def fetch_openalex(session, members, since):
    # Include inactive members as well, preserving the lab's publication history.
    ids = [m["openalex_id"] for m in members]
    params = {"filter": "authorships.author.id:" + "|".join(ids) + f",from_publication_date:{since}-01-01",
              "per-page": 200, "cursor": "*"}
    if os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = os.environ["OPENALEX_API_KEY"]
    works, cursors = {}, set()
    while params["cursor"]:
        if params["cursor"] in cursors:
            raise ValueError("OpenAlex repeated a pagination cursor")
        cursors.add(params["cursor"])
        payload = get(session, "https://api.openalex.org/works", **params).json()
        for work in payload["results"]:
            works[work["id"]] = work
        params["cursor"] = payload["meta"]["next_cursor"]
    if not works:
        raise ValueError("OpenAlex returned no publications; refusing to clear the page")
    records, counts = [], Counter()
    for work in works.values():
        authorships = work.get("authorships") or []
        author_ids = {(a.get("author") or {}).get("id", "").rsplit("/", 1)[-1]
                      for a in authorships if (a.get("author") or {}).get("id")}
        matched = [m["name"] for m in members if m["openalex_id"] in author_ids]
        counts.update(matched)
        if not matched or not work.get("display_name"):
            raise ValueError(f"Unexpected OpenAlex record: {work['id']}")
        locations = work.get("locations") or []
        published = [location for location in locations if location.get("is_published")
                     and (location.get("source") or {}).get("type") in {"journal", "conference"}]
        location = (published[0] if published else work.get("primary_location")) or {}
        source = location.get("source") or {}
        records.append({"title": work["display_name"], "year": work["publication_year"],
                        "authors": ", ".join((a.get("author") or {}).get("display_name") or a.get("raw_author_name") or "Unknown author" for a in authorships),
                        "venue": source.get("display_name") or "Venue not specified",
                        "url": work.get("doi") or location.get("landing_page_url") or work["id"],
                        "doi": work.get("doi"), "preprint": not published and (work.get("type") == "preprint" or "arxiv" in source.get("display_name", "").lower()),
                        "sources": [work["id"]], "members": matched})
    return records, dict(counts)


def parse_scholar_page(content):
    soup = BeautifulSoup(content, "html.parser")
    name = soup.select_one("#gsc_prf_in")
    if not name or name.get_text(strip=True) != "Manuel Roveri":
        raise ValueError("Scholar returned an unexpected profile or a blocking page")
    records = []
    for row in soup.select(".gsc_a_tr"):
        title, year = row.select_one(".gsc_a_at"), row.select_one(".gsc_a_y")
        if not title:  # Scholar may include an empty loading row.
            continue
        year = year.get_text(strip=True) if year else ""
        details = row.select(".gs_gray")
        venue = details[1].get_text(" ", strip=True) if len(details) > 1 else ""
        url = urljoin("https://scholar.google.com", title["href"])
        records.append({"title": title.get_text(" ", strip=True), "year": int(year) if year.isdigit() else None,
                        "authors": details[0].get_text(" ", strip=True) if details else "Unknown authors",
                        "venue": venue or "Venue not specified", "url": url, "doi": None,
                        "preprint": "arxiv" in venue.lower(), "sources": [url], "members": ["Manuel Roveri"]})
    more = soup.select_one("#gsc_bpf_more")
    return records, bool(more and not more.has_attr("disabled"))


def fetch_scholar():
    records, seen = [], set()
    for offset in range(0, 2000, 100):
        params = dict(user=SCHOLAR_ID, hl="en", pagesize=100, sortby="pubdate")
        if offset:
            params["cstart"] = offset
        # curl also works on hosts where Scholar rejects the Python HTTP client.
        response = subprocess.run(["curl", "--fail", "--silent", "--show-error", "--location",
                                   "--max-time", "30", "https://scholar.google.com/citations?" + urlencode(params)],
                                  capture_output=True, check=True, timeout=35)
        page, more = parse_scholar_page(response.stdout)
        urls = {p["url"] for p in page}
        if not page or urls & seen:
            raise ValueError("Scholar returned empty or repeated results")
        records.extend(page)
        seen.update(urls)
        if not more:
            return {"retrieved_on": date.today().isoformat(), "records": records}
    raise ValueError("Scholar pagination exceeded safety limit")


def deduplicate(records):
    groups, by_title, by_doi = [], {}, {}
    # Keep the published version and the fuller author list when titles coincide.
    for record in sorted(records, key=lambda p: (p["preprint"], -len(p["authors"]), -p["year"])):
        key, doi = title_key(record["title"]), (record.get("doi") or "").lower()
        index = by_doi.get(doi) if doi else None
        if index is None:
            index = by_title.get(key)
        if index is None:
            index = len(groups)
            groups.append(dict(record))
        else:
            for field in ("sources", "members"):
                groups[index][field] = sorted(set(groups[index][field] + record[field]))
        by_title[key] = index
        if doi:
            by_doi[doi] = index
    return sorted(groups, key=lambda p: (-p["year"], p["title"].casefold()))


def generate_html_list(publications):
    lines = []
    for pub in publications:
        url = pub["url"]
        if urlparse(url).scheme not in {"https", "http"}:
            raise ValueError("Publication URL must use HTTP(S)")
        title = f'<a href="{escape(url, quote=True)}">{escape(pub["title"])}</a>'
        preprint = " · Preprint" if pub["preprint"] else ""
        lines.append(f'<li><strong>{title}</strong><br><em>Authors:</em> {escape(pub["authors"])}<br>'
                     f'<em>Venue:</em> {escape(pub["venue"])} ({pub["year"]}){preprint}</li>')
    return "\n".join(lines)


def updated_html(content, publications, since, as_of=None):
    if content.count(START_MARKER) != 1 or content.count(END_MARKER) != 1:
        raise ValueError("Expected exactly one pair of publication markers")
    start = content.index(START_MARKER) + len(START_MARKER)
    end = content.index(END_MARKER)
    if start >= end or not publications:
        raise ValueError("Invalid markers or empty publication list")
    summary = (f'\n<p>Publications by members of the lab since {since}, including preprints. '
               f'{len(publications)} works · Updated {as_of or date.today().isoformat()}.</p>\n')
    return content[:start] + summary + "<ul>\n" + generate_html_list(publications) + "\n</ul>\n" + content[end:]


def write_json(path, payload):
    atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def atomic_write(path, content):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", type=int, default=date.today().year - 9, help="First year included (default: last ten calendar years)")
    parser.add_argument("--offline", action="store_true", help="Render the saved bibliography without network requests")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and report without changing files")
    args = parser.parse_args()
    page = ROOT / "pages/publications.html"
    snapshot_path = ROOT / "data/publications.json"
    cache_path = ROOT / "data/scholar-roveri.json"
    members = json.loads((ROOT / "data/members.json").read_text())
    if args.offline:
        snapshot = json.loads(snapshot_path.read_text())
        publications = [p for p in snapshot["publications"] if p["year"] >= args.since]
        args.since = max(args.since, snapshot["since"])
        if not args.dry_run:
            atomic_write(page, updated_html(page.read_text(), publications, args.since, snapshot["retrieved_on"]))
        print(f"Offline snapshot from {snapshot['retrieved_on']}: {len(publications)} works")
        return
    session = requests.Session()
    records, counts = fetch_openalex(session, members, args.since)
    cache = None
    try:
        cache = fetch_scholar()
        scholar_status = "live"
    except (requests.RequestException, ValueError, subprocess.SubprocessError, OSError) as error:
        if cache_path.exists():
            cache = json.loads(cache_path.read_text())
            scholar_status = f"cached ({cache['retrieved_on']})"
        else:
            scholar_status = "unavailable"
        print(f"Warning: Scholar refresh failed ({type(error).__name__}); {scholar_status}", file=sys.stderr)
    scholar_records = [p for p in (cache or {}).get("records", []) if p["year"] and p["year"] >= args.since]
    openalex_keys = {title_key(p["title"]) for p in records}
    missing = [p["title"] for p in scholar_records if title_key(p["title"]) not in openalex_keys]
    publications = deduplicate(records + scholar_records)
    snapshot = {"retrieved_on": date.today().isoformat(), "since": args.since,
                "openalex_counts_by_member": counts, "scholar_status": scholar_status,
                "scholar_comparison": {"profile": SCHOLAR_ID, "records_in_range": len(scholar_records),
                                       "titles_missing_from_openalex": missing}, "publications": publications}
    html = updated_html(page.read_text(), publications, args.since)
    for member in members:
        print(f'{member["name"]}: {counts.get(member["name"], 0)} OpenAlex works')
    print(f"Scholar: {scholar_status}, {len(scholar_records)} records, {len(missing)} additional titles")
    print(f"Total: {len(publications)} unique works since {args.since}")
    if not args.dry_run:
        if cache:
            write_json(cache_path, cache)
        write_json(snapshot_path, snapshot)
        atomic_write(page, html)


if __name__ == "__main__":
    try:
        main()
    except (requests.RequestException, ValueError, KeyError, OSError) as error:
        # Do not echo request URLs, which might contain an API key.
        print(f"Update failed ({type(error).__name__}). Existing page preserved.", file=sys.stderr)
        sys.exit(1)
