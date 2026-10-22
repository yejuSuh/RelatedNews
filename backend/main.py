from concurrent.futures import ThreadPoolExecutor
import heapq
import json
import os
import uuid
import re
from datetime import datetime, timezone
from typing import List, Literal, Optional, Tuple
from urllib.parse import urlparse
import asyncio

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

from backend.cache import PersistentCache

from google import genai
from google.genai import types

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
assert GOOGLE_API_KEY, "GOOGLE_API_KEY must be set"

CACHE = PersistentCache()


gemini = genai.Client(api_key=GOOGLE_API_KEY)


Feedback = Literal["like", "dislike"]


class CrossReference(BaseModel):
    title: str
    url: str
    note: Optional[str] = None


class RecommendationItem(BaseModel):
    id: str
    title: str
    url: str
    summary: str
    source: str
    score: float
    feedback: Optional[Feedback] = None
    crossReferences: Optional[List[CrossReference]] = None


class FeedbackRequest(BaseModel):
    source: str
    feedback: Feedback


class StructuredResponse(BaseModel):
    query: str
    createdAt: str
    items: List[RecommendationItem]


class RelatedRequest(BaseModel):
    query: str
    url: HttpUrl
    title: str
    contentSnippet: str


def derive_query(req: RelatedRequest) -> str:
    if req.query and req.query.strip():
        return req.query.strip()
    if req.title and req.title.strip():
        return req.title.strip()
    if req.contentSnippet and req.contentSnippet.strip():
        return req.contentSnippet.strip()[:200]
    if req.url and req.url.host:
        return req.url.host
    return "Current page"


def get_feedback_for_source(source: str) -> Optional[Feedback]:
    if not source:
        return None
    data = CACHE.get(f"feedback::{source}")
    if isinstance(data, dict):
        fb = data.get("feedback")
        if fb in ("like", "dislike"):
            return fb  # type: ignore[return-value]
    return None


def extract_json_object(text: str):
    s = text.strip()
    if not s:
        raise ValueError("Empty LLM response")

    fence_match = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL | re.IGNORECASE)
    if fence_match:
        s = fence_match.group(1).strip()

    if not s.lstrip().startswith("{"):
        start = s.find("{")
        end = s.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("No JSON object braces found in response")
        s = s[start : end + 1]

    data = json.loads(s)
    if not isinstance(data, dict):
        raise ValueError("Parsed JSON is not an object")
    return data


def normalize_domain(url_or_host: str) -> str:
    if not url_or_host:
        return ""
    if "://" in url_or_host:
        try:
            host = urlparse(url_or_host).hostname or ""
        except Exception:
            host = ""
    else:
        host = url_or_host
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def sanitize_phrasing(text: str) -> str:
    if not text:
        return text

    # Remove "the candidate article"
    text = re.sub(
        r"\bthe candidate article('?s)?\b",
        "the piece",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bthis candidate article\b",
        "this piece",
        text,
        flags=re.IGNORECASE,
    )

    # Remove boilerplate starts like "This article", "This piece", "This report"
    text = re.sub(
        r"^(This (article|piece|report|story)\s+)",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return text.strip()


def snippet_from_supports(chunks, supports) -> dict:
    per_chunk_texts = {i: [] for i in range(len(chunks))}

    for s in supports:
        seg = getattr(s, "segment", None)
        if not seg or not getattr(seg, "text", None):
            continue
        seg_text = seg.text.strip()
        if not seg_text:
            continue

        indices = getattr(s, "grounding_chunk_indices", []) or []
        for idx in indices:
            if 0 <= idx < len(chunks):
                per_chunk_texts[idx].append(seg_text)

    snippets = {}
    for idx, texts in per_chunk_texts.items():
        if not texts:
            continue
        joined = " ".join(dict.fromkeys(texts))  # dedupe in order
        sentences = re.split(r"(?<=[.!?])\s+", joined)
        snippet = " ".join(sentences[:4]).strip()
        snippets[idx] = snippet

    return snippets


def _looks_like_inaccessible_message(lowered_summary: str) -> bool:
    if not lowered_summary:
        return False
    if "could not be retrieved" in lowered_summary:
        return True
    if "unable to retrieve" in lowered_summary:
        return True
    if "url appears inaccessible" in lowered_summary:
        return True
    if "unable to access the content at" in lowered_summary:
        return True
    if lowered_summary.startswith("unfortunately") and (
        "retrieve" in lowered_summary or "access" in lowered_summary
    ):
        return True
    return False


def resolve_redirect_url(uri: str) -> str:
    """
    Resolve Google redirect URLs to their final destination.
    """
    if not uri:
        return uri

    cache_key = f"resolve::{uri}"
    cached = CACHE.get(cache_key)
    if isinstance(cached, str):
        return cached

    host = normalize_domain(uri)
    redirectish = any(
        s in host
        for s in [
            "google.",
            "vertexaisearch.cloud.google.com",
            "gstatic.com",
        ]
    )

    if not redirectish:
        # Not a known redirect host; just return as-is.
        CACHE.set(cache_key, uri)
        return uri

    try:
        resp = requests.get(
            uri,
            allow_redirects=True,
            timeout=6,
            headers={"User-Agent": "Mozilla/5.0 (related-coverage-extension)"},
        )
        final_url = resp.url or uri
    except Exception:
        final_url = uri

    CACHE.set(cache_key, final_url)
    return final_url


def search_candidates(req: RelatedRequest) -> List[dict]:
    print("S", req.url)
    main_query = derive_query(req)

    main_site = normalize_domain(str(req.url))

    cache_key = f"search::{main_query}"
    cached = CACHE.get(cache_key)
    if cached is not None:
        return cached

    search_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(tools=[search_tool])

    user_prompt = f"""
The user is reading an article about:

{main_query}

Contents:

{req.contentSnippet}

Use Google Search to find several high-quality news or analysis pieces that
specifically cover the same incident or closely related events, from diverse
and reputable outlets. State the article name and then provide summaries for each, identifying key points and
information that would be interesting to the user from each.

Avoid returning results from the same outlet as the main article (domain: {main_site})
or community-written websites like Wikipedia which have no verifiable authors.
"""

    try:
        response = gemini.models.generate_content(
            model="gemini-2.5-flash",
            contents=[{"role": "user", "parts": [{"text": user_prompt.strip()}]}],
            config=config,
        )

        if not response.candidates:
            raise ValueError("No candidates returned from Gemini search call")

        cand0 = response.candidates[0]
        gm = getattr(cand0, "grounding_metadata", None)
        if not gm:
            raise ValueError("No grounding_metadata available")

        chunks = getattr(gm, "grounding_chunks", None) or []
        supports = getattr(gm, "grounding_supports", None) or []

    except Exception as e:
        raise RuntimeError("Failed to generate") from e

    snippets_by_idx = snippet_from_supports(chunks, supports)

    items: List[dict] = []
    for idx, ch in enumerate(chunks):
        web = getattr(ch, "web", None)
        if not web:
            continue

        uri = getattr(web, "uri", "") or ""
        if not uri:
            continue

        final_url = resolve_redirect_url(uri)
        if not final_url:
            continue

        domain = normalize_domain(final_url)
        if not domain:
            continue

        if "wikipedia.org" in domain:
            continue

        if main_site and domain and domain == main_site:
            continue

        title_raw = (getattr(web, "title", "") or "").strip()

        source_name = domain or "Unknown"

        snippet = snippets_by_idx.get(idx, "")
        if not snippet:
            snippet = (
                f"Coverage from {source_name} related to '{main_query}', "
                "useful for comparing facts and framing with other reports."
            )

        items.append(
            {
                "id": final_url or str(uuid.uuid4()),
                "title": title_raw
                or source_name
                or "(untitled)",  # will be replaced later
                "url": final_url,
                "type": "articles",
                "raw_content": snippet,  # search-derived description
                "source": source_name,
            }
        )

    # One article per domain
    seen_domains = set()
    unique_items = []
    for it in items:
        domain_key = normalize_domain(it["source"] or it["url"])
        if not domain_key:
            domain_key = f"__nohost__:{it['id']}"
        if domain_key in seen_domains:
            continue
        seen_domains.add(domain_key)
        unique_items.append(it)
    items = unique_items

    if not items:
        raise ValueError("no relevant results")

    print("D")
    CACHE.set(cache_key, items)
    return items


def analyze_candidate(
    main_query: str,
    main_url: str,
    main_snippet: str,
    candidate: dict,
) -> Optional[Tuple[str, str, int, List[CrossReference]]]:
    title = candidate.get("title", "")
    candidate_url = candidate.get("url", "")
    source_domain = candidate.get("source", "") or normalize_domain(candidate_url)
    snippet = candidate.get("raw_content", "")

    key_hash = hash(("analysis", main_query, main_url or "", candidate_url, title))
    cache_key = f"analysis::{key_hash}"
    cached = CACHE.get(cache_key)
    print("A", candidate_url)
    if cached is not None:
        score = cached.get("score", 0)
        headline = str(cached.get("headline", "")).strip()
        summary = str(cached.get("summary", "")).strip()
        cr_list = [CrossReference(**cr) for cr in cached.get("crossReferences", [])]
        headline = sanitize_phrasing(headline)
        summary = sanitize_phrasing(summary)
        lowered = summary.lower()
        if _looks_like_inaccessible_message(lowered):
            return None
        if not headline:
            headline = title or f"Coverage from {source_domain or 'source'}"
        display_title = f"{headline} — {source_domain}" if source_domain else headline
        return display_title, summary, score, cr_list

    system_prompt = """
You help a browser extension cross-check a main news article against another article.

You can fetch and read the pages at the given URLs using url_context.
Your tasks:

1) Extract the article's REAL headline from the comparison URL.
   - Use the page's main <h1> or headline text if available.
   - Otherwise use the browser <title> or best visible headline.
   - Do NOT paraphrase or rewrite it; copy it as written (except trimming whitespace).

2) Compare what the comparison piece says about the same incident as the main article.

Behaviour when URLs fail:
- If a URL cannot be loaded, DO NOT mention that.
- DO NOT say: "unfortunately", "content could not be retrieved", "URL is inaccessible", etc.
- Fall back to title/source/snippet in the prompt and base comparison on that.

Style constraints:
- Do NOT use phrases like "the comparison article" or "this comparison article".
- Do NOT start with “This article…”, “This piece…”, or “This report…”.
- Start summaries directly with information, e.g.:
  “Highlights…”, “Emphasizes…”, “Adds detail on…”, “Challenges the claim that…”.
- Keep wording tight and non-repetitive.

OUTPUT FORMAT (IMPORTANT):
- Output ONLY a JSON object:
  {
    "score": <an integer score from 0-100 where 100 is most relevant and 0 is not relevant at all>,
    "headline": "<exact headline from the page>",
    "summary": "<<=30 words, 1–2 sentences, explaining how this piece relates to the main article>",
    "aspects": [
      {
        "aspect": "<short label (1–4 words)>",
        "note": "<<=20 words, single sentence on how this piece aligns/contradicts/adds context>"
      },
      ...
    ]
  }
"""

    main_url_text = main_url

    user_prompt = f"""
Main article:
- Headline or topic: {main_query}
- URL: {main_url_text}

Main article snippet:
{main_snippet}

Comparison article:
- Existing label or title (may be generic): {title}
- Source domain: {source_domain}
- URL: {candidate_url}

Comparison snippet / description (from search):
{snippet}

When you set "headline", copy the actual article headline exactly from the page.
If you cannot see a headline, use the best available page title without paraphrasing.

Return ONLY the JSON object described above.
"""

    tools = [{"url_context": {}}]
    config = types.GenerateContentConfig(tools=tools)

    try:
        response = gemini.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                {"role": "model", "parts": [{"text": system_prompt.strip()}]},
                {"role": "user", "parts": [{"text": user_prompt.strip()}]},
            ],
            config=config,
        )
        raw = response.text or ""
        obj = extract_json_object(raw)

        score = obj.get("score", 0)
        headline = str(obj.get("headline", "")).strip()
        summary = str(obj.get("summary", "")).strip()
        aspects = obj.get("aspects") or []

        headline = sanitize_phrasing(headline)
        summary = sanitize_phrasing(summary)
        lowered = summary.lower()
        if _looks_like_inaccessible_message(lowered) or not summary:
            print("Analysis unusable or inaccessible; skipping article.")
            return None

        if not headline:
            headline = title or f"Coverage from {source_domain}"

        display_title = f"{headline} — {source_domain}" if source_domain else headline

        cross_refs: List[CrossReference] = []
        for item in aspects[:2]:  # max 2 aspects
            if not isinstance(item, dict):
                continue
            aspect = sanitize_phrasing(str(item.get("aspect", "")).strip())
            note = sanitize_phrasing(str(item.get("note", "")).strip())
            if not aspect:
                continue
            cr = CrossReference(
                title=aspect,
                url=candidate_url or "#",
                note=note or None,
            )
            cross_refs.append(cr)

        print("T", candidate_url)
        CACHE.set(
            cache_key,
            {
                "headline": headline,
                "summary": summary,
                "score": score,
                "crossReferences": [cr.model_dump() for cr in cross_refs],
            },
        )
        return display_title, summary, score, cross_refs

    except Exception as e:
        print("Gemini analysis error, skipping candidate:", e)
        return None


def feedback_rank(source: str | None) -> int:
    fb = get_feedback_for_source(source) if source else None

    if fb == "like":
        return 0
    if fb is None:
        return 1
    return 2


async def generate_related_resources(req: RelatedRequest) -> StructuredResponse:
    query = derive_query(req)
    main_url = str(req.url)
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor() as pool:
        candidates = await loop.run_in_executor(pool, search_candidates, req)

        top_candidates = heapq.nsmallest(
            5, candidates, lambda cand: feedback_rank(cand.get("source"))
        )

        tasks = [
            loop.run_in_executor(
                pool,
                analyze_candidate,
                query,
                main_url,
                req.contentSnippet,
                c,
            )
            for c in top_candidates
        ]

        results = await asyncio.gather(*tasks)
        items: List[RecommendationItem] = []
        for c, analysis in zip(top_candidates, results):
            if analysis is None:
                continue
            display_title, summary, score, crossrefs = analysis
            source = c["source"]
            existing_feedback = get_feedback_for_source(source) if source else None

            items.append(
                RecommendationItem(
                    id=c.get("id") or str(uuid.uuid4()),
                    title=display_title,
                    url=c.get("url") or "",
                    summary=summary,
                    source=source,
                    score=max(min(score, 100), 0) / 100,
                    crossReferences=crossrefs,
                    feedback=existing_feedback,
                )
            )

        items.sort(key=lambda item: (feedback_rank(item.source), -item.score))

        return StructuredResponse(
            query=query,
            createdAt=datetime.now(timezone.utc).isoformat(),
            items=items,
        )


# ---------------------------
# FastAPI App
# ---------------------------

app = FastAPI(title="Related Articles Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/related", response_model=StructuredResponse)
async def related(payload: RelatedRequest):
    return await generate_related_resources(payload)


@app.post("/feedback")
async def submit_feedback(payload: FeedbackRequest):
    cache_key = f"feedback::{payload.source}"
    CACHE.set(
        cache_key,
        {
            "feedback": payload.feedback,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"status": "ok", "source": payload.source, "feedback": payload.feedback}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
    )
