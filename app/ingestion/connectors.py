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


async def fetch_ashby(client: httpx.AsyncClient, board_slug: str) -> list[NormalizedJob]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{board_slug}"
    resp = await client.get(url, timeout=20.0)
    resp.raise_for_status()
    jobs: list[NormalizedJob] = []
    for item in resp.json().get("jobs", []):
        title = (item.get("title") or "").strip()
        loc = (item.get("location") or "").strip()
        desc = normalize_html(item.get("descriptionHtml") or item.get("descriptionPlain") or "")
        is_remote = bool(item.get("isRemote")) or _detect_remote(title, loc)
        jobs.append(
            NormalizedJob(
                external_id=str(item.get("id") or item.get("jobUrl") or title),
                source="ashby",
                title=title,
                location=loc,
                is_remote=is_remote,
                description=desc,
                apply_url=item.get("jobUrl") or item.get("applyUrl") or "",
            )
        )
    return jobs


async def fetch_remotive(client: httpx.AsyncClient, board_slug: str = "all") -> list[NormalizedJob]:
    params = {} if board_slug in ("", "all") else {"category": board_slug}
    resp = await client.get("https://remotive.com/api/remote-jobs", params=params, timeout=20.0)
    resp.raise_for_status()
    jobs: list[NormalizedJob] = []
    for item in resp.json().get("jobs", []):
        title = (item.get("title") or "").strip()
        loc = (item.get("candidate_required_location") or "Worldwide").strip()
        desc = normalize_html(item.get("description") or "")
        jobs.append(
            NormalizedJob(
                external_id=str(item["id"]),
                source="remotive",
                title=title,
                location=loc,
                is_remote=True,
                description=desc,
                apply_url=item.get("url") or "",
            )
        )
    return jobs
