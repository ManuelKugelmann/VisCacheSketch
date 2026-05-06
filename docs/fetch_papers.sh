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
    "https://graphics.cs.utah.edu/research/projects/gris/sig22_GRIS.pdf"

download "Lin2022_GRIS_ReSTIR_PT_supplemental.pdf" \
    "https://graphics.cs.utah.edu/research/projects/gris/GRIS_supplemental.pdf"

download "Muller2022_InstantNGP.pdf" \
    "https://arxiv.org/pdf/2201.05989.pdf"

download "Zhang2024_AreaReSTIR.pdf" \
    "https://research.nvidia.com/labs/rtr/publication/zhang2024area/zhang2024area.pdf"

download "Lin2026_ReSTIR_PT_Enhanced.pdf" \
    "https://research.nvidia.com/labs/rtr/publication/lin2026restirptenhanced/lin2026restirptenhanced.pdf"

download "Stotko2025_MrHash.pdf" \
    "https://arxiv.org/pdf/2511.21459.pdf"

download "Binder2019_MassivelyParallelPathSpaceFiltering.pdf" \
    "https://arxiv.org/pdf/1902.05942.pdf"

download "Boksansky2025_NeuralVisCache.pdf" \
    "https://arxiv.org/pdf/2506.05930.pdf"

echo ""

# ── GPUOpen / SIGGRAPH archive (open) ───────────────────────────────────
echo "GPUOpen + SIGGRAPH archive:"

download "Boisse2021_WorldSpaceReSTIR.pdf" \
    "https://gpuopen.com/download/publications/SA2021_WorldSpace_ReSTIR.pdf"

download "Boisse2022_GI10_RadianceCaching.pdf" \
    "https://gpuopen.com/download/publications/GPUOpen2022_GI1_0.pdf"

download "Binder2018_JitteredSpatialHashing.pdf" \
    "https://history.siggraph.org/wp-content/uploads/2022/09/2018-Talks-Binder_Fast-Path-Space-Filtering-by-Jittered-Spatial-Hashing.pdf"

download "Zhang2023_WorldSpacePathResampling.pdf" \
    "https://wangningbei.github.io/2023/ReSTIR_files/paper_ReSTIRGI.pdf"

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

download "Ulbrich2013_ProgressiveVisCache.pdf" \
    "https://haukerehfeld.de/publications/ProgressiveVisibilityCaching/ProgressiveVisibilityCaching.pdf"

download "Guo2020_NEEplusplus.pdf" \
    "https://repository.tudelft.nl/file/File_b19b0fe9-d16c-406d-a2cd-32f38507c50f"

echo ""

# ── NVIDIA Research hosted ──────────────────────────────────────────────
echo "NVIDIA Research:"

download "Liu2025_ReservoirSplatting.pdf" \
    "https://research.nvidia.com/labs/rtr/publication/liu2025splatting/liu2025splatting_paper.pdf"

download "Boksansky2021_ReGIR.pdf" \
    "https://cwyman.org/papers/rtg2-manyLightReGIR.pdf"

echo ""

# ── Adjacent literature (literature log additions) ───────────────────────
echo "Adjacent literature (RR, path guiding, radiance caches, denoising):"

download "Vorba2016_ADRRS.pdf" \
    "https://cgg.mff.cuni.cz/~jaroslav/papers/2016-adrrs/2016-vorba-adrrs-paper.pdf"

download "Rath2022_EARS.pdf" \
    "https://graphics.cg.uni-saarland.de/papers/rath-2022-ears.pdf"

download "Muller2021_NRC.pdf" \
    "https://tom94.net/data/publications/mueller21realtime/mueller21realtime.pdf"

download "Muller2017_PracticalPathGuiding.pdf" \
    "https://tom94.net/data/publications/mueller17practical/mueller17practical.pdf"

download "Vevoda2018_BayesianLightSampling.pdf" \
    "https://cgg.mff.cuni.cz/~jaroslav/papers/2018-bayesianlighting/2018-vevoda-bayesianlighting-paper.pdf"

download "Majercik2019_DDGI.pdf" \
    "https://jcgt.org/published/0008/02/01/paper-lowres.pdf"

download "Schied2017_SVGF.pdf" \
    "https://research.nvidia.com/sites/default/files/pubs/2017-07_Spatiotemporal-Variance-Guided-Filtering%3A/svgf_preprint.pdf"

download "Zheng2024_ReSTIR_PG.pdf" \
    "https://cseweb.ucsd.edu/~ravir/zhengsiga.pdf"

# ── GRIS / mutation lineage (algorithmic basis of ReSTIR PT) ─────────────
download "Hedstrom2025_ReSTIR_BDPT.pdf" \
    "https://cwyman.org/papers/tog25_ReSTIR_BDPT.pdf"

# Note: Veach 1997 MLT (Stanford thesis), Kelemen 2002 PSS-MLT (Eurographics),
# Lehtinen 2013 / Kettunen 2015 gradient-domain MLT/BDPT — author-hosted PDFs
# move regularly; left for manual fetch. See docs/REFERENCES.md.

echo ""

# ── Summary ──────────────────────────────────────────────────────────────
echo "=== Downloaded ==="
count=$(ls "$REF_DIR"/*.pdf 2>/dev/null | wc -l)
echo "$count papers in $REF_DIR/"
ls -1 "$REF_DIR"/*.pdf 2>/dev/null | while read -r f; do
    printf "  %-55s %s\n" "$(basename "$f")" "$(du -h "$f" | cut -f1)"
done

echo ""
echo "Note: Ward1994 was converted from HTML and is already committed."
echo "Note: Liu2025 (241 MB) exceeds GitHub 100 MB limit — download only."
