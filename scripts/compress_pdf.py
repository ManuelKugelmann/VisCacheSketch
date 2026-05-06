"""Shrink embedded images in PDFs while keeping text as text.

Two strategies, tried in order:
  1. PyMuPDF Document.rewrite_images() — fast, but segfaults on some PDFs.
  2. Manual per-image rewrite via extract_image + Pillow + Page.replace_image.
     Skips any image where individual processing throws.

Text content streams are NEVER touched; searchable / selectable text is
preserved.

Usage:
    runtime/pythondist/python.exe scripts/compress_pdf.py <pdf>...
"""
import sys, os, io, shutil, traceback
import fitz                # PyMuPDF
from PIL import Image

TARGET_BYTES = 45 * 1024 * 1024  # ≤45 MB to clear GitHub's 50 MB warning
ATTEMPTS = [
    (200, 80),
    (150, 75),
    (150, 65),
    (120, 60),
    (100, 55),
    (80, 50),
    (60, 45),
]


def shrink_via_rewrite_images(in_path, dpi, quality, out_path):
    """Strategy 1: PyMuPDF's built-in rewrite_images."""
    doc = fitz.open(in_path)
    doc.rewrite_images(
        dpi_threshold=0, dpi_target=dpi, quality=quality,
        lossy=True, lossless=True, color=True, gray=True, bitonal=False,
    )
    doc.save(out_path, garbage=4, deflate=True)
    doc.close()
    return os.path.getsize(out_path)


def shrink_via_per_image(in_path, dpi, quality, out_path):
    """Strategy 2: walk every image xref, decode with Pillow, downsample to
    dpi, re-encode as JPEG, replace in place. Skips images that fail."""
    doc = fitz.open(in_path)
    seen = set()
    swapped = 0
    skipped = 0
    for page in doc:
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            if xref in seen:
                continue
            seen.add(xref)
            try:
                base = doc.extract_image(xref)
                img_bytes = base["image"]
                pil = Image.open(io.BytesIO(img_bytes))
                # Downsample if the image is larger than what `dpi` would
                # need at the bbox size on the page.
                rects = page.get_image_rects(xref) or []
                if rects:
                    rect = rects[0]
                    target_w = max(1, int(rect.width  * dpi / 72.0))
                    target_h = max(1, int(rect.height * dpi / 72.0))
                    if pil.width > target_w * 1.2 or pil.height > target_h * 1.2:
                        pil = pil.resize((target_w, target_h), Image.LANCZOS)
                if pil.mode not in ("RGB", "L"):
                    pil = pil.convert("RGB")
                buf = io.BytesIO()
                pil.save(buf, format="JPEG", quality=quality, optimize=True)
                page.replace_image(xref, stream=buf.getvalue())
                swapped += 1
            except Exception:
                skipped += 1
    doc.save(out_path, garbage=4, deflate=True)
    doc.close()
    print(f"    per-image: swapped={swapped} skipped={skipped}", flush=True)
    return os.path.getsize(out_path)


def shrink(in_path, dpi, quality):
    out_path = in_path + ".compressed"
    # Try fast path first.
    try:
        return shrink_via_rewrite_images(in_path, dpi, quality, out_path), out_path
    except Exception as e:
        print(f"    rewrite_images failed: {e}", flush=True)
    # Cleanup any partial output before fallback.
    if os.path.exists(out_path):
        try: os.remove(out_path)
        except OSError: pass
    return shrink_via_per_image(in_path, dpi, quality, out_path), out_path


def main():
    targets = sys.argv[1:]
    if not targets:
        print("usage: compress_pdf.py <pdf>...", file=sys.stderr)
        sys.exit(2)
    for in_path in targets:
        orig_bytes = os.path.getsize(in_path)
        print(f"[{os.path.basename(in_path)}] {orig_bytes/1e6:.1f} MB", flush=True)

        if orig_bytes <= TARGET_BYTES:
            print(f"  already under {TARGET_BYTES/1e6:.0f} MB target", flush=True)
            continue

        accepted = False
        for dpi, q in ATTEMPTS:
            try:
                out_bytes, out_path = shrink(in_path, dpi, q)
            except Exception as e:
                print(f"  dpi={dpi} q={q} -> error: {e}", flush=True)
                traceback.print_exc()
                continue
            ratio = out_bytes / orig_bytes
            print(f"  dpi={dpi} q={q} -> {out_bytes/1e6:.1f} MB ({ratio*100:.0f}%)", flush=True)
            if out_bytes <= TARGET_BYTES:
                shutil.move(out_path, in_path)
                print(f"  ACCEPTED", flush=True)
                accepted = True
                break
            os.remove(out_path)
        if not accepted:
            print(f"  WARN: none of the attempts fit under {TARGET_BYTES/1e6:.0f} MB", flush=True)


if __name__ == "__main__":
    main()
