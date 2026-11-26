import asyncio
import os
import asyncpg
import httpx

DEFAULT_DB_URL = "postgresql://truehire:truehire_dev@localhost:5432/truehire"

CANDIDATE_BOARDS: list[tuple[str, str, str, str]] = [
    ("Groww", "greenhouse", "groww", "groww.in"),
    ("Slice", "greenhouse", "slice", "sliceit.com"),
    ("GitLab", "greenhouse", "gitlab", "gitlab.com"),
    ("Razorpay", "greenhouse", "razorpay", "razorpay.com"),
    ("Postman", "greenhouse", "postman", "postman.com"),
    ("CRED", "greenhouse", "cred", "cred.club"),
    ("Meesho", "greenhouse", "meesho", "meesho.com"),
    ("PhonePe", "greenhouse", "phonepe", "phonepe.com"),
    ("Swiggy", "greenhouse", "swiggy", "swiggy.com"),
    ("Zepto", "greenhouse", "zepto", "zeptonow.com"),
    ("Juspay", "greenhouse", "juspay", "juspay.in"),
    ("Chargebee", "greenhouse", "chargebee", "chargebee.com"),
    ("Freshworks", "greenhouse", "freshworks", "freshworks.com"),
    ("Hasura", "greenhouse", "hasura", "hasura.io"),
    ("Acko", "greenhouse", "acko", "acko.com"),
    ("CoinDCX", "greenhouse", "coindcx", "coindcx.com"),
    ("Stripe", "greenhouse", "stripe", "stripe.com"),
    ("Figma", "greenhouse", "figma", "figma.com"),
    ("Cloudflare", "greenhouse", "cloudflare", "cloudflare.com"),
    ("MongoDB", "greenhouse", "mongodb", "mongodb.com"),
    ("Databricks", "greenhouse", "databricks", "databricks.com"),
    ("Coinbase", "greenhouse", "coinbase", "coinbase.com"),
    ("Airbnb", "greenhouse", "airbnb", "airbnb.com"),
    ("Dropbox", "greenhouse", "dropbox", "dropbox.com"),
    ("Okta", "greenhouse", "okta", "okta.com"),
    ("Twilio", "greenhouse", "twilio", "twilio.com"),
    ("Elastic", "greenhouse", "elastic", "elastic.co"),
    ("Grafana Labs", "greenhouse", "grafanalabs", "grafana.com"),
    ("Canonical", "greenhouse", "canonical", "canonical.com"),
    ("Automattic", "greenhouse", "automattic", "automattic.com"),
    ("Vercel", "greenhouse", "vercel", "vercel.com"),
    ("Supabase", "greenhouse", "supabase", "supabase.com"),
    ("Anthropic", "greenhouse", "anthropic", "anthropic.com"),
    ("Weights & Biases", "greenhouse", "wandb", "wandb.ai"),
    ("BrowserStack", "lever", "browserstack", "browserstack.com"),
    ("Darwinbox", "lever", "darwinbox", "darwinbox.com"),
    ("Mindtickle", "lever", "mindtickle", "mindtickle.com"),
    ("Innovaccer", "lever", "innovaccer", "innovaccer.com"),
    ("CleverTap", "lever", "clevertap", "clevertap.com"),
    ("MoEngage", "lever", "moengage", "moengage.com"),
    ("Yellow.ai", "lever", "yellow", "yellow.ai"),
    ("Plivo", "lever", "plivo", "plivo.com"),
    ("Hevo Data", "lever", "hevodata", "hevodata.com"),
    ("Sprinto", "lever", "sprinto", "sprinto.com"),
    ("Remote.com", "lever", "remotecom", "remote.com"),
    ("Palantir", "lever", "palantir", "palantir.com"),
    ("Klarna", "lever", "klarna", "klarna.com"),
    ("Spotify", "lever", "spotify", "spotify.com"),
    ("Netflix", "lever", "netflix", "netflix.com"),
    ("Plaid", "lever", "plaid", "plaid.com"),
    ("Level AI", "ashby", "level-ai", "thelevel.ai"),
    ("Ashby", "ashby", "ashby", "ashbyhq.com"),
    ("Linear", "ashby", "linear", "linear.app"),
    ("Notion", "ashby", "notion", "notion.so"),
    ("Deel", "ashby", "deel", "deel.com"),
    ("Perplexity", "ashby", "perplexity", "perplexity.ai"),
    ("Cohere", "ashby", "cohere", "cohere.com"),
    ("ElevenLabs", "ashby", "elevenlabs", "elevenlabs.io"),
    ("Modal", "ashby", "modal", "modal.com"),
    ("Pinecone", "ashby", "pinecone", "pinecone.io"),
    ("LangChain", "ashby", "langchain", "langchain.com"),
    ("PostHog", "ashby", "posthog", "posthog.com"),
    ("Raycast", "ashby", "raycast", "raycast.com"),
    ("Cal.com", "ashby", "cal", "cal.com"),
    ("Replit", "ashby", "replit", "replit.com"),
    ("Ramp", "ashby", "ramp", "ramp.com"),
    ("Sierra", "ashby", "sierra", "sierra.ai"),
    ("Cognition", "ashby", "cognition", "cognition.ai"),
    ("Remotive Software Dev", "remotive", "software-dev", "remotive.com"),
    ("Remotive Data", "remotive", "data", "remotive.com"),
    ("Remotive DevOps", "remotive", "devops", "remotive.com"),
]

PROBE_URLS = {
    "greenhouse": lambda s: f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs",
    "lever": lambda s: f"https://api.lever.co/v0/postings/{s}?mode=json",
    "ashby": lambda s: f"https://api.ashbyhq.com/posting-api/job-board/{s}",
    "remotive": lambda s: f"https://remotive.com/api/remote-jobs?category={s}&limit=5",
}


async def probe_board(client: httpx.AsyncClient, ats_type: str, slug: str) -> bool:
    url = PROBE_URLS[ats_type](slug)
    try:
        resp = await client.get(url, timeout=12.0)
        if resp.status_code != 200:
            return False
        data = resp.json()
        if ats_type == "greenhouse":
            return isinstance(data, dict) and len(data.get("jobs", [])) > 0
        if ats_type == "lever":
            return isinstance(data, list) and len(data) > 0
        if ats_type == "ashby":
            return isinstance(data, dict) and len(data.get("jobs", [])) > 0
        if ats_type == "remotive":
            return isinstance(data, dict) and len(data.get("jobs", [])) > 0
        return False
    except Exception:
        return False


async def main() -> None:
    db_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=5)
    headers = {"User-Agent": "TrueHireBot/0.1 (contact@truehire.local)"}

    try:
        async with httpx.AsyncClient(follow_redirects=True, headers=headers) as client:
            sem = asyncio.Semaphore(10)

            async def probe_one(entry: tuple[str, str, str, str]) -> tuple[tuple[str, str, str, str], bool]:
                name, ats_type, slug, domain = entry
                async with sem:
                    ok = await probe_board(client, ats_type, slug)
                print(f"[{'OK  ' if ok else 'SKIP'}] {ats_type}:{slug}")
                return entry, ok

            probed = await asyncio.gather(*(probe_one(b) for b in CANDIDATE_BOARDS))

        valid_entries = [entry for entry, ok in probed if ok]
        async with pool.acquire() as conn:
            async with conn.transaction():
                for name, ats_type, slug, domain in valid_entries:
                    await conn.execute(
                        """
                        INSERT INTO companies (name, ats_type, board_slug, domain)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (ats_type, board_slug) DO UPDATE
                        SET name = EXCLUDED.name, domain = EXCLUDED.domain
                        """,
                        name, ats_type, slug, domain,
                    )

            total_companies = await conn.fetchval("SELECT COUNT(*) FROM companies")
            total_jobs = await conn.fetchval("SELECT COUNT(*) FROM jobs")
            total_snaps = await conn.fetchval("SELECT COUNT(*) FROM job_snapshots")
            print(f"\nVerified {len(valid_entries)}/{len(CANDIDATE_BOARDS)} boards.")
            print(f"DB counts -> companies: {total_companies}, jobs: {total_jobs}, snapshots: {total_snaps}")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
