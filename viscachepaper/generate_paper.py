#!/usr/bin/env python3
"""
generate_paper.py — DEPRECATED

This reportlab-based PDF generator has been removed.
Paper generation is moving to LaTeX. See viscachepaper/sections/*.md
for the current WIP content (combined by CI into paper-combined.md).
"""

import sys

def main():
    print("generate_paper.py is deprecated. Use LaTeX for PDF generation.")
    print("Paper content lives in viscachepaper/sections/*.md")
    sys.exit(0)

if __name__ == "__main__":
    main()
