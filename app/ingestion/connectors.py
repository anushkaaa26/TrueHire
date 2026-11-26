import httpx
from app.ingestion.schemas import NormalizedJob, normalize_html

REMOTE_KEYWORDS = ("remote", "work from home", "wfh", "anywhere")


def _detect_remote(title: str, location: str) -> bool:
    combined = f"{title} {location}".lower()
    return any(k in combined for k in REMOTE_KEYWORDS)


async def fetch_greenhouse(client: httpx.AsyncClient, board_slug: str) -> list[NormalizedJob]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_slug}/jobs?content=true"
    resp = await client.get(url, timeout=20.0)
    resp.raise_for_status()
    jobs = []
    for item in resp.json().get("jobs", []):
        title = item.get("title", "").strip()
        loc = (item.get("location") or {}).get("name", "").strip()
        desc = normalize_html(item.get("content", ""))
        jobs.append(
            NormalizedJob(
                external_id=str(item["id"]),
                source="greenhouse",
                title=title,
                location=loc,
                is_remote=_detect_remote(title, loc),
                description=desc,
                apply_url=item.get("absolute_url", ""),
            )
        )
    return jobs


async def fetch_lever(client: httpx.AsyncClient, board_slug: str) -> list[NormalizedJob]:
    url = f"https://api.lever.co/v0/postings/{board_slug}?mode=json"
    resp = await client.get(url, timeout=20.0)
    resp.raise_for_status()
    jobs = []
    for item in resp.json():
        title = item.get("text", "").strip()
        loc = (item.get("categories") or {}).get("location", "").strip()
        desc = normalize_html(item.get("descriptionPlain") or item.get("description") or "")
        jobs.append(
            NormalizedJob(
                external_id=str(item["id"]),
                source="lever",
                title=title,
                location=loc,
                is_remote=_detect_remote(title, loc) or item.get("workplaceType") == "remote",
                description=desc,
                apply_url=item.get("hostedUrl", ""),
            )
        )
    return jobs
