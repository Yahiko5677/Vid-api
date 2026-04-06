"""
# v5 - 2026-03-20
thumbnail.py — Cinematic 16:9 thumbnail generator (1280×720).

Layout:
  • Blurred/darkened backdrop as full background
  • Left-to-right dark gradient for text legibility
  • Poster art right side fading left
  • Genre tags row top-left
  • Large bold title + synopsis left side
  • WATCH NOW button
  • Frosted glass card bottom-right (movie: score+year, anime: ep+season)
  • Watermark top-right

Fonts: assets/fonts/DejaVuSans-Bold.ttf + DejaVuSans.ttf
       Auto-downloaded on first run.
"""

import io
import os
import logging
import asyncio
import aiohttp
from typing import Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

logger = logging.getLogger(__name__)

# System font paths (installed via fonts-dejavu-core in Dockerfile)
_FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_FONT_REG  = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_SIZE      = (1280, 720)





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
        test = " ".join(line + [w])
        if draw.textlength(test, font=font) > max_w:
            if line:
                lines.append(" ".join(line))
            line = [w]
        else:
            line.append(w)
    if line:
        lines.append(" ".join(line))
    return lines


# ── UI Components ─────────────────────────────────────────────────────────────

def _draw_glass_rect(canvas, box, fill=(20,24,35,180), outline=(255,255,255,40), radius=15):
    x1, y1, x2, y2 = box
    region = canvas.crop((x1, y1, x2, y2))
    region = region.filter(ImageFilter.GaussianBlur(15))
    mask   = Image.new("L", (x2-x1, y2-y1), 0)
    dm     = ImageDraw.Draw(mask)
    dm.rounded_rectangle([0, 0, x2-x1, y2-y1], radius=radius, fill=255)
    canvas.paste(region, (x1, y1), mask)
    overlay = Image.new("RGBA", canvas.size, (0,0,0,0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=1)
    return Image.alpha_composite(canvas, overlay)


def _draw_genre_tags(canvas: Image.Image, genres: list) -> Image.Image:
    if not genres:
        return canvas
    W, H   = canvas.size
    ov     = Image.new("RGBA", (W, H), (0,0,0,0))
    od     = ImageDraw.Draw(ov)
    font   = _font(30, bold=False)   # bigger font
    x, y   = 60, 112
    for i, g in enumerate(genres[:4]):
        od.text((x, y), g, font=font, fill=(220, 220, 220, 230))
        tw = int(od.textlength(g, font=font))
        x += tw + 20
        if i < len(genres[:4]) - 1:
            # Dot vertically centered with 30px font (ascent ~22px)
            dot_cx = x - 8
            dot_cy = y + 14   # center of text height
            dot_r  = 4
            od.ellipse(
                [dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r],
                fill=(210, 25, 25, 230)
            )
            x += 12
    return Image.alpha_composite(canvas, ov)


def _draw_watermark(canvas: Image.Image, text: str) -> Image.Image:
    if not text:
        return canvas
    W, H   = canvas.size
    margin = 32
    px, py = 14, 8
    font   = _font(20, bold=False)
    td     = ImageDraw.Draw(canvas)
    bbox   = td.textbbox((0, 0), text, font=font)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    x = W - tw - px*2 - margin
    y = margin
    canvas = _draw_glass_rect(canvas, [x, y, x+tw+px*2, y+th+py*2], fill=(0,0,0,160))
    ImageDraw.Draw(canvas).text((x+px, y+py), text, font=font, fill=(220,220,220,220))
    return canvas


# ── Base layer ────────────────────────────────────────────────────────────────

def _draw_base(poster: Image.Image, backdrop: Optional[Image.Image]) -> Image.Image:
    W, H   = _SIZE
    canvas = Image.new("RGBA", (W, H), (10,12,18,255))

    # Blurred dark background
    bg = (backdrop or poster).convert("RGBA").resize((W, H), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(14))
    bg = ImageEnhance.Brightness(bg).enhance(0.20)
    canvas.paste(bg, (0, 0))

    # Left-to-right gradient
    grad = Image.new("RGBA", (W, H), (0,0,0,0))
    gd   = ImageDraw.Draw(grad)
    for i in range(int(W * 0.65)):
        alpha = int(230 * (1-(i/(W*0.65))**0.75))
        gd.line([(i, 0), (i, H)], fill=(6, 8, 14, alpha))
    canvas = Image.alpha_composite(canvas, grad)

    # Poster/character art — right side, slightly oversized and fading
    char   = poster.convert("RGBA")
    char_h = int(H * 1.05)
    char_w = int(char_h * char.width / char.height)
    char   = char.resize((char_w, char_h), Image.LANCZOS)

    # Create fade mask — fades from transparent on left to opaque on right
    fade   = Image.new("L", (char_w, char_h), 0)
    for x in range(char_w):
        fade_alpha = int(255 * min(1.0, (x / (char_w * 0.35)) ** 1.2))
        for y2 in range(char_h):
            fade.putpixel((x, y2), fade_alpha)
    char.putalpha(fade)
    canvas.paste(char, (W-char_w+40, (H-char_h)//2), char)

    return canvas


# ── Title + synopsis ──────────────────────────────────────────────────────────

def _draw_title_synopsis(canvas, meta: dict) -> int:
    draw   = ImageDraw.Draw(canvas)
    left_x = 60
    max_w  = 600
    title  = meta.get("title", "UNKNOWN").upper()

    # Auto-size title to fit in 2 lines max
    tf, tlines, th = None, None, None
    for size in [80, 68, 55, 44, 36]:
        f     = _font(size, True)
        lines = _wrap(title, f, draw, max_w)
        if len(lines) <= 2:
            tf, tlines, th = f, lines, int(size * 1.15)
            break
    if tf is None:
        tf = _font(36, True)
        tlines = _wrap(title, tf, draw, max_w)[:3]
        th = 42

    curr_y = 165
    for ln in tlines:
        # Shadow
        draw.text((left_x+3, curr_y+3), ln, font=tf, fill=(0, 0, 0, 120))
        draw.text((left_x,   curr_y),   ln, font=tf, fill=(255, 255, 255, 255))
        curr_y += th

    # Synopsis — tighter line height, no gaps
    synopsis = (meta.get("synopsis") or meta.get("overview", ""))[:200]
    if synopsis:
        if not synopsis.endswith("..."):
            synopsis += "..."
        df      = _font(23, False)
        line_h  = 32
        curr_y += 18
        for ln in _wrap(synopsis, df, draw, 560)[:3]:
            draw.text((left_x, curr_y), ln, font=df, fill=(195, 200, 215, 225))
            curr_y += line_h

    return curr_y


# ── Info cards ────────────────────────────────────────────────────────────────

def _episode_card(canvas, meta: dict) -> Image.Image:
    W, H = _SIZE
    card_w, card_h = 320, 120
    cx = W - card_w - 30
    cy = H - card_h - 30
    canvas = _draw_glass_rect(canvas, [cx, cy, cx+card_w, cy+card_h])
    cd     = ImageDraw.Draw(canvas)

    ep     = str(meta.get("episode", "01"))
    if "-" not in ep:
        ep = ep.zfill(2)
    season = str(meta.get("season", "1")).zfill(2)

    cd.text((cx+20, cy+18), "EP " + ep,        font=_font(32, True),  fill=(255,255,255))
    cd.text((cx+20, cy+62), "Season " + season, font=_font(20, False), fill=(170,170,180))

    poster = meta.get("_poster_img")
    if poster:
        mini_w = 90
        mini_h = card_h - 16
        mini   = poster.resize((mini_w, mini_h), Image.LANCZOS)
        canvas.paste(mini, (cx + card_w - mini_w - 8, cy + 8))

    return canvas


def _movie_card(canvas, meta: dict) -> Image.Image:
    W, H = _SIZE
    card_w, card_h = 320, 120
    cx = W - card_w - 30
    cy = H - card_h - 30
    canvas = _draw_glass_rect(canvas, [cx, cy, cx+card_w, cy+card_h])
    cd     = ImageDraw.Draw(canvas)

    score = str(meta.get("score") or "")
    year  = str(meta.get("year")  or "")

    text_x = cx + 20
    if score and score not in ("N/A", "None"):
        cd.text((text_x, cy+16), "⭐ " + score, font=_font(36, True),  fill=(255, 215, 50, 255))
    if year:
        cd.text((text_x, cy+64), year,           font=_font(24, False), fill=(180, 180, 185, 255))

    poster = meta.get("_poster_img")
    if poster:
        mini_w = 90
        mini_h = card_h - 16
        mini   = poster.resize((mini_w, mini_h), Image.LANCZOS)
        canvas.paste(mini, (cx + card_w - mini_w - 8, cy + 8))

    return canvas


# ── Main builder ──────────────────────────────────────────────────────────────

def _build_card(
    poster:    Image.Image,
    backdrop:  Optional[Image.Image],
    meta:      dict,
    is_movie:  bool = False,
    watermark: str  = "",
) -> Image.Image:
    W, H   = _SIZE
    canvas = _draw_base(poster, backdrop)
    draw   = ImageDraw.Draw(canvas)

    # Title + synopsis
    curr_y = _draw_title_synopsis(canvas, meta)

    # WATCH NOW button
    curr_y += 36
    bw, bh = 185, 52
    draw.rounded_rectangle([60, curr_y, 60+bw, curr_y+bh], radius=10, fill=(210,25,25,255))
    draw.text((60+35, curr_y+13), "WATCH NOW", font=_font(19, True), fill=(255,255,255))

    # Bottom-right info card
    meta["_poster_img"] = poster
    canvas = _movie_card(canvas, meta) if is_movie else _episode_card(canvas, meta)

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
    poster_url:    str,
    backdrop_url:  Optional[str] = None,
    watermark:     str = "",
    meta:          dict = {},
    is_movie:      bool = False,
) -> Optional[bytes]:
    poster   = (await _fetch(poster_url)) or Image.new("RGBA", (400, 600), (20,20,20,255))
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
    """Convert any image to 16:9 1280×720 JPEG (for custom thumbnails)."""
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
