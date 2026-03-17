"""
services/thumbnail.py — Cinematic 16:9 thumbnail generator (1280×720).

Layout:
  Anime/TV:
    • Blurred backdrop BG + left gradient
    • Poster art right side
    • Title + synopsis left
    • Genre tags top
    • Frosted glass EPISODE card bottom-right
    • Watermark top-right

  Movie:
    • Same BG/gradient/poster
    • Title + synopsis left
    • Genre tags top
    • Frosted glass INFO card bottom-right (rating + year, no episode/season)
    • Watermark top-right

Fonts auto-downloaded on first run to assets/fonts/.
"""

import io
import os
import logging
import asyncio
import aiohttp
from typing import Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

logger = logging.getLogger(__name__)

_FONT_DIR  = "assets/fonts"
_FONT_BOLD = os.path.join(_FONT_DIR, "DejaVuSans-Bold.ttf")
_FONT_REG  = os.path.join(_FONT_DIR, "DejaVuSans.ttf")
_SIZE      = (1280, 720)

_FONT_URLS = {
    _FONT_BOLD: "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans-Bold.ttf",
    _FONT_REG:  "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf",
}


# ── Font auto-download ────────────────────────────────────────────────────────

async def _ensure_fonts():
    os.makedirs(_FONT_DIR, exist_ok=True)
    for path, url in _FONT_URLS.items():
        if not os.path.exists(path):
            try:
                logger.info(f"Downloading font: {os.path.basename(path)}")
                async with aiohttp.ClientSession() as s:
                    async with s.get(url, timeout=aiohttp.ClientTimeout(total=30)) as r:
                        if r.status == 200:
                            with open(path, "wb") as f:
                                f.write(await r.read())
                            logger.info(f"Font saved: {path}")
            except Exception as e:
                logger.warning(f"Font download failed ({path}): {e}")


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _fetch(url: str) -> Optional[Image.Image]:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    return Image.open(io.BytesIO(await r.read())).convert("RGBA")
    except Exception as e:
        logger.error(f"Image fetch failed: {e}")
    return None


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    path = _FONT_BOLD if bold else _FONT_REG
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _wrap(text: str, font, draw, max_w: int) -> list:
    words = text.split()
    lines, line = [], []
    for w in words:
        if draw.textlength(" ".join(line + [w]), font=font) > max_w:
            if line:
                lines.append(" ".join(line))
            line = [w]
        else:
            line.append(w)
    if line:
        lines.append(" ".join(line))
    return lines


# ── UI Components ─────────────────────────────────────────────────────────────

def _draw_glass_rect(canvas, box, fill=(20, 24, 35, 180), outline=(255, 255, 255, 40), radius=15):
    x1, y1, x2, y2 = box
    region = canvas.crop((x1, y1, x2, y2))
    region = region.filter(ImageFilter.GaussianBlur(15))
    mask   = Image.new("L", (x2-x1, y2-y1), 0)
    dm     = ImageDraw.Draw(mask)
    dm.rounded_rectangle([0, 0, x2-x1, y2-y1], radius=radius, fill=255)
    canvas.paste(region, (x1, y1), mask)
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=1)
    return Image.alpha_composite(canvas, overlay)


def _draw_watermark(canvas: Image.Image, text: str) -> Image.Image:
    if not text:
        return canvas
    W, H   = canvas.size
    px, py = 12, 6
    margin = 32
    font   = _font(18, bold=False)
    td     = ImageDraw.Draw(canvas)
    bbox   = td.textbbox((0, 0), text, font=font)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    x = W - tw - px*2 - margin
    y = margin
    canvas = _draw_glass_rect(canvas, [x, y, x+tw+px*2, y+th+py*2], fill=(0,0,0,160))
    ImageDraw.Draw(canvas).text((x+px, y+py), text, font=font, fill=(220,220,220,220))
    return canvas


def _draw_genre_tags(canvas: Image.Image, genres: list) -> Image.Image:
    if not genres:
        return canvas
    W, H = canvas.size
    ov   = Image.new("RGBA", (W, H), (0,0,0,0))
    od   = ImageDraw.Draw(ov)
    font = _font(20, bold=False)
    x, y = 60, 120
    for i, g in enumerate(genres[:4]):
        od.text((x, y), g, font=font, fill=(200,200,200,200))
        x += int(od.textlength(g, font=font)) + 15
        if i < len(genres[:4])-1:
            od.ellipse([x-10, y+10, x-6, y+14], fill=(210,25,25,200))
            x += 15
    return Image.alpha_composite(canvas, ov)


def _draw_base(poster: Image.Image, backdrop: Optional[Image.Image]) -> tuple:
    """Build background + gradient + poster art. Returns (canvas, draw)."""
    W, H   = _SIZE
    canvas = Image.new("RGBA", (W, H), (10, 12, 18, 255))

    bg = (backdrop or poster).convert("RGBA").resize((W, H), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(12))
    bg = ImageEnhance.Brightness(bg).enhance(0.22)
    canvas.paste(bg, (0, 0))

    grad = Image.new("RGBA", (W, H), (0,0,0,0))
    gd   = ImageDraw.Draw(grad)
    for i in range(W // 2):
        alpha = int(220 * (1-(i/(W//2))**0.8))
        gd.line([(i, 0), (i, H)], fill=(8,10,16,alpha))
    canvas = Image.alpha_composite(canvas, grad)

    char   = poster.convert("RGBA")
    char_h = int(H * 1.1)
    char_w = int(char_h * char.width / char.height)
    char   = char.resize((char_w, char_h), Image.LANCZOS)
    canvas.paste(char, (W-char_w+60, -20), char)

    return canvas


def _draw_title_synopsis(canvas, meta: dict) -> int:
    """Draw title + synopsis. Returns y position after text."""
    draw   = ImageDraw.Draw(canvas)
    left_x = 60
    title  = meta.get("title", "UNKNOWN").upper()

    def _get_font(text, max_w):
        for s in [75, 60, 45]:
            f     = _font(s, True)
            lines = _wrap(text, f, draw, max_w)
            if len(lines) <= 2:
                return f, lines, int(s*1.1)
        f = _font(35, True)
        return f, _wrap(text, f, draw, max_w)[:3], 39

    tf, tlines, th = _get_font(title, 580)
    curr_y = 175
    for ln in tlines:
        draw.text((left_x+2, curr_y+2), ln, font=tf, fill=(0,0,0,100))
        draw.text((left_x,   curr_y),   ln, font=tf, fill=(255,255,255,255))
        curr_y += th

    synopsis = (meta.get("synopsis") or meta.get("overview",""))[:180]
    if synopsis:
        if not synopsis.endswith("..."):
            synopsis += "..."
        df = _font(22, False)
        curr_y += 20
        for ln in _wrap(synopsis, df, draw, 550)[:3]:
            draw.text((left_x, curr_y), ln, font=df, fill=(200,200,210,230))
            curr_y += 30

    return curr_y


# ── Card variants ─────────────────────────────────────────────────────────────

def _episode_card(canvas, meta: dict) -> Image.Image:
    """Frosted glass card for Anime/TV — shows episode + season."""
    W, H = _SIZE
    card_w, card_h = 350, 130
    cx = W - card_w - 32
    cy = H - card_h - 32
    canvas = _draw_glass_rect(canvas, [cx, cy, cx+card_w, cy+card_h])
    cd = ImageDraw.Draw(canvas)

    ep     = str(meta.get("episode", "01"))  # "01" or "01-13" range
    # Only zero-pad if it's a plain number, not a range
    if "-" not in ep:
        ep = ep.zfill(2)
    season = str(meta.get("season", "1")).zfill(2)
    ep_label = "EP " + ep

    cd.text((cx+20, cy+20), ep_label,            font=_font(28, True),  fill=(255,255,255))
    cd.text((cx+20, cy+65), f"Season {season}", font=_font(18, False), fill=(180,180,180))

    # Mini poster in card
    poster = meta.get("_poster_img")
    if poster:
        mini_w = 100
        mini   = poster.resize((mini_w, card_h-20), Image.LANCZOS)
        canvas.paste(mini, (cx+card_w-mini_w-10, cy+10))

    return canvas


def _movie_card(canvas, meta: dict) -> Image.Image:
    """Frosted glass card for Movie — shows rating + year (no episode/season)."""
    W, H = _SIZE
    card_w, card_h = 350, 110
    cx = W - card_w - 32
    cy = H - card_h - 32
    canvas = _draw_glass_rect(canvas, [cx, cy, cx+card_w, cy+card_h])
    cd = ImageDraw.Draw(canvas)

    score = str(meta.get("score") or "N/A")
    year  = str(meta.get("year")  or "")

    if score != "N/A":
        cd.text((cx+20, cy+18), "⭐ " + score, font=_font(32, True),  fill=(255, 220, 50))
    if year:
        cd.text((cx+20, cy+62), year,           font=_font(20, False), fill=(180, 180, 180))

    # Mini poster in card
    poster = meta.get("_poster_img")
    if poster:
        mini_w = 100
        mini   = poster.resize((mini_w, card_h-20), Image.LANCZOS)
        canvas.paste(mini, (cx+card_w-mini_w-10, cy+10))

    return canvas


# ── Main build ────────────────────────────────────────────────────────────────

def _build_card(
    poster:       Image.Image,
    backdrop:     Optional[Image.Image],
    meta:         dict,
    is_movie:     bool = False,
    watermark:    str  = "",
) -> Image.Image:
    W, H   = _SIZE
    canvas = _draw_base(poster, backdrop)
    draw   = ImageDraw.Draw(canvas)

    # Title + synopsis
    curr_y = _draw_title_synopsis(canvas, meta)

    # Watch Now button
    curr_y += 40
    btn_w, btn_h = 180, 52
    draw.rounded_rectangle(
        [60, curr_y, 60+btn_w, curr_y+btn_h],
        radius=8, fill=(210, 25, 25, 255)
    )
    draw.text((60+42, curr_y+14), "WATCH NOW", font=_font(18), fill=(255,255,255))

    # Bottom-right info card
    meta["_poster_img"] = poster  # pass for mini thumbnail in card
    if is_movie:
        canvas = _movie_card(canvas, meta)
    else:
        canvas = _episode_card(canvas, meta)

    # Genre tags
    genres = meta.get("genres", [])
    if isinstance(genres, str):
        genres = [g.strip() for g in genres.split(",")]
    canvas = _draw_genre_tags(canvas, genres)

    # Watermark
    if watermark:
        canvas = _draw_watermark(canvas, watermark)

    return canvas


# ── Public API ────────────────────────────────────────────────────────────────

async def build_thumbnail(
    poster_url:   str,
    backdrop_url: str | None = None,
    watermark:    str = "",
    meta:         dict = {},
    is_movie:     bool = False,
) -> bytes | None:
    """
    Build cinematic 1280×720 thumbnail.
    is_movie=True → shows rating/year card instead of episode/season card.
    Returns JPEG bytes or None on failure.
    """
    await _ensure_fonts()

    poster   = (await _fetch(poster_url)) or Image.new("RGBA", (400,600), (20,20,20,255))
    backdrop = await _fetch(backdrop_url) if backdrop_url else None

    try:
        card = _build_card(poster, backdrop, meta, is_movie=is_movie, watermark=watermark)
        buf  = io.BytesIO()
        card.convert("RGB").save(buf, format="JPEG", quality=95, optimize=True, subsampling=0)
        return buf.getvalue()
    except Exception as e:
        logger.error(f"Thumbnail build failed: {e}")
        return None


def process_thumbnail(image_bytes: bytes) -> bytes:
    """Convert any uploaded image to 16:9 1280×720 JPEG."""
    try:
        img   = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h  = img.size
        ratio = w / h
        tr    = 1280 / 720
        if ratio > tr:
            new_w = int(h * tr)
            img   = img.crop(((w-new_w)//2, 0, (w-new_w)//2+new_w, h))
        elif ratio < tr:
            new_h = int(w / tr)
            img   = img.crop((0, (h-new_h)//2, w, (h-new_h)//2+new_h))
        img = img.resize((1280, 720), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"Thumbnail process failed: {e}")
        return image_bytes
