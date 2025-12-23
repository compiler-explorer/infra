from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

LOGGER = logging.getLogger(__name__)

OWNER_REPO = "compiler-explorer/compiler-explorer"
USER_AGENT = "CE Live Now Notification Bot"

NOW_LIVE_LABEL = "live"
NOW_LIVE_MESSAGE = "This is now live"


def post(entity: str, token: str, query: dict | None = None, dry_run=False) -> dict:
    try:
        if query is None:
            query = {}
        path = entity
        querystring = json.dumps(query).encode()
        if dry_run:
            print(f"[DRY RUN] Would post to {path} with data: {query}")
            return {}
        LOGGER.debug(f"Posting {path}")
        req = urllib.request.Request(
            f"https://api.github.com/{path}",
            data=querystring,
            headers={
                "User-Agent": USER_AGENT,
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        result = urllib.request.urlopen(req)
        # It's ok not to check for error codes here. We'll throw either way
        return json.loads(result.read())
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Error while posting {entity}") from e


def get(entity: str, token: str, query: dict | None = None) -> dict:
    try:
        if query is None:
            query = {}
        path = entity
        if query:
            querystring = urllib.parse.urlencode(query)
            path += f"?{querystring}"
        LOGGER.debug(f"Getting {path}")
        req = urllib.request.Request(
            f"https://api.github.com/{path}",
            None,
            {
                "User-Agent": USER_AGENT,
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        result = urllib.request.urlopen(req)
        # It's ok not to check for error codes here. We'll throw either way
        return json.loads(result.read())
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Error while getting {entity}") from e


def paginated_get(entity: str, token: str, query: dict | None = None) -> list[dict]:
    if query is None:
        query = {}
    result: list[dict] = []
    results_per_page = 50
    query["page"] = 1
    query["per_page"] = results_per_page
    while True:
        current_page_results = get(entity, token, query)
        result.extend(current_page_results)
        if len(current_page_results) == results_per_page:
            query["page"] += 1
        else:
            break
    return result


def list_inbetween_commits(end_commit: str, new_commit: str, token: str) -> list[dict]:
    commits = get(f"repos/{OWNER_REPO}/compare/{end_commit}...{new_commit}", token=token)
    return commits["commits"]


def get_linked_pr(commit: str, token: str) -> dict:
    """Returns a list whose items are the PR associated to each commit"""
    pr = get(f"repos/{OWNER_REPO}/commits/{commit}/pulls", token=token)
    return pr[0] if len(pr) == 1 else {}


def get_linked_issues(pr: str, token: str, dry_run=False):
    query = f"""
query {{
  repository(owner: "compiler-explorer", name: "compiler-explorer") {{
    pullRequest(number: {pr}) {{
      closingIssuesReferences(first: 10) {{
        edges {{
          node {{
            repository {{
              owner {{
                login
              }}
              name
            }}
            labels(first: 10) {{
              edges {{
                node {{
                  name
                }}
              }}
            }}
            number
          }}
        }}
      }}
    }}
  }}
}}
    """
    return post("graphql", token, {"query": query}, dry_run=dry_run)


def get_issue_comments(issue: str, repo: str, token: str) -> list[dict]:
    return paginated_get(f"repos/{repo}/issues/{issue}/comments", token)


def comment_on_issue(issue: str, repo: str, msg: str, token: str, dry_run=False):
    result = post(f"repos/{repo}/issues/{issue}/comments", token, {"body": msg}, dry_run=dry_run)
    return result


def set_issue_labels(issue: str, repo: str, labels: list[str], token: str, dry_run=False):
    post(f"repos/{repo}/issues/{issue}/labels", token, {"labels": labels}, dry_run=dry_run)


def should_send_comment_to_issue(issue: str, repo: str, token: str):
    """Only send a comment to the issue if nothing like the live message is there already"""
    comments = get_issue_comments(issue, repo, token)
    return all([NOW_LIVE_MESSAGE not in comment["body"] for comment in comments])


def send_live_message(issue: str, repo: str, token: str, dry_run=False):
    if dry_run:
        print(f"[DRY RUN] Would add '{NOW_LIVE_LABEL}' label to {repo}#{issue}")
        if should_send_comment_to_issue(issue, repo, token):
            print(f"[DRY RUN] Would comment '{NOW_LIVE_MESSAGE}' on {repo}#{issue}")
        else:
            LOGGER.debug(f"[DRY RUN] Would skip commenting on {repo}#{issue} (already has live message)")
    else:
        set_issue_labels(issue, repo, [NOW_LIVE_LABEL], token, dry_run=dry_run)
        if should_send_comment_to_issue(issue, repo, token):
            comment_on_issue(issue, repo, NOW_LIVE_MESSAGE, token, dry_run=dry_run)


def get_edges(issue: dict) -> list[dict]:
    return issue["data"]["repository"]["pullRequest"]["closingIssuesReferences"]["edges"]


def should_process_pr(pr_labels):
    """Only process PRs that do not have the live label already set"""
    return all([label["name"] != NOW_LIVE_LABEL for label in pr_labels])


def should_notify_issue(edge) -> bool:
    """We want to notify the issue if:
    - there's one linked ("number" in edge) AND
    - it's in a compiler-explorer repository AND
    - either:
      - the linked issue has no labels ("labels" not in edge) OR
      - the NOW_LIVE_LABEL label is not among its labels"""
    if "number" not in edge:
        return False

    # Only notify for compiler-explorer repositories
    repo_info = edge.get("repository", {})
    owner = repo_info.get("owner", {}).get("login", "")
    if owner != "compiler-explorer":
        return False

    # Check if issue already has live label
    return ("labels" not in edge) or all([label["node"]["name"] != NOW_LIVE_LABEL for label in edge["labels"]["edges"]])


def handle_notify(base, new, token, dry_run=False):
    print(f"Checking for live notifications from {base} to {new}")

    commits = list_inbetween_commits(base, new, token)
    prs = [get_linked_pr(commit["sha"], token) for commit in commits]

    for pr_data in prs:
        if not pr_data:
            continue
        pr_id = pr_data["number"]
        if should_process_pr(pr_data["labels"]):
            if dry_run:
                print(f"[DRY RUN] Would notify PR #{pr_id}")
            else:
                print(f"Notifying PR {pr_id}")
            send_live_message(pr_id, OWNER_REPO, token, dry_run=dry_run)

            linked_issues = get_linked_issues(pr_id, token, dry_run=False)
            issues_edges = get_edges(linked_issues)
            for edge_wrapper in issues_edges:
                if "node" in edge_wrapper:
                    edge = edge_wrapper["node"]
                    if should_notify_issue(edge):
                        repo_info = edge.get("repository", {})
                        owner = repo_info.get("owner", {}).get("login", "")
                        repo_name = repo_info.get("name", "")
                        full_repo = f"{owner}/{repo_name}"

                        if dry_run:
                            print(f"[DRY RUN] Would notify issue {full_repo}#{edge['number']}")
                        else:
                            print(f"Notifying issue {full_repo}#{edge['number']}")
                        send_live_message(edge["number"], full_repo, token, dry_run=dry_run)
                    else:
                        repo_info = edge.get("repository", {})
                        owner = repo_info.get("owner", {}).get("login", "unknown")
                        repo_name = repo_info.get("name", "unknown")

                        if dry_run:
                            LOGGER.debug(
                                f"[DRY RUN] Would skip notifying issue {owner}/{repo_name}#{edge['number']} (already has live label or external repo)"
                            )
                        else:
                            LOGGER.debug(f"Skipping notifying issue {edge['number']}")
            if not issues_edges:
                if dry_run:
                    LOGGER.debug(f"[DRY RUN] No issues to notify for PR #{pr_id}")
                else:
                    LOGGER.debug(f"No issues in which to notify for PR {pr_id}")
        else:
            if dry_run:
                LOGGER.debug(f"[DRY RUN] Would skip notifying PR #{pr_id} (already has live label)")
            else:
                LOGGER.debug(f"Skipping notifying PR {pr_id}")
