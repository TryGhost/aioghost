"""Tests for the Ghost Admin API client."""

import re

import pytest
from aiohttp import ClientError
from aioresponses import aioresponses

from aioghost import GhostAdminAPI
from aioghost.exceptions import (
    GhostAuthError,
    GhostConnectionError,
    GhostError,
    GhostNotFoundError,
    GhostValidationError,
)

API_URL = "https://test.ghost.io"
API_KEY = (
    "650b7a9f8e8c1234567890ab:"
    "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
)


@pytest.fixture
def api():
    """Create a test API client."""
    return GhostAdminAPI(api_url=API_URL, admin_api_key=API_KEY)


# -----------------------------------------------------------------------------
# Initialization & Auth
# -----------------------------------------------------------------------------


def test_https_required():
    """Test that HTTP URLs are rejected."""
    with pytest.raises(ValueError, match="must use HTTPS"):
        GhostAdminAPI(api_url="http://test.ghost.io", admin_api_key=API_KEY)


def test_trailing_slash_stripped():
    """Test that trailing slashes are stripped from URL."""
    api = GhostAdminAPI(api_url="https://test.ghost.io/", admin_api_key=API_KEY)
    assert api.api_url == "https://test.ghost.io"


def test_invalid_api_key_format():
    """Test that invalid API key format raises error."""
    api = GhostAdminAPI(api_url=API_URL, admin_api_key="invalid-key-no-colon")
    with pytest.raises(GhostAuthError, match="Invalid API key format"):
        api._generate_token()


def test_invalid_api_key_secret():
    """Test that invalid API key secret raises error."""
    api = GhostAdminAPI(api_url=API_URL, admin_api_key="validid:not-hex-string")
    with pytest.raises(GhostAuthError, match="Invalid API key secret"):
        api._generate_token()


def test_generate_token_success(api: GhostAdminAPI):
    """Test that valid credentials generate a JWT token."""
    token = api._generate_token()
    assert token is not None
    assert len(token) > 50  # JWT tokens are reasonably long


# -----------------------------------------------------------------------------
# Site
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_site(api: GhostAdminAPI):
    """Test getting site info."""
    with aioresponses() as m:
        m.get(
            f"{API_URL}/ghost/api/admin/site/",
            payload={"site": {"title": "Test Site", "url": API_URL}},
        )
        async with api:
            site = await api.get_site()
        assert site["title"] == "Test Site"


@pytest.mark.asyncio
async def test_validate_credentials_success(api: GhostAdminAPI):
    """Test credential validation success."""
    with aioresponses() as m:
        m.get(f"{API_URL}/ghost/api/admin/site/", payload={"site": {"title": "Test"}})
        async with api:
            valid = await api.validate_credentials()
        assert valid is True


@pytest.mark.asyncio
async def test_validate_credentials_failure(api: GhostAdminAPI):
    """Test credential validation failure."""
    with aioresponses() as m:
        m.get(f"{API_URL}/ghost/api/admin/site/", status=401)
        async with api:
            valid = await api.validate_credentials()
        assert valid is False


# -----------------------------------------------------------------------------
# Members
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_members_count(api: GhostAdminAPI):
    """Test getting member counts."""
    with aioresponses() as m:
        m.get(
            f"{API_URL}/ghost/api/admin/members/stats/count/",
            payload={"total": 100, "data": [{"paid": 10, "free": 83, "comped": 5, "gift": 2}]},
        )
        async with api:
            members = await api.get_members_count()
        assert members["total"] == 100
        assert members["paid"] == 10
        assert members["free"] == 83
        assert members["comped"] == 5
        assert members["gift"] == 2


@pytest.mark.asyncio
async def test_get_members_count_empty_history(api: GhostAdminAPI):
    """Test getting member counts with no history data."""
    with aioresponses() as m:
        m.get(
            f"{API_URL}/ghost/api/admin/members/stats/count/",
            payload={"total": 50, "data": []},
        )
        async with api:
            members = await api.get_members_count()

        assert members["total"] == 50
        assert members["paid"] == 0
        assert members["free"] == 0
        assert members["comped"] == 0
        assert members["gift"] == 0


@pytest.mark.asyncio
async def test_get_mrr(api: GhostAdminAPI):
    """Test getting MRR data returns rounded whole currency units."""
    with aioresponses() as m:
        m.get(
            f"{API_URL}/ghost/api/admin/members/stats/mrr/",
            payload={
                "data": [
                    {"currency": "usd", "data": [{"value": 10000}, {"value": 12284}]},
                    {"currency": "eur", "data": [{"value": 5049}]},
                ]
            },
        )
        async with api:
            mrr = await api.get_mrr()
        assert mrr["usd"] == 123  # 12284 cents → $123
        assert mrr["eur"] == 50  # 5049 cents → €50 (rounded)


@pytest.mark.asyncio
async def test_get_mrr_empty(api: GhostAdminAPI):
    """Test getting MRR with no data."""
    with aioresponses() as m:
        m.get(f"{API_URL}/ghost/api/admin/members/stats/mrr/", payload={"data": []})
        async with api:
            mrr = await api.get_mrr()
        assert mrr == {}


# -----------------------------------------------------------------------------
# ARR
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_arr(api: GhostAdminAPI):
    """Test getting ARR data returns MRR × 12."""
    with aioresponses() as m:
        m.get(
            f"{API_URL}/ghost/api/admin/members/stats/mrr/",
            payload={
                "data": [
                    {"currency": "usd", "data": [{"value": 10000}]},
                    {"currency": "eur", "data": [{"value": 5000}]},
                ]
            },
        )
        async with api:
            arr = await api.get_arr()
        assert arr["usd"] == 1200  # 10000 cents → $100 MRR → $1200 ARR
        assert arr["eur"] == 600  # 5000 cents → €50 MRR → €600 ARR


@pytest.mark.asyncio
async def test_get_arr_empty(api: GhostAdminAPI):
    """Test getting ARR with no MRR data."""
    with aioresponses() as m:
        m.get(f"{API_URL}/ghost/api/admin/members/stats/mrr/", payload={"data": []})
        async with api:
            arr = await api.get_arr()
        assert arr == {}


# -----------------------------------------------------------------------------
# Posts
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_posts_count(api: GhostAdminAPI):
    """Test getting post counts."""
    with aioresponses() as m:
        # Use pattern to match URLs with query params
        posts_pattern = re.compile(rf"^{re.escape(API_URL)}/ghost/api/admin/posts/\?.*$")
        m.get(posts_pattern, payload={"posts": [], "meta": {"pagination": {"total": 42}}})
        m.get(posts_pattern, payload={"posts": [], "meta": {"pagination": {"total": 5}}})
        m.get(posts_pattern, payload={"posts": [], "meta": {"pagination": {"total": 2}}})
        async with api:
            counts = await api.get_posts_count()
        assert counts["published"] == 42
        assert counts["drafts"] == 5
        assert counts["scheduled"] == 2


@pytest.mark.asyncio
async def test_get_latest_post(api: GhostAdminAPI):
    """Test getting latest post."""
    with aioresponses() as m:
        posts_pattern = re.compile(rf"^{re.escape(API_URL)}/ghost/api/admin/posts/\?.*$")
        m.get(posts_pattern, payload={"posts": [{"title": "Latest Post", "slug": "latest-post"}]})
        async with api:
            post = await api.get_latest_post()
        assert post["title"] == "Latest Post"


@pytest.mark.asyncio
async def test_get_latest_post_none(api: GhostAdminAPI):
    """Test getting latest post when none exist."""
    with aioresponses() as m:
        posts_pattern = re.compile(rf"^{re.escape(API_URL)}/ghost/api/admin/posts/\?.*$")
        m.get(posts_pattern, payload={"posts": []})
        async with api:
            post = await api.get_latest_post()
        assert post is None


# -----------------------------------------------------------------------------
# Newsletters
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_newsletters(api: GhostAdminAPI):
    """Test getting newsletters."""
    with aioresponses() as m:
        pattern = re.compile(rf"^{re.escape(API_URL)}/ghost/api/admin/newsletters/\?.*$")
        m.get(
            pattern,
            payload={
                "newsletters": [
                    {"name": "Weekly", "count": {"members": 1000}},
                    {"name": "Daily", "count": {"members": 500}},
                ]
            },
        )
        async with api:
            newsletters = await api.get_newsletters()
        assert len(newsletters) == 2
        assert newsletters[0]["name"] == "Weekly"


# -----------------------------------------------------------------------------
# Email Stats
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_latest_email(api: GhostAdminAPI):
    """Test getting latest email stats."""
    with aioresponses() as m:
        posts_pattern = re.compile(rf"^{re.escape(API_URL)}/ghost/api/admin/posts/\?.*$")
        m.get(
            posts_pattern,
            payload={
                "posts": [
                    {
                        "title": "Newsletter #1",
                        "slug": "newsletter-1",
                        "published_at": "2026-01-15T10:00:00Z",
                        "email": {
                            "email_count": 1000,
                            "delivered_count": 980,
                            "opened_count": 450,
                            "failed_count": 20,
                            "subject": "Newsletter #1",
                            "submitted_at": "2026-01-15T10:00:00Z",
                        },
                        "count": {"clicks": 120},
                    }
                ]
            },
        )
        async with api:
            email = await api.get_latest_email()
        assert email["title"] == "Newsletter #1"
        assert email["email_count"] == 1000
        assert email["opened_count"] == 450
        assert email["open_rate"] == 45
        assert email["click_rate"] == 12


@pytest.mark.asyncio
async def test_get_latest_email_no_clicks(api: GhostAdminAPI):
    """Test email stats with no click data."""
    with aioresponses() as m:
        posts_pattern = re.compile(rf"^{re.escape(API_URL)}/ghost/api/admin/posts/\?.*$")
        m.get(
            posts_pattern,
            payload={
                "posts": [
                    {
                        "title": "Post",
                        "slug": "post",
                        "email": {"email_count": 100, "opened_count": 50},
                        "count": {},
                    }
                ]
            },
        )
        async with api:
            email = await api.get_latest_email()
        assert email["clicked_count"] == 0
        assert email["click_rate"] == 0


@pytest.mark.asyncio
async def test_get_latest_email_zero_sent(api: GhostAdminAPI):
    """Test email stats with zero emails sent."""
    with aioresponses() as m:
        posts_pattern = re.compile(rf"^{re.escape(API_URL)}/ghost/api/admin/posts/\?.*$")
        m.get(
            posts_pattern,
            payload={
                "posts": [
                    {
                        "title": "Post",
                        "slug": "post",
                        "email": {"email_count": 0, "opened_count": 0},
                    }
                ]
            },
        )
        async with api:
            email = await api.get_latest_email()
        assert email["open_rate"] == 0
        assert email["click_rate"] == 0


@pytest.mark.asyncio
async def test_get_latest_email_none(api: GhostAdminAPI):
    """Test getting latest email when none exist."""
    with aioresponses() as m:
        posts_pattern = re.compile(rf"^{re.escape(API_URL)}/ghost/api/admin/posts/\?.*$")
        m.get(posts_pattern, payload={"posts": [{"title": "Post", "slug": "post"}]})
        async with api:
            email = await api.get_latest_email()
        assert email is None


# -----------------------------------------------------------------------------
# Comments
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_comments_count(api: GhostAdminAPI):
    """Test getting comments count."""
    with aioresponses() as m:
        comments_pattern = re.compile(rf"^{re.escape(API_URL)}/ghost/api/admin/comments/\?.*$")
        m.get(
            comments_pattern,
            payload={"comments": [], "meta": {"pagination": {"total": 156}}},
        )
        async with api:
            count = await api.get_comments_count()
        assert count == 156


# -----------------------------------------------------------------------------
# Tiers
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_tiers(api: GhostAdminAPI):
    """Test getting tiers."""
    with aioresponses() as m:
        m.get(
            f"{API_URL}/ghost/api/admin/tiers/",
            payload={
                "tiers": [
                    {"name": "Free", "type": "free"},
                    {"name": "Premium", "type": "paid", "monthly_price": 500},
                ]
            },
        )
        async with api:
            tiers = await api.get_tiers()
        assert len(tiers) == 2
        assert tiers[1]["name"] == "Premium"


# -----------------------------------------------------------------------------
# ActivityPub
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_activitypub_stats(api: GhostAdminAPI):
    """Test getting ActivityPub stats."""
    with aioresponses() as m:
        m.get(
            f"{API_URL}/.ghost/activitypub/followers/index",
            payload={"totalItems": 250},
        )
        m.get(
            f"{API_URL}/.ghost/activitypub/following/index",
            payload={"totalItems": 50},
        )
        async with api:
            stats = await api.get_activitypub_stats()
        assert stats["followers"] == 250
        assert stats["following"] == 50


@pytest.mark.asyncio
async def test_get_activitypub_stats_not_available(api: GhostAdminAPI):
    """Test ActivityPub stats when not available."""
    with aioresponses() as m:
        m.get(f"{API_URL}/.ghost/activitypub/followers/index", status=404)
        m.get(f"{API_URL}/.ghost/activitypub/following/index", status=404)
        async with api:
            stats = await api.get_activitypub_stats()
        assert stats["followers"] == 0
        assert stats["following"] == 0


@pytest.mark.asyncio
async def test_get_activitypub_stats_exception(api: GhostAdminAPI):
    """Test ActivityPub stats when request raises exception."""
    with aioresponses() as m:
        m.get(f"{API_URL}/.ghost/activitypub/followers/index", exception=ClientError())
        m.get(f"{API_URL}/.ghost/activitypub/following/index", exception=ClientError())
        async with api:
            stats = await api.get_activitypub_stats()
        assert stats["followers"] == 0
        assert stats["following"] == 0


# -----------------------------------------------------------------------------
# Webhooks
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_webhook(api: GhostAdminAPI):
    """Test creating a webhook."""
    with aioresponses() as m:
        m.post(
            f"{API_URL}/ghost/api/admin/webhooks/",
            payload={
                "webhooks": [
                    {"id": "wh123", "event": "member.added", "target_url": "https://example.com/hook"}
                ]
            },
        )
        async with api:
            webhook = await api.create_webhook("member.added", "https://example.com/hook")
        assert webhook["id"] == "wh123"
        assert webhook["event"] == "member.added"


@pytest.mark.asyncio
async def test_delete_webhook(api: GhostAdminAPI):
    """Test deleting a webhook."""
    with aioresponses() as m:
        m.delete(f"{API_URL}/ghost/api/admin/webhooks/wh123/", payload={})
        async with api:
            await api.delete_webhook("wh123")
        # No exception means success


# -----------------------------------------------------------------------------
# Error Handling
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_error_401(api: GhostAdminAPI):
    """Test 401 authentication error."""
    with aioresponses() as m:
        m.get(f"{API_URL}/ghost/api/admin/site/", status=401)
        async with api:
            with pytest.raises(GhostAuthError, match="Authentication failed"):
                await api.get_site()


@pytest.mark.asyncio
async def test_error_404(api: GhostAdminAPI):
    """Test 404 not found error."""
    with aioresponses() as m:
        m.get(f"{API_URL}/ghost/api/admin/site/", status=404)
        async with api:
            with pytest.raises(GhostNotFoundError, match="not found"):
                await api.get_site()


@pytest.mark.asyncio
async def test_error_422(api: GhostAdminAPI):
    """Test 422 validation error."""
    with aioresponses() as m:
        m.post(
            f"{API_URL}/ghost/api/admin/webhooks/",
            status=422,
            payload={"errors": [{"message": "Invalid target URL"}]},
        )
        async with api:
            with pytest.raises(GhostValidationError, match="Invalid target URL"):
                await api.create_webhook("member.added", "bad-url")


@pytest.mark.asyncio
async def test_error_500(api: GhostAdminAPI):
    """Test 500 server error."""
    with aioresponses() as m:
        m.get(f"{API_URL}/ghost/api/admin/site/", status=500, body="Internal error")
        async with api:
            with pytest.raises(GhostError, match="API error 500"):
                await api.get_site()


@pytest.mark.asyncio
async def test_connection_error(api: GhostAdminAPI):
    """Test connection error handling."""
    with aioresponses() as m:
        m.get(f"{API_URL}/ghost/api/admin/site/", exception=ClientError("Connection failed"))
        async with api:
            with pytest.raises(GhostConnectionError, match="Connection failed"):
                await api.get_site()


# -----------------------------------------------------------------------------
# Session Management
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_external_session():
    """Test using an external session."""
    import aiohttp

    async with aiohttp.ClientSession() as session:
        api = GhostAdminAPI(api_url=API_URL, admin_api_key=API_KEY, session=session)
        assert api._session is session
        assert api._owns_session is False
        # Session should not be closed by the API
        await api.close()
        assert not session.closed


@pytest.mark.asyncio
async def test_context_manager(api: GhostAdminAPI):
    """Test async context manager."""
    with aioresponses() as m:
        m.get(f"{API_URL}/ghost/api/admin/site/", payload={"site": {"title": "Test"}})
        async with api:
            await api.get_site()
        # Session should be closed after context manager exits
        assert api._session is None or api._session.closed
