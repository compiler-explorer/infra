import json
import urllib.parse
import urllib.request
from typing import List

OWNER_REPO = "compiler-explorer/compiler-explorer"
USER_AGENT = "CE Live Now Notification Bot"

NOW_LIVE_LABEL = "live"
NOW_LIVE_MESSAGE = "This is now live"


def post(entity: str, token: str, query: dict = None, dry_run=False) -> dict:
    try:
        if query is None:
            query = {}
        path = entity
        querystring = json.dumps(query).encode()
        if dry_run:
            print(f"[DRY RUN] Would post to {path} with data: {query}")
            return {}
        print(f"Posting {path}")
        req = urllib.request.Request(
            f"https://api.github.com/{path}",
            data=querystring,
            headers={
                "User-Agent": USER_AGENT,
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        result = urllib.request.urlopen(req)
        # It's ok not to check for error codes here. We'll throw either way
        return json.loads(result.read())
    except Exception as e:
        raise RuntimeError(f"Error while posting {entity}") from e


def get(entity: str, token: str, query: dict = None) -> dict:
    try:
        if query is None:
            query = {}
        path = entity
        if query:
            querystring = urllib.parse.urlencode(query)
            path += f"?{querystring}"
        print(f"Getting {path}")
        req = urllib.request.Request(
            f"https://api.github.com/{path}",
            None,
            {
                "User-Agent": USER_AGENT,
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        result = urllib.request.urlopen(req)
        # It's ok not to check for error codes here. We'll throw either way
        return json.loads(result.read())
    except Exception as e:
        raise RuntimeError(f"Error while getting {entity}") from e


def paginated_get(entity: str, token: str, query: dict = None) -> List[dict]:
    if query is None:
        query = {}
    result: List[dict] = []
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


def list_inbetween_commits(end_commit: str, new_commit: str, token: str) -> List[dict]:
    commits = get(f"repos/{OWNER_REPO}/compare/{end_commit}...{new_commit}", token=token)
    return commits["commits"]


def get_linked_pr(commit: str, token: str) -> dict:
    """Returns a list whose items are the PR associated to each commit"""
    pr = get(f"repos/{OWNER_REPO}/commits/{commit}/pulls", token=token)
    return pr[0] if len(pr) == 1 else {}


def get_linked_issues(pr: str, token: str, dry_run=False):
    query = (
        """
query {
  repository(owner: "compiler-explorer", name: "compiler-explorer") {
    pullRequest(number: %s) {
      closingIssuesReferences(first: 10) {
        edges {
          node {
            labels(first: 10) {
              edges {
                node {
                  name
                }
              }
            }
            number
          }
        }
      }
    }
  }
}
    """
        % pr
    )
    return post("graphql", token, {"query": query}, dry_run=dry_run)


def get_issue_comments(issue: str, token: str) -> List[dict]:
    return paginated_get(f"repos/{OWNER_REPO}/issues/{issue}/comments", token)


def comment_on_issue(issue: str, msg: str, token: str, dry_run=False):
    result = post(f"repos/{OWNER_REPO}/issues/{issue}/comments", token, {"body": msg}, dry_run=dry_run)
    return result


def set_issue_labels(issue: str, labels: List[str], token: str, dry_run=False):
    post(f"repos/{OWNER_REPO}/issues/{issue}/labels", token, {"labels": labels}, dry_run=dry_run)


def should_send_comment_to_issue(issue: str, token: str):
    """Only send a comment to the issue if nothing like the live message is there already"""
    comments = get_issue_comments(issue, token)
    return all([NOW_LIVE_MESSAGE not in comment["body"] for comment in comments])


def send_live_message(issue: str, token: str, dry_run=False):
    if dry_run:
        print(f"[DRY RUN] Would add '{NOW_LIVE_LABEL}' label to issue #{issue}")
        if should_send_comment_to_issue(issue, token):
            print(f"[DRY RUN] Would comment '{NOW_LIVE_MESSAGE}' on issue #{issue}")
        else:
            print(f"[DRY RUN] Would skip commenting on issue #{issue} (already has live message)")
    else:
        set_issue_labels(issue, [NOW_LIVE_LABEL], token, dry_run=dry_run)
        if should_send_comment_to_issue(issue, token):
            comment_on_issue(issue, NOW_LIVE_MESSAGE, token, dry_run=dry_run)


def get_edges(issue: dict) -> List[dict]:
    return issue["data"]["repository"]["pullRequest"]["closingIssuesReferences"]["edges"]


def should_process_pr(pr_labels):
    """Only process PRs that do not have the live label already set"""
    return all([label["name"] != NOW_LIVE_LABEL for label in pr_labels])


def should_notify_issue(edge) -> bool:
    """We want to notify the issue if:
    - there's one linked ("number" in edge) AND
    - either:
      - the linked issue has no labels ("labels" not in edge["node"]) OR
      - the NOW_LIVE_LABEL label is not among its labels"""
    return "number" in edge and (
        ("labels" not in edge) or all([label["node"]["name"] != NOW_LIVE_LABEL for label in edge["labels"]["edges"]])
    )


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
            send_live_message(pr_id, token, dry_run=dry_run)

            linked_issues = get_linked_issues(pr_id, token, dry_run=False)
            issues_edges = get_edges(linked_issues)
            if len(issues_edges) == 1 and "node" in issues_edges[0]:
                edge = issues_edges[0]["node"]
                if should_notify_issue(edge):
                    if dry_run:
                        print(f"[DRY RUN] Would notify issue #{edge['number']}")
                    else:
                        print(f"Notifying issue {edge['number']}")
                    send_live_message(edge["number"], token, dry_run=dry_run)
                else:
                    if dry_run:
                        print(f"[DRY RUN] Would skip notifying issue #{edge['number']} (already has live label)")
                    else:
                        print(f"Skipping notifying issue {edge['number']}")
            else:
                if dry_run:
                    print(f"[DRY RUN] No issues to notify for PR #{pr_id}")
                else:
                    print(f"No issues in which to notify for PR {pr_id}")
        else:
            if dry_run:
                print(f"[DRY RUN] Would skip notifying PR #{pr_id} (already has live label)")
            else:
                print(f"Skipping notifying PR {pr_id}")
