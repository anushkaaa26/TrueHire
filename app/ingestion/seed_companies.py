import asyncio
import os
import asyncpg
import httpx

DEFAULT_DB_URL = "postgresql://truehire:truehire_dev@localhost:5432/truehire"

CANDIDATE_BOARDS: list[tuple[str, str, str, str]] = [
    # Greenhouse — India & Remote-Friendly Tech
    ("Razorpay", "greenhouse", "razorpay", "razorpay.com"),
    ("Groww", "greenhouse", "groww", "groww.in"),
    ("Postman", "greenhouse", "postman", "postman.com"),
    ("PhonePe", "greenhouse", "phonepe", "phonepe.com"),
    ("CRED", "greenhouse", "cred", "cred.club"),
    ("Meesho", "greenhouse", "meesho", "meesho.com"),
    ("Swiggy", "greenhouse", "swiggy", "swiggy.com"),
    ("Zepto", "greenhouse", "zepto", "zeptonow.com"),
    ("Juspay", "greenhouse", "juspay", "juspay.in"),
    ("Chargebee", "greenhouse", "chargebee", "chargebee.com"),
    ("Freshworks", "greenhouse", "freshworks", "freshworks.com"),
    ("Hasura", "greenhouse", "hasura", "hasura.io"),
    ("Acko", "greenhouse", "acko", "acko.com"),
    ("Slice", "greenhouse", "slice", "sliceit.com"),
    ("CoinDCX", "greenhouse", "coindcx", "coindcx.com"),
    ("GitLab", "greenhouse", "gitlab", "gitlab.com"),
    ("Stripe", "greenhouse", "stripe", "stripe.com"),
    ("Figma", "greenhouse", "figma", "figma.com"),
    ("Cloudflare", "greenhouse", "cloudflare", "cloudflare.com"),
    ("MongoDB", "greenhouse", "mongodb", "mongodb.com"),
    ("Databricks", "greenhouse", "databricks", "databricks.com"),
    ("Coinbase", "greenhouse", "coinbase", "coinbase.com"),
    ("DoorDash", "greenhouse", "doordash", "doordash.com"),
    ("Robinhood", "greenhouse", "robinhood", "robinhood.com"),
    ("Airbnb", "greenhouse", "airbnb", "airbnb.com"),
    ("Dropbox", "greenhouse", "dropbox", "dropbox.com"),
    ("Okta", "greenhouse", "okta", "okta.com"),
    ("Twilio", "greenhouse", "twilio", "twilio.com"),
    ("Elastic", "greenhouse", "elastic", "elastic.co"),
    ("Grafana Labs", "greenhouse", "grafanalabs", "grafana.com"),
    ("Canonical", "greenhouse", "canonical", "canonical.com"),
    ("Automattic", "greenhouse", "automattic", "automattic.com"),
    ("Contentful", "greenhouse", "contentful", "contentful.com"),
    ("Algolia", "greenhouse", "algolia", "algolia.com"),
    ("Netlify", "greenhouse", "netlify", "netlify.com"),
    ("Vercel", "greenhouse", "vercel", "vercel.com"),
    ("Supabase", "greenhouse", "supabase", "supabase.com"),
    ("Scale AI", "greenhouse", "scaleai", "scale.com"),
    ("Anthropic", "greenhouse", "anthropic", "anthropic.com"),
    ("Weights & Biases", "greenhouse", "wandb", "wandb.ai"),

    # Lever — India & Remote-Friendly Tech
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
    ("Toplyne", "lever", "toplyne", "toplyne.io"),
    ("Remote.com", "lever", "remotecom", "remote.com"),
    ("Palantir", "lever", "palantir", "palantir.com"),
    ("Klarna", "lever", "klarna", "klarna.com"),
    ("Spotify", "lever", "spotify", "spotify.com"),
    ("Netflix", "lever", "netflix", "netflix.com"),
    ("Wealthfront", "lever", "wealthfront", "wealthfront.com"),
    ("Plaid", "lever", "plaid", "plaid.com"),

    # Ashby — AI & Remote-First Tech
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
    ("Vapi", "ashby", "vapi", "vapi.ai"),
    ("PostHog", "ashby", "posthog", "posthog.com"),
    ("Raycast", "ashby", "raycast", "raycast.com"),
    ("Cal.com", "ashby", "cal", "cal.com"),
    ("Replit", "ashby", "replit", "replit.com"),
    ("Ramp", "ashby", "ramp", "ramp.com"),
    ("Sierra", "ashby", "sierra", "sierra.ai"),
    ("Harvey", "ashby", "harvey", "harvey.ai"),
    ("Cognition", "ashby", "cognition", "cognition.ai"),

    # Remotive — Remote Categories
    ("Remotive Software Dev", "remotive", "software-dev", "remotive.com"),
    ("Remotive Data", "remotive", "data", "remotive.com"),
    ("Remotive DevOps", "remotive", "devops", "remotive.com"),
]

PROBE_URLS = {
    "greenhouse": lambda s: f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs",
    "lever": lambda s: f"https://api.lever.co/v0/postings/{s}?mode=json",
    "ashby": lambda s: f"https://api.ashbyhq.com/posting-api/job-board/{s}",
    "remotive": lambda s: f"https://remotive.com/api/remote-jobs?category={s}&limit=1",
}


async def probe_board(client: httpx.AsyncClient, ats_type: str, slug: str) -> bool:
    url = PROBE_URLS[ats_type](slug)
    try:
        resp = await client.get(url, timeout=10.0)
        return resp.status_code == 200
    except Exception:
        return False


async def main() -> None:
    db_url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    conn = await asyncpg.connect(db_url)
    valid_count = 0

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            sem = asyncio.Semaphore(12)

            async def check_and_insert(entry: tuple[str, str, str, str]) -> bool:
                name, ats_type, slug, domain = entry
                async with sem:
                    ok = await probe_board(client, ats_type, slug)
                if not ok:
                    print(f"[SKIP] {ats_type}:{slug}")
                    return False
                await conn.execute(
                    """
                    INSERT INTO companies (name, ats_type, board_slug, domain)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (ats_type, board_slug) DO UPDATE
                    SET name = EXCLUDED.name, domain = EXCLUDED.domain
                    """,
                    name, ats_type, slug, domain,
                )
                print(f"[OK]   {ats_type}:{slug}")
                return True

            results = await asyncio.gather(*(check_and_insert(b) for b in CANDIDATE_BOARDS))
            valid_count = sum(1 for r in results if r)

        total = await conn.fetchval("SELECT COUNT(*) FROM companies")
        print(f"\nVerified {valid_count}/{len(CANDIDATE_BOARDS)} boards. Total companies in DB: {total}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
