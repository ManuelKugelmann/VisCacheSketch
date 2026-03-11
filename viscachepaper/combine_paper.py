#!/usr/bin/env python3
"""Combine per-section markdown files into a single paper document."""

import os
import sys
import subprocess
import datetime

SECTIONS_DIR = os.path.join(os.path.dirname(__file__), "sections")

# Ordered list of section files to combine
SECTION_FILES = [
    "00-front-matter.md",
    "01-introduction.md",
    "02-related-work.md",
    "03-data-structure.md",
    "04-addressing.md",
    "05-insert.md",
    "06-eviction-and-temporal-decay.md",
    "07-lookup.md",
    "08-control-variate-with-russian-roulette.md",
    "09-restir-integration.md",
    "10-contribution-weighted-revalidation.md",
    "11-cache-free-alternatives.md",
    "12-runtime-statistics.md",
    "13-results.md",
    "14-conclusion.md",
    "references.md",
]


def build_stamp():
    sha = os.environ.get("GITHUB_SHA", "").strip()
    if not sha:
        try:
            sha = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
            ).decode().strip()
        except Exception:
            sha = "unknown"
    else:
        sha = sha[:7]

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Build repo link for commit
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    sha_full = os.environ.get("GITHUB_SHA", "")
    if repo and sha_full:
        sha_link = f"[`{sha}`](https://github.com/{repo}/commit/{sha_full})"
    else:
        sha_link = f"`{sha}`"

    parts = [f"**Built:** {ts} | {sha_link}"]

    # Add PR info if available
    pr_number = ""
    ref = os.environ.get("GITHUB_REF", "")
    if ref.startswith("refs/pull/") and ref.endswith("/merge"):
        pr_number = ref.split("/")[2]
    if pr_number and repo:
        parts.append(f"[PR #{pr_number}](https://github.com/{repo}/pull/{pr_number})")

    # Add branch info
    branch = os.environ.get("GITHUB_HEAD_REF", "").strip()  # PR source branch
    if not branch:
        branch = os.environ.get("GITHUB_REF_NAME", "").strip()
    if not branch:
        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
        except Exception:
            branch = ""
    if branch:
        parts.append(f"branch: `{branch}`")

    return " | ".join(parts)


def combine(output_path):
    parts = []
    for fname in SECTION_FILES:
        path = os.path.join(SECTIONS_DIR, fname)
        if not os.path.exists(path):
            print(f"Warning: {path} not found, skipping", file=sys.stderr)
            continue
        with open(path, "r") as f:
            content = f.read().rstrip()
        parts.append(content)

    combined = "\n\n---\n\n".join(parts)

    # Prepend build stamp
    stamp = build_stamp()
    combined = f"{stamp}\n\n---\n\n{combined}\n"

    with open(output_path, "w") as f:
        f.write(combined)

    lines = combined.count("\n") + 1
    print(f"Combined paper: {output_path} ({lines} lines, {len(SECTION_FILES)} sections)")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "paper-combined.md"
    )
    combine(out)
