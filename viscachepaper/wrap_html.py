#!/usr/bin/env python3
"""Wrap a markdown file in minimal HTML with client-side rendering via marked.js."""

import html
import sys


def wrap(md_path, html_path):
    with open(md_path, "r") as f:
        md_content = f.read()

    # Escape for embedding in a <script> tag
    escaped = md_content.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")

    out = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Multilevel Visibility Hash Filter — Paper Sketch</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.5.1/github-markdown-light.min.css">
<style>
  body {{ max-width: 980px; margin: 0 auto; padding: 20px 40px; }}
  .markdown-body {{ font-size: 16px; }}
  .markdown-body pre {{ background: #f6f8fa; }}
  .markdown-body code {{ font-size: 85%; }}
  @media (max-width: 767px) {{ body {{ padding: 15px; }} }}
</style>
</head>
<body>
<article class="markdown-body" id="content"></article>
<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.1/marked.min.js"></script>
<script>
const md = `{escaped}`;
document.getElementById('content').innerHTML = marked.parse(md);
</script>
</body>
</html>
"""

    with open(html_path, "w") as f:
        f.write(out)

    print(f"Wrapped: {md_path} -> {html_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} input.md output.html", file=sys.stderr)
        sys.exit(1)
    wrap(sys.argv[1], sys.argv[2])
