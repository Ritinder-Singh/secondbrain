"""
GitHub connector.
Ingests repos (file-level, code-chunked), issues, and PRs.
Requires GITHUB_TOKEN + GITHUB_USERNAME in .env.
"""
from pathlib import Path

from github import Github, GithubException
from config.settings import settings

# File extensions to ingest from repos
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".go", ".rs", ".java", ".cpp", ".c", ".h",
    ".md", ".txt", ".yaml", ".yml", ".toml", ".json",
}

# Directories to skip
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", "coverage",
}


def _gh_client() -> Github:
    if not settings.GITHUB_TOKEN:
        raise ValueError("GITHUB_TOKEN not set in .env")
    return Github(settings.GITHUB_TOKEN)


def ingest_repo(
    repo_name: str,
    branch: str = None,
    include_issues: bool = True,
    include_prs: bool = True,
) -> dict:
    """
    Ingest a single GitHub repo into the knowledge base.

    Args:
        repo_name: "owner/repo" or just "repo" (uses GITHUB_USERNAME as owner)
        branch: Branch to ingest (defaults to repo default branch)
        include_issues: Also ingest open issues
        include_prs: Also ingest open PRs

    Returns:
        Summary dict with counts
    """
    from ingestion.pipeline import ingest_parsed

    gh = _gh_client()

    if "/" not in repo_name:
        repo_name = f"{settings.GITHUB_USERNAME}/{repo_name}"

    print(f"\n[GitHub] Ingesting {repo_name}...")
    repo = gh.get_repo(repo_name)
    branch = branch or repo.default_branch

    files_ingested = 0
    issues_ingested = 0
    prs_ingested = 0

    # ── Ingest source files ────────────────────────────────────────────────
    print(f"  Fetching file tree from branch '{branch}'...")
    try:
        tree = repo.get_git_tree(branch, recursive=True).tree
    except GithubException as e:
        print(f"  [warn] Could not fetch tree: {e}")
        tree = []

    for item in tree:
        if item.type != "blob":
            continue
        path = Path(item.path)

        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in CODE_EXTENSIONS:
            continue

        try:
            file_content = repo.get_contents(item.path, ref=branch)
            if file_content.size > 500_000:  # skip files > 500KB
                continue
            text = file_content.decoded_content.decode("utf-8", errors="ignore")
            if not text.strip():
                continue

            lang = path.suffix.lstrip(".") or "text"
            source_url = f"https://github.com/{repo_name}/blob/{branch}/{item.path}"

            ingest_parsed(
                {
                    "title":       f"{repo.name}/{item.path}",
                    "text":        text,
                    "source_type": "github",
                    "source_url":  source_url,
                    "file_path":   item.path,
                    "metadata": {
                        "repo":     repo_name,
                        "branch":   branch,
                        "language": lang,
                        "size":     file_content.size,
                    },
                },
                para_category="Resources",
                tags=["github", repo.name, lang],
            )
            files_ingested += 1
        except Exception as e:
            print(f"  [warn] Skipped {item.path}: {e}")

    # ── Ingest issues ──────────────────────────────────────────────────────
    if include_issues:
        print(f"  Fetching issues...")
        for issue in repo.get_issues(state="open"):
            if issue.pull_request:
                continue
            try:
                body = issue.body or "(no description)"
                text = f"# Issue #{issue.number}: {issue.title}\n\n{body}"
                ingest_parsed(
                    {
                        "title":       f"{repo.name} Issue #{issue.number}: {issue.title}",
                        "text":        text,
                        "source_type": "github",
                        "source_url":  issue.html_url,
                        "file_path":   "",
                        "metadata": {
                            "repo":   repo_name,
                            "type":   "issue",
                            "number": issue.number,
                            "state":  issue.state,
                        },
                    },
                    para_category="Resources",
                    tags=["github", "issue", repo.name],
                )
                issues_ingested += 1
            except Exception as e:
                print(f"  [warn] Skipped issue #{issue.number}: {e}")

    # ── Ingest PRs ─────────────────────────────────────────────────────────
    if include_prs:
        print(f"  Fetching PRs...")
        for pr in repo.get_pulls(state="open"):
            try:
                body = pr.body or "(no description)"
                text = f"# PR #{pr.number}: {pr.title}\n\n{body}"
                ingest_parsed(
                    {
                        "title":       f"{repo.name} PR #{pr.number}: {pr.title}",
                        "text":        text,
                        "source_type": "github",
                        "source_url":  pr.html_url,
                        "file_path":   "",
                        "metadata": {
                            "repo":   repo_name,
                            "type":   "pr",
                            "number": pr.number,
                            "state":  pr.state,
                        },
                    },
                    para_category="Resources",
                    tags=["github", "pr", repo.name],
                )
                prs_ingested += 1
            except Exception as e:
                print(f"  [warn] Skipped PR #{pr.number}: {e}")

    print(f"  ✓ {repo_name}: {files_ingested} files, {issues_ingested} issues, {prs_ingested} PRs\n")
    return {
        "repo":             repo_name,
        "files_ingested":   files_ingested,
        "issues_ingested":  issues_ingested,
        "prs_ingested":     prs_ingested,
    }


def ingest_all_repos(include_issues: bool = True, include_prs: bool = True) -> list[dict]:
    """Ingest all repos owned by GITHUB_USERNAME (non-fork only)."""
    gh = _gh_client()
    user = gh.get_user(settings.GITHUB_USERNAME)
    results = []
    for repo in user.get_repos(type="owner"):
        if repo.fork:
            continue
        result = ingest_repo(
            repo.full_name,
            include_issues=include_issues,
            include_prs=include_prs,
        )
        results.append(result)
    return results
