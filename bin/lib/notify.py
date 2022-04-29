import urllib.request
import urllib.parse
import json
from typing import List

OWNER_REPO = "compiler-explorer/compiler-explorer"
USER_AGENT = "CE Live Now Notification Bot"


def post(entity: str, token: str, query: dict = None, dry=False) -> dict:
    if query is None:
        query = {}
    path = entity
    querystring = json.dumps(query).encode()
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
    if dry:
        return {}
    result = urllib.request.urlopen(req)
    # It's ok not to check for error codes here. We'll throw either way
    return json.loads(result.read())


def get(entity: str, token: str, query: dict = None) -> dict:
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
    pr = get(f"repos/{OWNER_REPO}/commits/{commit}/pulls", token=token)
    return pr


def get_linked_issues(pr: str, token: str):
    query = """
    query {
        repository(owner: "compiler-explorer", name: "compiler-explorer") {
            pullRequest(number: %s) {
              closingIssuesReferences(first: 10) {
                edges {
                  node {
                    number
                  }
                }
              }
            }
        }
    }
    """ % pr
    return post(f"graphql", token, {"query": query})


def get_issue_comments(issue: str, token: str) -> List[dict]:
    return paginated_get(f"repos/{OWNER_REPO}/issues/{issue}/comments", token)


def comment_on_issue(issue: str, msg: str, token: str):
    result = post(f"repos/{OWNER_REPO}/issues/{issue}/comments", token, {"body": msg}, dry=True)
    return result


def send_live_message(issue: str, token: str):
    comment_on_issue(issue, "This is now live", token=token)


def get_edges(issue: dict) -> List[dict]:
    return issue["data"]["repository"]["pullRequest"]["closingIssuesReferences"]["edges"]


def handle_notify(base, new, token):
    print(f'Notifying from {base} to {new}')

    commits = list_inbetween_commits(base, new, token)

    prs = [get_linked_pr(commit["sha"], token) for commit in commits]
    ids = [pr[0]["number"] for pr in prs]
    linked_issues = [get_linked_issues(pr, token) for pr in ids]
    issues_ids = [get_edges(issue) for issue in linked_issues if len(get_edges(issue)) > 0]

    for edge in issues_ids:
        for node in edge:
            issue = node["node"]["number"]
            comments = get_issue_comments(issue, token)
            if not any(["This is now live" in comment["body"] for comment in comments]):
                send_live_message(issue, token)
            else:
                print(f"Skipping notifying {issue}, it's already been done")
