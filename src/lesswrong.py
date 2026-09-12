"""LessWrong GraphQL API client for posting comments.

Authentication:
    1. Log into LessWrong in your browser
    2. Open DevTools → Network tab
    3. Make any action (upvote, comment)
    4. Find the request to /graphql
    5. Copy the Authorization header value
    6. Paste it into your .env as LESSWRONG_AUTH_TOKEN

The token is long-lived (~5 years) so you only need to do this once.
"""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)

LW_GRAPHQL_URL = "https://www.lesswrong.com/graphql"

# The createComment mutation — discovered via GraphiQL introspection.
# LessWrong uses Vulcan's auto-generated CRUD mutations.
# The comment body uses a "contents" field with a "originalContents" sub-object
# that takes markdown via { data: "...", type: "markdown" }.
CREATE_COMMENT_MUTATION = """
mutation CreateComment($data: CreateCommentDataInput!) {
  createComment(data: $data) {
    data {
      _id
      postId
      contents {
        html
      }
    }
  }
}
"""


async def post_comment(
    auth_token: str,
    *,
    post_id: str,
    body: str,
    parent_comment_id: str | None = None,
) -> bool:
    """Post a comment to a LessWrong post. Returns True on success."""
    variables: dict = {
        "data": {
            "postId": post_id,
            "contents": {
                "originalContents": {
                    "data": body,
                    "type": "markdown",
                }
            },
        }
    }

    if parent_comment_id:
        variables["data"]["parentCommentId"] = parent_comment_id

    headers = {
        "Content-Type": "application/json",
        "Authorization": auth_token,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                LW_GRAPHQL_URL,
                json={"query": CREATE_COMMENT_MUTATION, "variables": variables},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

            if "errors" in data:
                log.error("LessWrong API errors: %s", data["errors"])
                return False

            comment_id = data.get("data", {}).get("createComment", {}).get("data", {}).get("_id")
            log.info("Posted comment %s to post %s", comment_id, post_id)
            return True

    except Exception as e:
        log.error("Failed to post comment to LessWrong: %s", e)
        return False


async def get_post_id_from_url(url: str) -> str | None:
    """Extract a LessWrong post's internal _id from its URL via the GraphQL API."""
    # LessWrong URLs look like: https://www.lesswrong.com/posts/ABC123/post-slug
    parts = url.rstrip("/").split("/")
    try:
        posts_idx = parts.index("posts")
        slug_or_id = parts[posts_idx + 1]
    except (ValueError, IndexError):
        log.error("Could not parse post ID from URL: %s", url)
        return None

    query = """
    query GetPost($id: String) {
      post(input: { selector: { _id: $id } }) {
        result {
          _id
          title
        }
      }
    }
    """

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                LW_GRAPHQL_URL,
                json={"query": query, "variables": {"id": slug_or_id}},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            result = data.get("data", {}).get("post", {}).get("result")
            if result:
                return result["_id"]
    except Exception as e:
        log.error("Failed to fetch post ID: %s", e)

    return None

