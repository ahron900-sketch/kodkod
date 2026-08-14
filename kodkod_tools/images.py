"""Image quality tooling for pictures the site is entitled to use.

What this does:
  * scores an image (sharpness, resolution, proportion) so weak pictures
    can be ranked down or dropped
  * finds burned-in caption/headline bars - the strips of text broadcasters
    and press offices bake into thumbnails - and crops them away, which is
    what makes a government-channel thumbnail usable as a clean photo
  * light enhancement (sharpen, contrast) for images that are otherwise fine

What this deliberately does NOT do:
  * remove, blur or paint over a logo, station bug, byline or any other
    marking that identifies who owns a picture. Those are detected
    elsewhere in the bot and used as a reason to REJECT the image.
  * inpaint text out of the middle of a photograph. Doing that convincingly
    needs a real inpainting model; a Pillow approximation leaves smeared
    patches that look worse than the caption did. Text in the middle of the
    frame is reported as uncroppable so the caller can skip the image.

Everything here fails open: on any error the original image is returned
unchanged and the bot carries on.
"""

import io

try:
    from PIL import Image, ImageFilter, ImageEnhance, ImageStat
    HAVE_PIL = True
except ImportError:  # same guarded-import contract as idf_scraper.py
    HAVE_PIL = False


# --- quality scoring -------------------------------------------------------

MIN_USABLE_WIDTH = 600
MIN_USABLE_HEIGHT = 340


def _open(image_bytes):
    return Image.open(io.BytesIO(image_bytes))


def sharpness(image_bytes):
    """Edge energy as a stand-in for focus. Higher is sharper. Same family
    of measure the bot's existing blur check uses, exposed as a number so
    images can be ranked rather than only pass/fail."""
    if not HAVE_PIL or not image_bytes:
        return None
    try:
        im = _open(image_bytes).convert("L").resize((300, 300))
        return ImageStat.Stat(im.filter(ImageFilter.FIND_EDGES)).var[0]
    except Exception:
        return None


def score_image(image_bytes):
    """A single 0-100 quality number plus the reasons behind it, so callers
    can sort candidates instead of taking the first thing that loads."""
    if not HAVE_PIL or not image_bytes:
        return {"score": 0, "reasons": ["no image data"]}
    try:
        im = _open(image_bytes)
        w, h = im.size
    except Exception as e:
        return {"score": 0, "reasons": [f"unreadable: {e}"]}

    reasons = []
    score = 100

    if w < MIN_USABLE_WIDTH or h < MIN_USABLE_HEIGHT:
        score -= 45
        reasons.append(f"small ({w}x{h})")

    ratio = (w / h) if h else 0
    if ratio and (ratio > 3.2 or ratio < 0.5):
        score -= 25
        reasons.append(f"odd proportion ({ratio:.2f})")

    sharp = sharpness(image_bytes)
    if sharp is not None:
        if sharp < 50:
            score -= 40
            reasons.append(f"soft/blurry (edge variance {sharp:.0f})")
        elif sharp < 120:
            score -= 12
            reasons.append(f"slightly soft ({sharp:.0f})")

    try:
        grey = _open(image_bytes).convert("L")
        spread = ImageStat.Stat(grey).stddev[0]
        if spread < 18:
            score -= 20
            reasons.append(f"flat/low contrast ({spread:.0f})")
    except Exception:
        pass

    return {"score": max(0, min(100, score)), "reasons": reasons,
            "width": w, "height": h, "sharpness": sharp}


# --- burned-in caption bars ------------------------------------------------

# A caption strip is busy (lots of edges from letterforms) and usually sits
# against a flatter background than the photo itself. Scanned in horizontal
# rows so a bar anywhere top or bottom is found regardless of height.
_BAND_ROWS = 20
_TEXT_EDGE_FACTOR = 1.9   # how much busier than the frame a row must be
_FLAT_BAND_FACTOR = 0.45  # how much flatter than the frame a solid bar is
_MAX_CROP_FRACTION = 0.34  # never eat more than a third of the picture


def _row_profile(image_bytes):
    """Per-row-band measurements used to spot caption strips.

    Two signals, because a caption bar shows up differently depending on
    what it sits on:
      edge   letterforms create edges
      flat   the bar's own background is usually a solid colour, so its
             pixel spread is far lower than a photograph's
    Edge density alone is not enough - measured against a noisy photo, a
    dark text bar is actually LESS busy than the picture, so an edge-only
    test misses exactly the bars it was written to find."""
    im = _open(image_bytes).convert("L")
    w, h = im.size
    edges = im.filter(ImageFilter.FIND_EDGES)
    profile = []
    step = max(1, h // _BAND_ROWS)
    for top in range(0, h - step + 1, step):
        box = (0, top, w, top + step)
        edge_mean = ImageStat.Stat(edges.crop(box)).mean[0]
        flatness = ImageStat.Stat(im.crop(box)).stddev[0]
        profile.append((top, top + step, edge_mean, flatness))
    return profile, w, h


def find_caption_bands(image_bytes):
    """Return the top/bottom regions that look like burned-in text bars.

    Only edge bands are reported. Text sitting in the middle of a frame is
    intentionally not reported, because cropping cannot remove it and this
    module will not paint over photographic content."""
    if not HAVE_PIL or not image_bytes:
        return {"top": 0, "bottom": 0, "text_in_middle": False}
    try:
        profile, w, h = _row_profile(image_bytes)
    except Exception:
        return {"top": 0, "bottom": 0, "text_in_middle": False}
    if not profile:
        return {"top": 0, "bottom": 0, "text_in_middle": False}

    edge_means = [e for _, _, e, _ in profile]
    flatnesses = [f for _, _, _, f in profile]
    typical_edge = sorted(edge_means)[len(edge_means) // 2] or 1e-6
    typical_flat = sorted(flatnesses)[len(flatnesses) // 2] or 1e-6
    # a band qualifies as caption-like if it is unusually busy for this
    # image OR unusually flat for it (a solid bar) - see _row_profile
    busy = [
        i for i in range(len(profile))
        if edge_means[i] > typical_edge * _TEXT_EDGE_FACTOR
        or flatnesses[i] < typical_flat * _FLAT_BAND_FACTOR
    ]

    top_px = 0
    for i in range(len(profile)):
        if i in busy:
            top_px = profile[i][1]
        else:
            break

    bottom_px = 0
    for i in range(len(profile) - 1, -1, -1):
        if i in busy:
            bottom_px = h - profile[i][0]
        else:
            break

    edge_idx = set()
    if top_px:
        edge_idx |= {i for i in range(len(profile)) if profile[i][1] <= top_px}
    if bottom_px:
        edge_idx |= {i for i in range(len(profile)) if profile[i][0] >= h - bottom_px}
    text_in_middle = any(i not in edge_idx for i in busy)

    limit = int(h * _MAX_CROP_FRACTION)
    return {"top": min(top_px, limit), "bottom": min(bottom_px, limit),
            "text_in_middle": text_in_middle, "height": h, "width": w}


def crop_caption_bands(image_bytes):
    """Crop detected caption bars off the top/bottom.

    Returns (bytes, info). On anything unexpected - or when the bars would
    take too much of the frame - the original bytes come back untouched."""
    info = find_caption_bands(image_bytes)
    top, bottom = info.get("top", 0), info.get("bottom", 0)
    if not HAVE_PIL or (not top and not bottom):
        return image_bytes, {**info, "cropped": False}
    try:
        im = _open(image_bytes)
        w, h = im.size
        if (top + bottom) >= h * _MAX_CROP_FRACTION * 2 or (h - top - bottom) < MIN_USABLE_HEIGHT:
            return image_bytes, {**info, "cropped": False, "why": "crop would gut the image"}
        out = im.crop((0, top, w, h - bottom))
        buf = io.BytesIO()
        out.convert("RGB").save(buf, format="JPEG", quality=88, optimize=True)
        return buf.getvalue(), {**info, "cropped": True,
                                "new_size": out.size, "removed_px": top + bottom}
    except Exception as e:
        return image_bytes, {**info, "cropped": False, "why": str(e)[:80]}


# --- gentle enhancement ----------------------------------------------------

def enhance(image_bytes, sharpen=1.15, contrast=1.06):
    """A light pass for images that are usable but dull. Conservative by
    intent: a news photo that looks obviously processed reads as fake, so
    this nudges rather than transforms."""
    if not HAVE_PIL or not image_bytes:
        return image_bytes
    try:
        im = _open(image_bytes).convert("RGB")
        if sharpen and sharpen != 1:
            im = ImageEnhance.Sharpness(im).enhance(sharpen)
        if contrast and contrast != 1:
            im = ImageEnhance.Contrast(im).enhance(contrast)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=90, optimize=True)
        return buf.getvalue()
    except Exception:
        return image_bytes
