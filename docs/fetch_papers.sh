#!/usr/bin/env bash
# fetch_papers.sh — Download freely available reference papers.
#
# Usage:
#     ./docs/fetch_papers.sh
#
# Downloads arXiv preprints, JCGT open-access papers, and author-hosted
# preprints. Does NOT download copyrighted papers from ACM/Eurographics.
# Downloaded PDFs go into docs/references/ (gitignored).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REF_DIR="$SCRIPT_DIR/references"
mkdir -p "$REF_DIR"

download() {
    local name="$1"
    local url="$2"
    local dest="$REF_DIR/$name"

    if [ -f "$dest" ]; then
        echo "  SKIP  $name (already exists)"
        return 0
    fi

    printf "  GET   %-50s " "$name"
    if curl -fSL --progress-bar -o "$dest" "$url" 2>/dev/null; then
        local size
        size=$(du -h "$dest" | cut -f1)
        echo "OK ($size)"
    else
        echo "FAILED"
        rm -f "$dest"
    fi
}

echo "Fetching freely available reference papers into docs/references/"
echo ""

# ── arXiv preprints ──────────────────────────────────────────────────────
echo "arXiv preprints:"

download "Ouyang2021_ReSTIR_GI.pdf" \
    "https://arxiv.org/pdf/2108.05263.pdf"

download "Lin2022_GRIS_ReSTIR_PT.pdf" \
    "https://arxiv.org/pdf/2211.09648.pdf"

download "Muller2022_InstantNGP.pdf" \
    "https://arxiv.org/pdf/2201.05989.pdf"

download "Zhang2024_AreaReSTIR.pdf" \
    "https://arxiv.org/pdf/2401.02293.pdf"

download "Stotko2025_MrHash.pdf" \
    "https://arxiv.org/pdf/2511.21459.pdf"

download "Binder2019_MassivelyParallelPathSpaceFiltering.pdf" \
    "https://arxiv.org/pdf/1902.05942.pdf"

download "Boksansky2025_NeuralVisCache.pdf" \
    "https://arxiv.org/pdf/2506.05930.pdf"

echo ""

# ── JCGT (open access journal) ──────────────────────────────────────────
echo "JCGT open access:"

download "Jarzynski2020_HashFunctions.pdf" \
    "https://jcgt.org/published/0009/03/02/paper.pdf"

echo ""

# ── Author-hosted preprints ─────────────────────────────────────────────
echo "Author preprints:"

download "Bitterli2020_ReSTIR_DI.pdf" \
    "https://benedikt-bitterli.me/restir/bitterli20restir.pdf"

download "Popov2013_AdaptiveQuantVisCache.pdf" \
    "https://cg.ivd.kit.edu/publications/p2013/AQVC_Popov_2013/AQVC_Popov_2013.pdf"

download "Teschner2003_SpatialHashing.pdf" \
    "https://matthias-research.github.io/pages/publications/tetraederCollision.pdf"

download "SzirmayKalos2005_GoWithTheWinners.pdf" \
    "https://dspace5.zcu.cz/bitstream/11025/1454/1/Szirmay-Kalos.pdf"

echo ""

# ── NVIDIA Research hosted ──────────────────────────────────────────────
echo "NVIDIA Research:"

download "Liu2025_ReservoirSplatting.pdf" \
    "https://research.nvidia.com/labs/rtr/publication/liu2025splatting/liu2025splatting_paper.pdf"

echo ""

# ── Summary ──────────────────────────────────────────────────────────────
echo "=== Downloaded ==="
count=$(ls "$REF_DIR"/*.pdf 2>/dev/null | wc -l)
echo "$count papers in $REF_DIR/"
ls -1 "$REF_DIR"/*.pdf 2>/dev/null | while read -r f; do
    printf "  %-55s %s\n" "$(basename "$f")" "$(du -h "$f" | cut -f1)"
done

echo ""
echo "=== Remaining (obtain from publisher or author page) ==="
for paper in \
    "Guo2020_NEEpp.pdf                — Wiley (CGF/Pacific Graphics)" \
    "Ulbrich2013_ProgressiveVisCache.pdf — Eurographics DL" \
    "Ward1994_AdaptiveShadowTesting.pdf — Springer (try radiance-online.org HTML)" \
    "Keller2014_PathSpaceSimilarity.pdf  — NVIDIA Research / ResearchGate" \
    ; do
    echo "  $paper"
done
echo ""
echo "Place manually obtained PDFs in: $REF_DIR/"
