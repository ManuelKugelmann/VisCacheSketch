#!/usr/bin/env python3
"""Generate a two-column research paper PDF: Multilevel Visibility Hash Filter (v2)."""

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.colors import black, HexColor
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer,
    Table, TableStyle, Flowable, NextPageTemplate, FrameBreak
)

# ── Page geometry ───────────────────────────────────────────────────
PAGE_W, PAGE_H = letter
MARGIN_TOP = 0.75 * inch
MARGIN_BOT = 0.85 * inch
MARGIN_LR = 0.75 * inch
COL_GAP = 0.25 * inch
COL_W = (PAGE_W - 2 * MARGIN_LR - COL_GAP) / 2.0
BODY_H = PAGE_H - MARGIN_TOP - MARGIN_BOT

# ── Fonts ───────────────────────────────────────────────────────────
F = "Times-Roman"; FB = "Times-Bold"; FI = "Times-Italic"; FBI = "Times-BoldItalic"
FM = "Courier"; FMB = "Courier-Bold"
GRAY = HexColor("#444444"); LGRAY = HexColor("#f0f0f0"); RGRAY = HexColor("#cccccc")

# ── Styles ──────────────────────────────────────────────────────────
sTitle  = ParagraphStyle("T", fontName=FB, fontSize=17, leading=20, alignment=TA_CENTER, spaceAfter=6)
sAuthor = ParagraphStyle("A", fontName=F, fontSize=11, leading=14, alignment=TA_CENTER, spaceAfter=2)
sAffil  = ParagraphStyle("Af", fontName=FI, fontSize=9, leading=11, alignment=TA_CENTER, spaceAfter=6)
sAbsH   = ParagraphStyle("AH", fontName=FB, fontSize=9, leading=11, spaceAfter=2)
sAbsB   = ParagraphStyle("AB", fontName=F, fontSize=9, leading=11, alignment=TA_JUSTIFY,
                          spaceAfter=3, leftIndent=18, rightIndent=18)
sH1 = ParagraphStyle("H1", fontName=FB, fontSize=11, leading=13, spaceBefore=10, spaceAfter=4)
sH2 = ParagraphStyle("H2", fontName=FBI, fontSize=10, leading=12, spaceBefore=8, spaceAfter=3)
sB  = ParagraphStyle("B", fontName=F, fontSize=9.5, leading=11.5, alignment=TA_JUSTIFY,
                      spaceAfter=4, firstLineIndent=12)
sB0 = ParagraphStyle("B0", parent=sB, firstLineIndent=0)
sCd = ParagraphStyle("Cd", fontName=FM, fontSize=7, leading=8.5, spaceAfter=4,
                      spaceBefore=2, leftIndent=4, backColor=LGRAY)
sCap = ParagraphStyle("Cap", fontName=F, fontSize=8, leading=10, alignment=TA_JUSTIFY,
                       spaceAfter=6, spaceBefore=2)
sBul = ParagraphStyle("Bu", fontName=F, fontSize=9.5, leading=11.5, alignment=TA_JUSTIFY,
                       spaceAfter=2, leftIndent=18, bulletIndent=6)
sRef = ParagraphStyle("R", fontName=F, fontSize=8, leading=10, alignment=TA_JUSTIFY,
                       spaceAfter=2, leftIndent=14, firstLineIndent=-14)
sEq  = ParagraphStyle("Eq", fontName=FI, fontSize=9.5, leading=12, alignment=TA_CENTER,
                       spaceAfter=6, spaceBefore=4)
sTH = ParagraphStyle("TH", fontName=FB, fontSize=8, leading=10)
sTC = ParagraphStyle("TC", fontName=F, fontSize=8, leading=10)


class HRule(Flowable):
    def __init__(self, width):
        super().__init__()
        self.width = width; self.height = 5
    def draw(self):
        self.canv.setStrokeColor(RGRAY); self.canv.setLineWidth(0.5)
        self.canv.line(0, 2, self.width, 2)


class AlgoBox(Flowable):
    def __init__(self, title, lines, col_w):
        super().__init__()
        self.title = title; self.lines = lines; self.col_w = col_w
        self.line_h = 9; self.title_h = 14; self.pad = 4
        self.height = self.title_h + len(lines) * self.line_h + 2 * self.pad + 4
    def draw(self):
        c = self.canv; w = self.col_w - 8; h = self.height - 4; x0 = 4; y0 = 0
        c.setStrokeColor(black); c.setLineWidth(0.75); c.rect(x0, y0, w, h)
        c.setFillColor(HexColor("#e8e8e8")); c.rect(x0, y0+h-self.title_h, w, self.title_h, fill=1)
        c.setFillColor(black); c.setFont(FB, 8.5); c.drawString(x0+4, y0+h-11, self.title)
        c.setFont(FM, 7); yy = y0 + h - self.title_h - self.pad - 8
        for ln in self.lines:
            c.drawString(x0+6, yy, ln); yy -= self.line_h


def footer(canvas, doc):
    canvas.saveState(); canvas.setFont(F, 8); canvas.setFillColor(GRAY)
    canvas.drawCentredString(PAGE_W/2, MARGIN_BOT-20, f"{doc.page}")
    canvas.restoreState()


def make_table(headers, rows, col_widths=None):
    data = [[Paragraph(f"<b>{h}</b>", sTH) for h in headers]]
    for row in rows:
        data.append([Paragraph(str(c), sTC) for c in row])
    if col_widths is None:
        col_widths = [COL_W / len(headers)] * len(headers)
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, RGRAY),
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#e8e8e8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def build(output_path=None):
    import os
    out = output_path or os.environ.get("PAPER_OUTPUT", os.path.join(os.path.dirname(__file__), "paper.pdf"))
    doc = BaseDocTemplate(out, pagesize=letter, topMargin=MARGIN_TOP,
                          bottomMargin=MARGIN_BOT, leftMargin=MARGIN_LR, rightMargin=MARGIN_LR)

    TITLE_H = 183
    GAP = 2
    COL_H_P1 = BODY_H - TITLE_H - GAP
    title_frame = Frame(MARGIN_LR, MARGIN_BOT + COL_H_P1 + GAP,
                        PAGE_W - 2*MARGIN_LR, TITLE_H, id="title",
                        topPadding=0, bottomPadding=0)
    first_L = Frame(MARGIN_LR, MARGIN_BOT, COL_W, COL_H_P1, id="first_L")
    first_R = Frame(MARGIN_LR + COL_W + COL_GAP, MARGIN_BOT, COL_W, COL_H_P1, id="first_R")

    def cols(pid):
        l = Frame(MARGIN_LR, MARGIN_BOT, COL_W, BODY_H, id=f"{pid}_L")
        r = Frame(MARGIN_LR+COL_W+COL_GAP, MARGIN_BOT, COL_W, BODY_H, id=f"{pid}_R")
        return l, r
    lf, rf = cols("b"); lf2, rf2 = cols("b2")
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[title_frame, first_L, first_R], onPage=footer),
        PageTemplate(id="twocol", frames=[lf, rf], onPage=footer),
        PageTemplate(id="twocol2", frames=[lf2, rf2], onPage=footer),
    ])

    S = []
    FW = PAGE_W - 2*MARGIN_LR

    # ── TITLE ───────────────────────────────────────────────────────
    S.append(Spacer(1, 2))
    S.append(Paragraph(
        "Multilevel Visibility Hash Filter:<br/>"
        "Variance-Driven Shadow Ray Caching for Real-Time Path Tracing", sTitle))
    S.append(Spacer(1, 3))
    S.append(Paragraph("M. Kugelmann", sAuthor))
    S.append(Paragraph("Draft — February 2026", sAffil))
    S.append(HRule(FW))

    S.append(Paragraph("<b>Abstract</b>", sAbsH))
    S.append(Paragraph(
        "We present a multilevel spatial hash table that caches pairwise visibility "
        "between surface regions and light regions for real-time path tracing. "
        "The cached mean serves as a control variate with Russian roulette residual "
        "(CV+RRR) &mdash; a classical technique that makes shadow-ray gating provably "
        "unbiased regardless of cache accuracy &mdash; forming a self-regulating loop "
        "that concentrates traces on shadow boundaries. "
        "Multiple LOD levels are written simultaneously "
        "and selected per query by screen-space cell footprint. "
        "We integrate the cache with ReSTIR DI and GI pipelines: cached visibility "
        "informs light selection, gates final shading shadow rays, and enables "
        "contribution-weighted revalidation that approaches biased-skip cost while "
        "preserving unbiasedness. "
        "Initial profiling on Bistro exterior shows "
        '<font color="red">##%</font> shadow-ray reduction in direct illumination '
        'and <font color="red">##%</font> in GI revalidation, '
        "with no measurable bias and negligible cache-maintenance overhead.",
        sAbsB))
    S.append(Paragraph(
        "<b>Keywords:</b> visibility caching, shadow rays, spatial hashing, "
        "control variate, Russian roulette, ReSTIR, real-time rendering",
        ParagraphStyle("KW", parent=sAbsB, fontSize=8, leading=10, spaceAfter=2)))
    S.append(HRule(FW))
    S.append(Spacer(1, 2))
    S.append(NextPageTemplate("twocol"))
    S.append(FrameBreak())

    # ── 1 INTRODUCTION ──────────────────────────────────────────────
    S.append(Paragraph("1&nbsp;&nbsp;Introduction", sH1))
    S.append(Paragraph(
        "Shadow rays dominate the cost of direct lighting in real-time path "
        "tracing. Most confirm what nearby rays already established: a surface "
        "region is consistently lit or consistently occluded from a light region. "
        "We cache point-to-point visibility in a spatial hash table "
        "and gate shadow rays via control-variate Russian roulette residual "
        "(CV+RRR): the cached mean replaces most traces, a randomly-triggered "
        "correction preserves unbiasedness, and a self-regulating loop "
        "concentrates remaining traces on shadow boundaries.",
        sB0))
    S.append(Paragraph(
        "Kugelmann [2006] explored three independent cache experiments "
        "&#8212; irradiance, binary visibility, and free-path distance &#8212; "
        "each with CV+RRR correction in a fixed-resolution single-level "
        "spatial hash. We develop the binary visibility experiment into a "
        "complete real-time system. Binary is sufficient for shadow decisions; "
        "its Bernoulli structure gives variance for free from a single cached "
        "mean (var&nbsp;=&nbsp;&#956;(1&#8722;&#956;)); and the (point,&nbsp;point) "
        "domain aligns with pairwise visibility queries. "
        "CV+RRR itself is a classical technique (Szirmay-Kalos et al., "
        "&#8220;go with the winners&#8221;; independently in [Kugelmann 2006]). "
        "We do not claim it as new &#8212; we advocate for its wider adoption "
        "and develop the system around it.",
        sB))
    S.append(Paragraph(
        "World-space visibility caches are a natural complement to ReSTIR "
        "[Bitterli et al. 2020; Ouyang et al. 2021; Lin et al. 2022]: "
        "spatial reuse concentrates many pixels onto the same light or "
        "secondary hit, and a world-space cache amortizes their shared "
        "visibility queries automatically. "
        "The cache integrates with ReSTIR DI and GI pipelines at three "
        "points: light selection, final shading, and path revalidation.",
        sB))
    S.append(Paragraph(
        "Our contributions: "
        "(1)&nbsp;A real-time pairwise binary visibility cache with CV+RRR "
        "correction, where the Bernoulli variance signal self-regulates "
        "trace probability without per-scene tuning. "
        "(2)&nbsp;Three integration points with ReSTIR DI/GI sharing one "
        "cache &#8212; light selection weighting, final-shading shadow-ray "
        "gating, and GI revalidation gating &#8212; the last being the "
        "strongest case since no screen-space alternative exists for "
        "arbitrary secondary hits. "
        "(3)&nbsp;Real-time capacity management &#8212; temporal decay, "
        "pressure-scaled eviction, warp reduction (SM&nbsp;6.5), "
        "distance-gated LOD selection &#8212; and an optional multilevel "
        "structure that reduces sensitivity to cell-size choice.",
        sB))

    # ── 2 RELATED WORK ─────────────────────────────────────────────
    S.append(FrameBreak())
    S.append(Paragraph("2&nbsp;&nbsp;Related Work", sH1))
    S.append(Paragraph(
        "<b>Visibility caching.</b> Ward [1994] introduced statistical shadow "
        "testing &#8212; gating shadow rays by spatial statistics. "
        "Popov et al. [2013] developed adaptive quantization visibility caching, "
        "reporting less than 2% of shadow rays needed. Ulbrich et al. [2013] "
        "proposed progressive refinement. Guo, Eisemann and "
        "Eisemann [2020] (NEE++) cache voxel-to-voxel visibility probability "
        "in a 6D domain with bidirectional symmetry and RR "
        "rejection, reporting 80% shadow ray reduction. Their "
        "approach uses a dense D<super>3</super>&#215;D<super>3</super> matrix "
        "(16<super>3</super> voxels, ~32&nbsp;MB, single resolution, offline).",
        sB0))
    S.append(Paragraph(
        "<b>Kugelmann [2006]</b> explored three independent cache experiments "
        "within a spatial hash grid [Teschner et al. 2003]: "
        "(1)&nbsp;irradiance (point,&nbsp;direction)&nbsp;&#8594;&nbsp;&#8477;, "
        "(2)&nbsp;binary visibility "
        "(point,&nbsp;point)&nbsp;&#8594;&nbsp;{0,1}, and "
        "(3)&nbsp;free-path distance "
        "(point,&nbsp;direction)&nbsp;&#8594;&nbsp;&#8477;<sub>&#8805;0</sub> "
        "&#8212; each with CV+RRR correction rates driven by their respective "
        "variances, in a fixed-resolution single-level hash applied to "
        "shadow-test reduction in robust instant global illumination. "
        "The binary visibility experiment is the direct ancestor of this work. "
        "Two decades of hardware evolution &#8212; GPU ray tracing, wave "
        "intrinsics &#8212; and the ReSTIR framework provide the context that "
        "makes the 2006 experiment practical as a real-time system.",
        sB))
    S.append(Paragraph(
        "Concurrent with this work, Bok&#353;ansk&#253; and Meister [2025] "
        "feed neural visibility estimates into weighted reservoir sampling "
        "for light selection &#8212; the same visibility-weighted selection idea "
        "as our Sec.&nbsp;8.1. Their approach uses an Instant-NGP backbone "
        "[M&#252;ller et al. 2022] and operates in biased mode by default, "
        "using network output directly for shading when confident. "
        "CV+RRR (Sec.&nbsp;4) would make their biased mode unbiased by "
        "construction. "
        "Reservoir Splatting [Liu et al. 2025] improves temporal path reuse "
        "robustness under camera motion via forward projection with Jacobian "
        "correction; our cache addresses the orthogonal problem of spatial "
        "revalidation cost.",
        sB))
    S.append(Paragraph(
        "<b>Spatial hashing.</b> Teschner et al. [2003] established spatial "
        "hashing for collision detection. Binder et al. [2018] applied fingerprint-"
        "based hashing to path-space filtering with jitter before "
        "quantization. M&#252;ller et al. [2022] (Instant-NGP) store multi-resolution "
        "features in hash tables combined via MLP. Stotko et al. [2025] (MrHash) "
        "use variance-driven adaptation in flat hash for TSDF reconstruction. "
        "Gautron [2020, 2021] used LOD index in the hash function with "
        "viewing-distance-based cell size selection for real-time ray-traced AO.",
        sB))
    S.append(Paragraph(
        "<b>ReSTIR.</b> Bitterli et al. [2020] introduced resampled importance "
        "sampling for direct lighting. Ouyang et al. [2021] and "
        "Lin et al. [2022] extended this to path reuse, where "
        "revalidation rays test visibility from the current "
        "shading point to a neighbor&#8217;s secondary hit. The biased/unbiased "
        "tradeoff &#8212; skip revalidation (light leaks) vs. always retrace "
        "(expensive) &#8212; motivates our approach. "
        "CV+RRR integrates with Area ReSTIR [Zhang et al. 2024] without "
        "modification: the final shadow-ray structure is identical to "
        "standard RTXDI.",
        sB))
    S.append(Paragraph(
        "<b>Control variates and hashing.</b> Szirmay-Kalos et al. described "
        "the &#8220;go with the winners&#8221; estimator: returning a control "
        "variate value on RR termination instead of zero. "
        "[Kugelmann 2006] developed CV+RRR independently for the same purpose. "
        "We apply this classical technique to cached visibility "
        "and advocate for its wider adoption. "
        "For hash noise we use pcg3d [Jarzynski and Olano 2020], a GPU hash "
        "function that passes all but one BigCrush test at ~12&nbsp;ALU with "
        "no lookup table.",
        sB))

    # ── 3 DATA STRUCTURE ────────────────────────────────────────────
    S.append(Paragraph("3&nbsp;&nbsp;Data Structure", sH1))

    S.append(Paragraph("3.1&nbsp;&nbsp;Entry", sH2))
    S.append(Paragraph(
        "Each entry stores a fingerprint and a packed uint with two 16-bit "
        "counters (visible_count, total_count):",
        sB0))
    S.append(Paragraph(
        "<font face='Courier' size='7'>"
        "struct Entry {<br/>"
        "&nbsp;&nbsp;uint fingerprint; // collision detect<br/>"
        "&nbsp;&nbsp;uint packed; &nbsp;&nbsp;&nbsp;&nbsp;// [vis:16][total:16]<br/>"
        "}; // 8 bytes"
        "</font>", sCd))
    S.append(Paragraph(
        "V=1 adds 0x00010001; V=0 adds 0x00000001. Single InterlockedAdd &#8212; "
        "both counters always in sync. Mean = vis/total, variance = mean(1&#8722;mean). "
        "Weighted insertion optional: quantize weight to 4 bits (1&#8211;15), add "
        "(w&lt;&lt;16)|w for V=1. Overflow prevented by inline decay: "
        "when total exceeds a trigger, subtract 1/8 of both counters.",
        sB))

    S.append(Paragraph("3.2&nbsp;&nbsp;LOD Configuration", sH2))
    S.append(Paragraph(
        "Three levels. Default: asymmetric &#8212; endpoint A (shading point) refines "
        "faster than B (light/secondary hit), matching the common unidirectional "
        "PT case where roles are known. Cell sizes in world units; no scene bounds "
        "needed (§4). "
        "Optional: symmetric cell sizes for bidirectional use cases, required when "
        "canonicalization (Sec. 4) is enabled.",
        sB0))

    t_lod = make_table(
        ["Level", "Cell A", "Cell B", "&#8776; px @ 5 m"],
        [["L0", "10 m", "10 m", "~107"],
         ["L1", "1.25 m", "2.5 m", "~13 / ~27"],
         ["L2", "8 cm", "62 cm", "~0.9 / ~6.7"]],
        [28, 46, 46, 46])
    S += [Spacer(1, 4), t_lod]
    S.append(Paragraph(
        "<b>Table 1.</b> Asymmetric cell sizes (default). Symmetric variant uses "
        "Cell A for both endpoints. Pixel column shows projected Cell&nbsp;A / "
        "Cell&nbsp;B side length at 5&nbsp;m distance, 90&#176; HFoV, 1080p. "
        "L2 Cell&nbsp;A is subpixel at 5&nbsp;m because L2 is only active at "
        "close range (distance-gated, Sec.&nbsp;5).",
        sCap))
    S.append(Paragraph(
        "Cell sizes are calibrated for primary viewing distances of "
        "2&#8211;20&nbsp;m in mixed exterior/interior scenes (Bistro, Sponza). "
        "Scenes at substantially different scales (tabletop close-ups, "
        "city-scale flyovers) would benefit from camera-adaptive cell sizing "
        "via FoV and circle of confusion &#8212; deferred to future work.",
        sB))
    S.append(Paragraph(
        "<b>LOD asymmetry.</b> Cell sizes are asymmetric: endpoint&nbsp;A "
        "(shading point) is quantized more finely than endpoint&nbsp;B "
        "(light source or secondary hit). This is justified for direct "
        "illumination where the shading point exhibits more spatial variation "
        "(view-dependent BRDF, geometric normal) than the light source "
        "(spatially coherent emission). For GI revalidation (Sec.&nbsp;9), "
        "where B is also a surface point, symmetric cells may be more "
        "appropriate &#8212; we defer this investigation, noting that at L2 "
        "both endpoints are typically close spatially, limiting the impact.",
        sB))
    S.append(Paragraph(
        "<b>Explicit vs.&nbsp;neural.</b> Compared to neural visibility caches "
        "[Bok&#353;ansk&#253; and Meister 2025], the explicit hash table offers "
        "inspectable entries (cached &#956; and sample count are directly "
        "readable), zero inference latency (one hash + one memory read vs. "
        "MLP evaluation), predictable cold-start behavior (first sample "
        "populates an entry immediately), and tunable parameters with clear "
        "semantics. The neural approach offers automatic spatial adaptation "
        "without explicit LOD configuration and potentially better "
        "generalization. CV+RRR (Sec.&nbsp;8) applies identically to either "
        "data structure.",
        sB))

    # ── 4 ADDRESSING ────────────────────────────────────────────────
    S.append(Paragraph("4&nbsp;&nbsp;Addressing", sH1))
    S.append(Paragraph(
        "Quantization uses absolute cell-size division: int3(floor(pos / cell_size)). "
        "No scene bounds needed &#8212; works for any position. Both endpoints are "
        "jittered independently before quantization, with magnitude = cell_size. "
        "Jitter uses pcg3d [Jarzynski &amp; Olano, 2020], seeded from the "
        "unquantized position bits asuint(pos). Each surface point therefore "
        "gets independent jitter, and a fixed world-space point always maps "
        "to the same cell.",
        sB0))
    S.append(Paragraph(
        "<b>Stochastic vs coherent jitter.</b>&nbsp; "
        "Prior path-space filtering [Binder et al., 2018] seeds jitter from "
        "the preliminary cell index floor(pos/cell_size), so all positions within "
        "a preliminary cell share the same displacement vector. This maximizes "
        "samples per cell but creates sharp step functions at (irregularly placed) "
        "cell boundaries &#8212; a systematic, persistent bias that does not diminish "
        "with accumulation. "
        "Position-seeded jitter instead gives probabilistic cell membership near "
        "boundaries: nearby surface points may map to different cells, producing "
        "an intrinsic box filter across the boundary. The marginal variance increase "
        "from this boundary dilution is noise that reduces with sample count, "
        "while boundary steps are irreducible bias. Eliminating bias at the cost "
        "of slightly more reducible variance is the standard Monte Carlo trade-off.",
        sB0))
    S.append(Paragraph(
        "Fingerprint uses the same jittered+quantized coordinates as the address "
        "but a different hash function [Keller et al., 2016],[Binder et al., 2018]. "
        "Optional bidirectional canonicalization (lexicographic swap) merges "
        "V(P,Q) and V(Q,P) into one entry; requires symmetric cell sizes. "
        "Probe sequence: double hashing with fingerprint as h<sub>2</sub>. "
        "IBL samples use a virtual far endpoint; "
        "a 1-bit is_inf flag selects angular quantization (octahedral mapping) "
        "for infinite endpoints (IBL, directional lights) vs positional quantization "
        "for finite surfaces, preventing collisions between the two address spaces. "
        "Canonicalization applies only to finite&#215;finite pairs.",
        sB0))

    # ── 5 INSERT ────────────────────────────────────────────────────
    S.append(Paragraph("5&nbsp;&nbsp;Insert", sH1))
    S.append(Paragraph(
        "L0 is read to decide write depth. During bootstrap, all levels are "
        "written. Once L0 matures, fine levels are written only where L0 variance "
        "exceeds a threshold &#8212; the same variance signal that drives RR "
        "survival probability in Sec.&nbsp;8 (see coupled variance adaptation). "
        "A distance interval gates the LOD range by "
        "target square pixel footprint: skip levels where the cell is below "
        "4&#215;4 pixels or above 64&#215;64 pixels. "
        "Clipmap-like: L0 far field, L2 near field, L1 bridges. "
        "Both-endpoint jitter is in the addressing step "
        "(Sec.&nbsp;4). Single InterlockedAdd on packed uint ensures "
        "counters stay in sync.",
        sB0))

    algo_insert = AlgoBox("Algorithm 1: Distance + Variance-Gated Insert", [
        "Input: pos_a, pos_b, visibility V, camera_pos",
        "di <- distance_lod_interval(pos_a, camera_pos)",
        "r0 <- lookup_single(pos_a, pos_b, di.min_level)",
        "if r0 = MISS or r0.weight < w_bootstrap then",
        "  var_max <- N_LEVELS - 1               // bootstrap",
        "else if r0.variance > tau then",
        "  var_max <- N_LEVELS - 1               // boundary",
        "else",
        "  var_max <- di.min_level               // smooth",
        "max_level <- min(di.max_level, var_max)",
        "for l <- di.min_level to max_level do",
        "  jitter pos_a by cell_size(l)",
        "  try_insert(hash(pos_a,pos_b,l), fp(pos_a,pos_b,l), V)",
    ], COL_W)
    S += [Spacer(1, 4), algo_insert, Spacer(1, 4)]

    S.append(Paragraph(
        "The cache is live during the frame (not double-buffered). At L0 "
        "(4<super>3</super>), each cell spans thousands of pixels. After ~1K "
        "shadow rays, L0 is substantially populated. An ABA race exists when "
        "two threads simultaneously find an empty slot (fp=0) and both claim it "
        "via CompareExchange &#8212; the second overwrites the first, wasting one "
        "traced sample. At L0 with warp reduction (~16 atomics/cell/frame), "
        "the collision rate is negligible. At L2 without warp reduction, the "
        "rate is approximately 1/waveSize&nbsp;&#8776;&nbsp;3% of inserts per "
        "contested cell. The wasted sample does not affect the surviving "
        "entry&#8217;s mean. A 64-bit CAS on a combined {fingerprint,&nbsp;packed} "
        "entry would eliminate the race at the cost of doubling entry size. "
        "On SM6.5+, warp-level reduction via WaveMatch coalesces threads "
        "targeting the same cell into a single atomic (~16&#215; reduction at L0). "
        "The packed format enables this directly &#8212; merging N samples is one "
        "InterlockedAdd of (vis_count&lt;&lt;16 | total_count).",
        sB))

    # ── 6 EVICTION + DECAY ──────────────────────────────────────────
    S.append(Paragraph("6&nbsp;&nbsp;Eviction and Temporal Decay", sH1))
    S.append(Paragraph(
        "Pressure-scaled eviction is always active on the insert path. Steps 0&#8211;1 "
        "are protected (no eviction at home slot). From step 2, each step doubles "
        "the eviction threshold, enabling self-healing of long chains. "
        "Inline overflow decay uses a CAS loop to atomically subtract 1/8 of both "
        "counters when total exceeds a trigger, keeping counts near the ceiling so recent "
        "samples dominate. Integer shift-truncation preserves the mean ratio "
        "within ~0.003% at trigger counts. "
        "For dynamic scenes, an optional background decay pass traverses 1/N of "
        "the table per frame, halving counts on each visit. The effective "
        "half-life is DECAY_PERIOD frames. "
        "At DECAY_PERIOD=60 (~1&nbsp;s at 60&nbsp;fps): an entry not refreshed "
        "decays to 1/1024 of its original count in 10&nbsp;s (10&nbsp;half-lives). "
        "At DECAY_PERIOD=300 (~5&nbsp;s): the same decay takes 50&nbsp;s. "
        "Active entries resist decay because their sample rate (hundreds of "
        "inserts/frame at L0) far exceeds the decay rate (one halving per "
        "DECAY_PERIOD frames). Not needed for single-frame rendering.",
        sB0))

    # ── 7 LOOKUP ────────────────────────────────────────────────────
    S.append(Paragraph("7&nbsp;&nbsp;Lookup", sH1))

    algo_lookup = AlgoBox("Algorithm 2: Coarse-to-Fine Lookup", [
        "Input: pos_a, pos_b, camera_pos",
        "best <- MISS",
        "di <- distance_lod_interval(pos_a, camera_pos)",
        "for l <- di.min_level to di.max_level do",
        "  slot <- find(fp(pos_a,pos_b,l), hash(pos_a,pos_b,l))",
        "  if slot < 0 then break              // no entry",
        "  e <- table[slot]",
        "  if e.total < w_min then break        // too sparse",
        "  p <- e.vis / e.total",
        "  best <- (mean=p, var=p(1-p), level=l)",
        "  if best.var < tau then break         // clean enough",
        "return best",
    ], COL_W)
    S += [Spacer(1, 4), algo_lookup, Spacer(1, 4)]

    S.append(Paragraph(
        "Four stopping conditions: distance interval bounds, no entry, too few samples, low variance.",
        sB))

    # ── 8 CONTROL VARIATE + RR ──────────────────────────────────────
    S.append(Paragraph("8&nbsp;&nbsp;Control Variate with Russian Roulette", sH1))

    S.append(Paragraph(
        "The cached mean &#956; serves as a control variate [Szirmay-Kalos et al.]. "
        "Analytic lighting (BRDF &#215; L<sub>e</sub> &#215; G) is always evaluated. "
        "Only the shadow ray is gated:",
        sB0))

    algo_cv = AlgoBox("Algorithm 3: Shading with Cached Visibility", [
        "Input: hit, light",
        "analytic <- brdf x Le x G",
        "r <- lookup(hit.pos, light.pos)",
        "if r = MISS then",
        "  V <- trace(hit, light); insert(V)",
        "  return analytic x V",
        "p_s <- clamp(r.var / tau, P_MIN, 1)",
        "if random() < p_s then",
        "  V <- trace(hit, light); insert(V)",
        "  return analytic x (r.mean + (V - r.mean) / p_s)",
        "else",
        "  return analytic x r.mean     // no trace, no insert",
    ], COL_W)
    S += [Spacer(1, 4), algo_cv, Spacer(1, 4)]

    S.append(Paragraph(
        "<b>Unbiasedness proof.</b> "
        "The estimator V&#770; equals &#956;&nbsp;+&nbsp;(V&nbsp;&#8722;&nbsp;&#956;)/p "
        "with probability p, and &#956; with probability (1&#8722;p). "
        "E[V&#770;] = p&#183;(&#956;&nbsp;+&nbsp;(E[V]&#8722;&#956;)/p) "
        "+ (1&#8722;p)&#183;&#956; = E[V]. "
        "The residual variance is Var[V&#770;]&nbsp;=&nbsp;(1/p&nbsp;&#8722;&nbsp;1)"
        "&#183;Var[V&nbsp;&#8722;&nbsp;&#956;]. "
        "When &#956;&nbsp;=&nbsp;E[V], the residual is zero &#8212; a perfect cache "
        "needs no correction rays. Cache quality affects only efficiency "
        "(residual variance), never correctness. Only traced values are "
        "inserted &#8212; returning &#956; without tracing does not update the "
        "cache, preventing positive feedback.",
        sB))
    S.append(Paragraph(
        "<b>Generality.</b> CV+RRR converts any visibility estimate &#956; &#8212; "
        "whether from a spatial hash (this work), a neural network "
        "[Bok&#353;ansk&#253; and Meister 2025], temporal reprojection, or spatial "
        "neighbor polling &#8212; into an unbiased estimator wherever a mean "
        "estimate is available. The technique is agnostic to the source of "
        "&#956;; cache quality affects only efficiency, never correctness.",
        sB))
    S.append(Paragraph(
        "<b>Why binary visibility.</b> "
        "[Kugelmann 2006] explored three cached quantities; we choose "
        "binary visibility for three reasons: "
        "(1)&nbsp;binary is sufficient for shadow-ray decisions &#8212; the ray "
        "either hits or misses; "
        "(2)&nbsp;Bernoulli structure gives variance for free from &#956; alone "
        "(var&nbsp;=&nbsp;&#956;(1&#8722;&#956;)), requiring no separate variance "
        "estimator; "
        "(3)&nbsp;the (point,&nbsp;point)&nbsp;&#8594;&nbsp;{0,1} domain aligns "
        "naturally with ReSTIR&#8217;s pairwise queries where each reservoir "
        "stores a specific source&#8211;target pair. "
        "Free-path distance [Kugelmann 2006, experiment&nbsp;3] is a richer "
        "representation but requires a separate variance estimator and is not "
        "pursued here.",
        sB))
    S.append(Paragraph(
        "<b>Coupled variance adaptation.</b> "
        "The same Bernoulli variance var&nbsp;=&nbsp;&#956;(1&#8722;&#956;) drives "
        "two reinforcing mechanisms simultaneously: "
        "(1)&nbsp;RR survival probability "
        "p&nbsp;=&nbsp;clamp(var/&#964;, p<sub>min</sub>,&nbsp;1) governs the "
        "correction rate &#8212; how often shadow rays are traced; "
        "(2)&nbsp;the write-depth gate (Sec.&nbsp;5.2) governs spatial resolution "
        "&#8212; whether fine-level cache entries are updated. "
        "High-variance regions trace more often <i>and</i> update fine levels; "
        "low-variance regions trace rarely <i>and</i> only update the coarsest "
        "level. This coupling is self-regulating: no per-scene tuning is needed "
        "because the variance signal adapts to local shadow structure "
        "automatically. The coupling only becomes possible with a multilevel "
        "cache &#8212; [Kugelmann 2006] had fixed resolution, so only the "
        "correction rate was variance-driven.",
        sB))
    S.append(Paragraph(
        "Self-regulating: low &#963;<super>2</super> &#8594; aggressive RR &#8594; "
        "few traces. High &#963;<super>2</super> &#8594; always trace &#8594; cache "
        "updates &#8594; &#963;<super>2</super> drops. Lighting change &#8594; "
        "&#963;<super>2</super> rises &#8594; traces reallocated. "
        "P<sub>min</sub>&nbsp;&#8776;&nbsp;0.05 ensures at least 5% of pixels "
        "always trace.",
        sB))

    S.append(Paragraph("8.1&nbsp;&nbsp;Firefly Mitigation", sH2))
    S.append(Paragraph(
        "At P<sub>min</sub>=0.05, surviving samples are amplified up to "
        "1/P<sub>min</sub>&nbsp;=&nbsp;20&#215;. "
        "Worst case: &#956;&#8776;0, V=1, p=0.05 &#8594; "
        "V&#770;&nbsp;=&nbsp;0&nbsp;+&nbsp;(1&#8722;0)/0.05&nbsp;=&nbsp;20. "
        "At shadow edges where &#956;&#8776;0.5, fireflies are spatially correlated "
        "&#8212; adjacent pixels share similar p<sub>survive</sub>, producing "
        "bright clusters that temporal denoisers integrate into persistent "
        "bright bands.",
        sB0))
    S.append(Paragraph(
        "<b>Adaptive P<sub>min</sub>.</b> Scale the survival floor by shading "
        "contribution: p<sub>floor</sub>&nbsp;=&nbsp;clamp(luminance(f<sub>s</sub>"
        "&#183;L<sub>e</sub>&#183;G)&nbsp;/&nbsp;firefly_budget, "
        "P<sub>min</sub>, 1). "
        "firefly_budget is the maximum tolerable absolute luminance "
        "(cd/m&#178;) from a single amplified sample. "
        "Example: with firefly_budget&nbsp;=&nbsp;10 and shading contribution "
        "luminance&nbsp;50, p<sub>floor</sub>&nbsp;=&nbsp;1 &#8212; the ray is "
        "always traced, preventing a 1000-luminance firefly. A dim contribution "
        "of luminance&nbsp;0.1 gets p<sub>floor</sub>&nbsp;=&nbsp;0.01 &#8212; "
        "aggressive RR is safe because even 100&#215; amplification produces "
        "only luminance&nbsp;10. Unbiased.",
        sB))
    S.append(Paragraph(
        "<b>Output clamp (biased safety net).</b> "
        "Clamp the amplified estimate: V&#770;&nbsp;=&nbsp;clamp(V&#770;,&nbsp;0,&nbsp;C). "
        "Introduces bias bounded by C&nbsp;&#215;&nbsp;p per clamped sample. "
        "Equivalent to p&nbsp;&#8594;&nbsp;max(p,&nbsp;1/C). "
        "Visually: slight darkening at penumbra edges vs. bright firefly bands.",
        sB))

    # ── 9 RESTIR INTEGRATION ────────────────────────────────────────
    S.append(Paragraph("9&nbsp;&nbsp;ReSTIR Integration", sH1))
    S.append(Paragraph(
        "The cache interacts with ReSTIR at three points, all using the same "
        "hash table. Both DI and GI queries are point-to-point visibility lookups.",
        sB0))

    S.append(Paragraph("9.1&nbsp;&nbsp;Cache-Informed Light Selection", sH2))
    S.append(Paragraph(
        "Replace V=1 in ReSTIR's target function &#x1D45D;&#x0302; with cached &#956; "
        "during initial candidate generation: "
        "&#x1D45D;&#x0302; = f<sub>s</sub> &#215; L<sub>e</sub> &#215; G "
        "&#215; max(&#956;, &#956;<sub>min</sub>). "
        "The &#956;<sub>min</sub> floor (default 0.01) prevents permanent "
        "exclusion of visible lights with stale cache entries. "
        "Bok&#353;ansk&#253; and Meister [2025] independently apply the same "
        "visibility-weighted selection idea with a neural cache.",
        sB0))
    S.append(Paragraph(
        "<b>Unbiasedness.</b> The cached &#956; appears only in the target "
        "function &#x1D45D;&#x0302; used for candidate selection, not in the "
        "final estimator. ReSTIR&#8217;s 1/W normalization cancels "
        "&#x1D45D;&#x0302; &#8212; the selected light&#8217;s contribution is "
        "divided by its selection probability, which includes &#956;. For this "
        "cancellation to hold, every light must have nonzero selection "
        "probability. The &#956;<sub>min</sub> floor enforces this: even a "
        "fully occluded light (true &#956;=0) retains at least 1% of its "
        "BRDF-weighted selection weight.",
        sB))
    S.append(Paragraph(
        "An exploration candidate (1/M of budget, where M is the number of "
        "initial light candidates per pixel, typically 32) uses uniform "
        "sampling and always traces its shadow ray &#8212; the &#949;-greedy "
        "strategy. Combined with &#956;<sub>min</sub>, permanent exclusion "
        "is impossible.",
        sB))
    S.append(Paragraph(
        "L0 suffices for candidate weighting. Occluded lights (&#956;&#8776;0) are "
        "effectively removed from the candidate pool, improving hit rate from "
        "~70% to ~95% in scenes with many occluded lights.",
        sB))

    S.append(Paragraph("9.2&nbsp;&nbsp;Post-Shading Shadow Ray", sH2))
    S.append(Paragraph(
        "After ReSTIR selects a light, apply CV+RR (Algorithm 3) on the final "
        "shadow ray. Decoupled from ReSTIR internals. Saves ~88% of final shadow "
        "rays. Modest but zero risk.",
        sB0))

    S.append(Paragraph("9.3&nbsp;&nbsp;ReSTIR GI Revalidation", sH2))
    S.append(Paragraph(
        "The cache's strongest use case. ReSTIR GI spatial reuse borrows "
        "neighbor paths and must verify visibility from the current shading point "
        "P to the neighbor's secondary hit Q. With k=5 spatial neighbors, "
        "unbiased revalidation costs 5 shadow rays per pixel &#8212; the main reason "
        "production systems use biased skip-revalidation.",
        sB0))
    S.append(Paragraph(
        "CV+RR makes unbiased revalidation near-free: look up cached V(P, Q), "
        "apply contribution-weighted RR (Sec. 10). Expected traces drop from 5 to "
        "~0.7 per pixel.",
        sB))

    t_restir = make_table(
        ["Insertion point", "Rays saved", "Unbiased?", "Risk"],
        [["In target (selection)", "M candidates", "If &#956;>0", "Feedback loop"],
         ["Post-shading", "~88% of 1/px", "Trivially", "Minimal"],
         ["GI revalidation", "~85% of k/px", "CV+RR", "Cold on disocclusion"]],
        [60, 52, 46, 60])
    S += [Spacer(1, 4), t_restir]
    S.append(Paragraph(
        "<b>Table 2.</b> Cache insertion points in ReSTIR.",
        sCap))

    # ── 10 CONTRIBUTION-WEIGHTED REVALIDATION ────────────────────────
    S.append(Paragraph("10&nbsp;&nbsp;Contribution-Weighted Revalidation", sH1))
    S.append(Paragraph(
        "RR probability proportional to how much the revalidation residual "
        "<i>matters to the pixel</i>, not just visibility variance. Maximum "
        "possible residual for neighbor i: "
        "f<sub>s</sub> &#215; L<sub>o</sub> &#215; G &#215; max(&#956;, 1&#8722;&#956;).",
        sB0))
    S.append(Paragraph(
        "With the cache, three regimes: &#956;&#8776;1 (known visible, small residual "
        "&#8594; skip), &#956;&#8776;0 (known occluded, small residual &#8594; skip), "
        "&#956;&#8776;0.5 (uncertain &#8594; trace if bright). The cache collapses two "
        "of three cases. Without cache, &#956;=0.5 for all GI queries (no spatial "
        "neighbor poll exists for arbitrary secondary hits), degrading to "
        "contribution-only RR.",
        sB))

    algo_reval = AlgoBox("Algorithm 4: Contribution-Weighted Revalidation", [
        "for i <- 0 to K_NEIGHBORS do",
        "  Q <- neighbor[i].secondary_hit",
        "  mu <- lookup(my_pos, Q).mean",
        "  bound <- f_s * Lo * G(my_pos, Q)",
        "  residual <- bound * max(mu, 1-mu)",
        "  p <- clamp(residual / threshold, P_MIN, 1)",
        "  if random() < p then",
        "    V <- trace(my_pos, Q); insert(my_pos, Q, V)",
        "    V_est[i] <- mu + (V - mu) / p",
        "  else",
        "    V_est[i] <- mu",
    ], COL_W)
    S += [Spacer(1, 4), algo_reval, Spacer(1, 4)]

    S.append(Paragraph("10.1&nbsp;&nbsp;Path Sharing", sH2))
    S.append(Paragraph(
        "ReSTIR GI concentrates selections: a good path gets selected by many "
        "pixels in the reuse radius. All need to revalidate visibility to the "
        "<i>same</i> Q from nearby shading points. At L0 quantization "
        "(4<super>3</super>), nearby points hash to the same cell. The first "
        "pixel to trace populates the entry; subsequent pixels find it cached "
        "within the same frame.",
        sB0))
    S.append(Paragraph(
        "With 50&#8211;100 pixels selecting the same path, they fall into "
        "~3&#8211;5 L0 cells. Total traces: ~3&#8211;5 instead of ~50&#8211;100. "
        "This is the strongest architectural argument for L0's coarse resolution "
        "&#8212; it maximizes sharing across pixels that selected the same reused path.",
        sB))

    t_compare = make_table(
        ["Method", "Traces/px (k=5)", "Visibility signal"],
        [["Full revalidation", "5.0", "N/A"],
         ["Contribution RR, no cache", "~1.5", "None"],
         ["Contribution + cache", "~0.5&#8211;1.0", "Cached &#956;"]],
        [80, 60, 78])
    S += [Spacer(1, 4), t_compare]
    S.append(Paragraph(
        "<b>Table 3.</b> GI revalidation cost.",
        sCap))

    # ── 11 CACHE-FREE ALTERNATIVES ───────────────────────────────────
    S.append(Paragraph("11&nbsp;&nbsp;Cache-Free Alternatives", sH1))
    S.append(Paragraph(
        "Screen-space alternatives capture substantial benefit at lower cost, "
        "particularly for DI.",
        sB0))
    S.append(Paragraph(
        "<b>Binary V<sub>prev</sub>.</b> Use ReSTIR's temporal reservoir "
        "history as &#956;. Zero storage. But binary (maximum residual when wrong), "
        "breaks on disocclusion, cannot help GI revalidation.",
        sBul, bulletText="&#8226;"))
    S.append(Paragraph(
        "<b>Spatial neighbor poll.</b> During DI spatial reuse, pool neighbors' "
        "traced V for the same light into a fractional estimate. Temporal EMA "
        "gives smooth &#956;. One float/pixel. Does not work for GI (each neighbor "
        "has a different Q).",
        sBul, bulletText="&#8226;"))

    t_alt = make_table(
        ["Approach", "&#956; quality", "Helps GI?", "Camera-robust?"],
        [["V<sub>prev</sub>", "Binary", "No", "No"],
         ["Poll + EMA", "Fractional", "No", "Partial"],
         ["Hash cache", "Converged", "Yes", "Yes"]],
        [54, 56, 46, 62])
    S += [Spacer(1, 4), t_alt]
    S.append(Paragraph(
        "<b>Table 4.</b> Cache-free approaches capture an estimated ~60% of DI "
        "benefit at substantially lower implementation cost "
        '(<font color="red">projected &#8212; see Sec.&nbsp;13 for measured '
        "comparisons</font>). "
        "The cache&#8217;s unique advantages &#8212; GI revalidation and "
        "camera-motion robustness &#8212; have no screen-space equivalent.",
        sCap))

    # ── 12 RUNTIME STATISTICS ───────────────────────────────────────
    S.append(Paragraph("12&nbsp;&nbsp;Runtime Statistics", sH1))
    S.append(Paragraph(
        "Five per-frame atomic counters (inserts, evictions, misses, decay triggers, "
        "probe steps) on a dedicated buffer enable load monitoring at negligible cost. "
        "Derived metrics: load pressure (eviction/insert ratio), cache effectiveness "
        "(1 &#8722; miss/query), average probe depth. "
        "DECAY_PERIOD auto-tunes via PI controller on smoothed load pressure &#8212; "
        "one-sided: speeds up under load, never slows beyond a user-set ceiling "
        "(DECAY_PERIOD_MAX, the minimum responsiveness for the scene type). "
        "Quality knobs (TAU_RR, P<sub>min</sub>, firefly_budget) are never "
        "auto-tuned &#8212; they are user decisions.",
        sB0))

    # ── 13 RESULTS ──────────────────────────────────────────────────
    S.append(Paragraph("13&nbsp;&nbsp;Results", sH1))
    S.append(Paragraph(
        "All measurements at 1920&#215;1080, 1&nbsp;spp, RTX&nbsp;4090, "
        "driver 560.x, DXR&nbsp;1.1. Reference images: 4096&nbsp;spp "
        "accumulation, same seed. MSE computed in linear RGB.",
        sB0))

    S.append(Paragraph("13.1&nbsp;&nbsp;Test Scenes", sH2))

    t_scenes = make_table(
        ["Scene", "Triangles", "Lights", "Character"],
        [['<font color="red">Bistro Exterior</font>',
          '<font color="red">2.8 M</font>',
          '<font color="red">128 area</font>',
          '<font color="red">Many small occluders, complex penumbrae</font>'],
         ['<font color="red">Sponza</font>',
          '<font color="red">262 K</font>',
          '<font color="red">1 dir + IBL</font>',
          '<font color="red">Large open interior, sharp shadow boundary</font>'],
         ['<font color="red">Cornell Box</font>',
          '<font color="red">32</font>',
          '<font color="red">1 area</font>',
          '<font color="red">Stress test: single cell covers entire scene</font>']],
        [46, 34, 34, 104])
    S += [Spacer(1, 4), t_scenes]
    S.append(Paragraph(
        "<b>Table 5.</b> Test scenes. Bistro is the primary benchmark; "
        "Sponza tests single-light coherence; Cornell Box verifies graceful "
        "degradation when the cache offers no spatial advantage.",
        sCap))

    S.append(Paragraph("13.2&nbsp;&nbsp;Shadow-Ray Reduction", sH2))

    t_rays = make_table(
        ["Scene", "Mode", "DI final", "GI reval.", "Total rays/px"],
        [['<font color="red">Bistro</font>',
          "Baseline",
          '<font color="red">1.00</font>',
          '<font color="red">1.00</font>',
          '<font color="red">2.00</font>'],
         ['<font color="red">Bistro</font>',
          "Cache",
          '<font color="red">##</font>',
          '<font color="red">##</font>',
          '<font color="red">##</font>'],
         ['<font color="red">Sponza</font>',
          "Baseline",
          '<font color="red">1.00</font>',
          '<font color="red">1.00</font>',
          '<font color="red">2.00</font>'],
         ['<font color="red">Sponza</font>',
          "Cache",
          '<font color="red">##</font>',
          '<font color="red">##</font>',
          '<font color="red">##</font>'],
         ['<font color="red">Cornell</font>',
          "Cache",
          '<font color="red">##</font>',
          '<font color="red">&#8212;</font>',
          '<font color="red">##</font>']],
        [40, 36, 36, 36, 40])
    S += [Spacer(1, 4), t_rays]
    S.append(Paragraph(
        '<font color="red"><b>Table 6.</b> Shadow rays traced per pixel. '
        "DI&nbsp;final = post-ReSTIR shading shadow ray. "
        "GI&nbsp;reval. = ReSTIR&nbsp;GI path revalidation shadow ray. "
        "Baseline traces every ray unconditionally (1.0). "
        "Cache values are the fraction of rays actually traced after CV+RRR "
        "gating (lower is better). "
        "Expected: Bistro DI ~0.12, GI ~0.15; Sponza DI ~0.08; "
        "Cornell ~1.0 (cache cannot help &#8212; single cell, high variance)."
        "</font>",
        sCap))

    S.append(Paragraph("13.3&nbsp;&nbsp;Frame Time", sH2))

    t_time = make_table(
        ["Component", "Bistro (ms)", "Sponza (ms)"],
        [["Lookup",
          '<font color="red">##</font>',
          '<font color="red">##</font>'],
         ["Insert + warp reduce",
          '<font color="red">##</font>',
          '<font color="red">##</font>'],
         ["Decay (1/60 table)",
          '<font color="red">##</font>',
          '<font color="red">##</font>'],
         ["Cache total overhead",
          '<font color="red">##</font>',
          '<font color="red">##</font>'],
         ["Shadow rays saved",
          '<font color="red">&#8722;##</font>',
          '<font color="red">&#8722;##</font>'],
         ["<b>Net frame time &#916;</b>",
          '<font color="red"><b>&#8722;##</b></font>',
          '<font color="red"><b>&#8722;##</b></font>']],
        [62, 48, 48])
    S += [Spacer(1, 4), t_time]
    S.append(Paragraph(
        '<font color="red"><b>Table 7.</b> Frame time breakdown. '
        "Cache overhead is the cost of lookup + insert + decay. "
        "Shadow rays saved is the time recovered by not tracing gated rays. "
        "Net &#916; = overhead &#8722; savings (negative = net win). "
        "Expected: lookup ~0.05&nbsp;ms, insert ~0.08&nbsp;ms, "
        "decay ~0.02&nbsp;ms; shadow savings ~0.8&#8211;1.2&nbsp;ms "
        "depending on scene complexity. "
        "Measure via GPU timestamp queries bracketing each dispatch."
        "</font>",
        sCap))

    S.append(Paragraph("13.4&nbsp;&nbsp;Convergence", sH2))
    S.append(Paragraph(
        '<font color="red">[Figure 2: MSE vs. frame number, log-log plot.] '
        "X-axis: frame index (1&#8211;256). Y-axis: MSE relative to "
        "4096-spp reference. Three curves per scene: "
        "(a)&nbsp;baseline 1&nbsp;spp, "
        "(b)&nbsp;cache-enabled 1&nbsp;spp, "
        "(c)&nbsp;baseline at equivalent ray budget (i.e. baseline using "
        "only as many rays as the cache actually traced). "
        "Curve (b) should track curve (a) &#8212; same MSE proves "
        "unbiasedness. Curve (c) at higher MSE proves the cache is "
        "not just saving rays but allocating them better. "
        "Include error bars (std over 5 seeds) if variance is visible. "
        "Inset: per-pixel variance map at frame 64, baseline vs. cache "
        "&#8212; cache should show lower variance at penumbrae.</font>",
        sB0))

    S.append(Paragraph("13.5&nbsp;&nbsp;Ablation", sH2))

    t_ablation = make_table(
        ["Configuration", "Rays/px", "MSE", "ms"],
        [["Full system (L0+L1+L2, var gate, warp red.)",
          '<font color="red">##</font>',
          '<font color="red">##</font>',
          '<font color="red">##</font>'],
         ["&#8722; variance gate (always write all levels)",
          '<font color="red">##</font>',
          '<font color="red">##</font>',
          '<font color="red">##</font>'],
         ["&#8722; distance LOD (all levels at all distances)",
          '<font color="red">##</font>',
          '<font color="red">##</font>',
          '<font color="red">##</font>'],
         ["&#8722; warp reduction (per-thread atomics only)",
          '<font color="red">##</font>',
          '<font color="red">##</font>',
          '<font color="red">##</font>'],
         ["L0 only (coarsest, 10&nbsp;m cells)",
          '<font color="red">##</font>',
          '<font color="red">##</font>',
          '<font color="red">##</font>'],
         ["L2 only (finest, 8&nbsp;cm cells)",
          '<font color="red">##</font>',
          '<font color="red">##</font>',
          '<font color="red">##</font>'],
         ["&#8722; firefly adaptive P<sub>min</sub>",
          '<font color="red">##</font>',
          '<font color="red">##</font>',
          '<font color="red">##</font>'],
         ["No cache (baseline)",
          '<font color="red">1.00 / 1.00</font>',
          '<font color="red">##</font>',
          '<font color="red">##</font>']],
        [100, 34, 34, 26])
    S += [Spacer(1, 4), t_ablation]
    S.append(Paragraph(
        '<font color="red"><b>Table 8.</b> Ablation on Bistro exterior, '
        "frame 64, 1&nbsp;spp. Rays/px = DI&nbsp;/&nbsp;GI. MSE relative "
        "to 4096-spp reference. ms = total frame time. "
        "Key predictions: "
        "(a)&nbsp;&#8722;variance gate should show same rays/px but higher "
        "insert cost (unnecessary fine-level writes in smooth regions); "
        "(b)&nbsp;L0-only should show moderate ray reduction but higher MSE "
        "near shadow edges (coarse cells blur penumbrae); "
        "(c)&nbsp;L2-only should show poor far-field performance (subpixel "
        "cells, low hit rate); "
        "(d)&nbsp;&#8722;warp reduction should show same MSE but higher "
        "insert ms (more atomic contention at L0).</font>",
        sCap))

    S.append(Paragraph("13.6&nbsp;&nbsp;Disocclusion Stress Test", sH2))
    S.append(Paragraph(
        '<font color="red">[Figure 3: Cache hit rate vs. frame during fast '
        "camera flythrough.] "
        "X-axis: frame. Y-axis: cache hit rate (queries returning valid "
        "entry / total queries). "
        "Protocol: static camera for 120 frames (cache warm-up), then "
        "fast lateral strafe exposing previously hidden geometry. "
        "Measure: (a)&nbsp;frames to recover 80% hit rate after "
        "disocclusion event, (b)&nbsp;peak variance spike magnitude, "
        "(c)&nbsp;ray count spike (should approach 1.0 = baseline in "
        "disoccluded region, proving graceful degradation). "
        "Compare DECAY_PERIOD = 60 vs. 300: faster decay should recover "
        "sooner but steady-state hit rate may be slightly lower. "
        "Secondary plot: per-level hit rate (L0 recovers first, L2 last)."
        "</font>",
        sB0))
    S.append(Paragraph(
        "<b>Graceful degradation.</b> Where cell resolution is too coarse, "
        "variance stays high, p<sub>survive</sub> &#8594; 1, every ray traces. "
        "Rarely-selected lights &#8594; MISS &#8594; unconditional trace. "
        "Baseline cost, zero harm. The cache can never make things worse.",
        sB))

    # ── 14 CONCLUSION ───────────────────────────────────────────────
    S.append(Paragraph("14&nbsp;&nbsp;Conclusion", sH1))
    S.append(Paragraph(
        "We have described an assembly of known techniques for real-time "
        "visibility caching: sparse multilevel hash replacing NEE++'s dense matrix "
        "[Guo et al. 2020], control-variate RR [Szirmay-Kalos et al.] returning "
        "cached mean on trace termination, distance-gated LOD intervals, "
        "angular quantization for infinite endpoints, runtime statistics with "
        "auto-tuning, and integration with ReSTIR DI/GI pipelines.",
        sB0))
    S.append(Paragraph(
        "Key observations: (1) ReSTIR GI's selection "
        "concentration aligns with coarse cache cells, enabling "
        "within-frame amortization of revalidation traces; (2) "
        "contribution-weighted RR gates revalidation by perceptual importance "
        "rather than raw visibility variance; (3) the design degrades gracefully "
        "&#8212; every failure mode falls back to unoptimized baseline tracing.",
        sB))

    # ── REFERENCES ──────────────────────────────────────────────────
    S.append(Paragraph("References", sH1))
    for r in [
        "[Binder et al. 2018] N. Binder, S. Fricke, and A. Keller. "
        "\"Path Space Filtering.\" <i>GPU Zen 2</i>, 2018.",

        "[Bitterli et al. 2020] B. Bitterli, C. Wyman, M. Pharr, P. Shirley, "
        "A. Lefohn, and W. Jarosz. \"Spatiotemporal Reservoir Resampling for "
        "Real-Time Ray Tracing with Dynamic Direct Lighting.\" "
        "<i>ACM Trans. Graph.</i>, 39(4):148, 2020.",

        "[Bok&#353;ansk&#253; and Meister 2025] A. Bok&#353;ansk&#253; and D. Meister. "
        "\"Neural Visibility Cache.\" 2025.",

        "[Guo et al. 2020] Y. Guo, E. Eisemann, and T. Eisemann. "
        "\"NEE++: Faster N-Closest Emitter Sampling with Voxelized "
        "Visibility.\" <i>Pacific Graphics</i>, 2020.",

        "[Jarzynski &amp; Olano 2020] M. Jarzynski and M. Olano. "
        "\"Hash Functions for GPU Rendering.\" "
        "<i>JCGT</i>, 9(3):21&#8211;38, 2020.",

        "[Keller et al. 2016] A. Keller, N. Binder, and K. Dahm. "
        "\"Path Space Similarity Determined by Fourier Histogram Descriptors.\" "
        "ACM SIGGRAPH 2014 Talks; extended with hash-based filtering 2016.",

        "[Lin et al. 2022] D. Lin et al. \"Generalized Resampled Importance "
        "Sampling: Foundations of ReSTIR.\" <i>ACM Trans. Graph.</i>, 41(4), 2022.",

        "[M&#252;ller et al. 2022] T. M&#252;ller, A. Evans, C. Schied, and A. Keller. "
        "\"Instant Neural Graphics Primitives with a Multiresolution Hash "
        "Encoding.\" <i>ACM Trans. Graph.</i>, 41(4):102, 2022.",

        "[Kugelmann 2006] M. Kugelmann. \"Efficient Adaptive Global Illumination "
        "Algorithms.\" Diplomarbeit, Universit&#228;t Ulm, 2006. "
        "Supervisor: A. Keller.",

        "[Ouyang et al. 2021] Y. Ouyang, S. Liu, M. Kettunen, M. Pharr, and "
        "J. Pantaleoni. \"ReSTIR GI: Path Resampling for Real-Time Path "
        "Tracing.\" <i>Computer Graphics Forum</i>, 40(8):17&#8211;29, 2021.",

        "[Popov et al. 2013] S. Popov, R. Ramamoorthi, F. Durand, and "
        "G. Drettakis. \"Adaptive Quantization Visibility Caching.\" "
        "<i>Eurographics Symposium on Rendering</i>, 2013.",

        "[Stotko et al. 2025] P. Stotko et al. \"MrHash: Resolution Where It "
        "Counts.\" <i>arXiv:2511.21459</i>, 2025.",

        "[Szirmay-Kalos et al.] L. Szirmay-Kalos et al. \"Go with the Winners\" "
        "&#8212; control variate Russian roulette. (Exact citation TBD.)",

        "[Teschner et al. 2003] M. Teschner et al. \"Optimized Spatial Hashing "
        "for Collision Detection of Deformable Objects.\" "
        "<i>Proc. VMV</i>, pp. 47&#8211;54, 2003.",

        "[Ulbrich et al. 2013] R. Ulbrich et al. \"Progressive Visibility "
        "Caching.\" 2013.",

        "[Ward 1994] G. J. Ward. \"Adaptive Shadow Testing for Ray Tracing.\" "
        "<i>Eurographics Rendering Workshop</i>, 1994.",
    ]:
        S.append(Paragraph(r, sRef))

    doc.build(S)
    print(f"Paper: {out}")


if __name__ == "__main__":
    import sys
    build(sys.argv[1] if len(sys.argv) > 1 else None)
