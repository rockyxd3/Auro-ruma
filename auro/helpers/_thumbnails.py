import os
import math
import random
import colorsys

import aiohttp

from PIL import (
    Image,
    ImageDraw,
    ImageEnhance,
    ImageFilter,
    ImageFont,
    ImageOps,
)

from auro import config
from auro.helpers import Track

CANVAS_SIZE = (1280, 720)

# --- Cover art box ---
COVER_SIZE = (380, 380)
COVER_POS = (80, 170)
COVER_RADIUS = 34
COVER_BORDER = 8

# --- Text / layout ---
TEXT_X = 540
TITLE_Y = 178
SUBTITLE_Y = 246

# --- Progress bar ---
BAR_X0 = TEXT_X
BAR_X1 = 1210
BAR_Y = 332
BAR_H = 8
TIME_Y = 356

# --- Control pill ---
PILL_X0 = TEXT_X
PILL_Y0 = 402
PILL_W = 560
PILL_H = 88

# --- Palette (soft pastel / plum, matches the reference design) ---
COL_DARK_TEXT = (250, 246, 252)     # title — light, sits on dark blurred bg
COL_MUTED_TEXT = (225, 210, 228)    # subtitle/time — light, sits on dark blurred bg
COL_ICON = (60, 32, 74)             # icons — dark, sit on the white control pill
COL_GRAD_A = (233, 64, 135)     # pink
COL_GRAD_B = (150, 76, 220)     # purple
COL_WHITE = (255, 255, 255)


class Thumbnail:
    def __init__(self):
        base = "auro/helpers"
        self.title_font_path = f"{base}/Poppins-ExtraBold.ttf"
        self.font_title = ImageFont.truetype(self.title_font_path, 50)
        self.font_subtitle = ImageFont.truetype(f"{base}/Raleway-Bold.ttf", 24)
        self.font_time = ImageFont.truetype(f"{base}/Raleway-Bold.ttf", 20)

    # ---------- helpers ----------

    async def save_thumb(self, output_path: str, url: str) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                open(output_path, "wb").write(await resp.read())
            return output_path

    def fit_image(self, image, size):
        return ImageOps.fit(
            image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5)
        )

    def add_round_corners(self, image, radius):
        rounded = image.convert("RGBA")
        w, h = rounded.size
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=radius, fill=255)
        output = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        output.paste(rounded, (0, 0), mask)
        return output

    def fit_title_font(self, draw, text, max_width, base_size=38, min_size=24):
        """Fixed, smaller max size than before (was 50) so the title never
        looks oversized, and shrinks further only if the text is long —
        keeping layout stable across different song titles."""
        size = base_size
        while size > min_size:
            font = ImageFont.truetype(self.title_font_path, size)
            bbox = draw.textbbox((0, 0), text, font=font)
            if bbox[2] - bbox[0] <= max_width:
                return font
            size -= 2
        return ImageFont.truetype(self.title_font_path, min_size)

    def truncate(self, text: str, limit: int) -> str:
        return text[: limit - 3] + "..." if len(text) > limit else text

    def fmt_time(self, seconds) -> str:
        try:
            seconds = int(seconds)
        except (TypeError, ValueError):
            return "0:00"
        m, s = divmod(max(seconds, 0), 60)
        return f"{m}:{s:02d}"

    def duration_to_seconds(self, duration_str) -> int:
        try:
            parts = [int(p) for p in str(duration_str).split(":")]
        except ValueError:
            return 0
        total = 0
        for p in parts:
            total = total * 60 + p
        return total

    def extract_accent_colors(self, cover_img):
        """Pull a vivid accent color out of the cover art (for the border,
        progress bar, and play button), plus a hue-shifted partner color
        for gradients — so these change per song instead of being fixed."""
        small = cover_img.convert("RGB").resize((80, 80))
        quant = small.quantize(colors=8, method=Image.MEDIANCUT)
        palette = quant.getpalette()[: 8 * 3]
        counts = quant.getcolors() or []
        counts = sorted(counts, key=lambda c: -c[0])

        candidates = []
        for count, idx in counts:
            r, g, b = palette[idx * 3: idx * 3 + 3]
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            candidates.append((h, s, v, count, (r, g, b)))

        vivid = [c for c in candidates if c[1] > 0.32 and 0.22 < c[2] < 0.95]
        vivid.sort(key=lambda c: -(c[1] * c[3]))

        if vivid:
            primary = vivid[0][4]
        elif candidates:
            primary = candidates[0][4]
        else:
            primary = (210, 90, 160)

        def boost(c, min_v=0.5, max_s=0.82):
            h, s, v = colorsys.rgb_to_hsv(*(x / 255 for x in c))
            v = max(v, min_v)
            s = min(max(s, 0.45), max_s)
            r, g, b = colorsys.hsv_to_rgb(h, s, v)
            return (int(r * 255), int(g * 255), int(b * 255))

        primary = boost(primary)
        h, s, v = colorsys.rgb_to_hsv(*(x / 255 for x in primary))
        h2 = (h + 0.14) % 1.0
        r2, g2, b2 = colorsys.hsv_to_rgb(h2, min(s + 0.08, 0.85), min(v + 0.1, 0.95))
        secondary = (int(r2 * 255), int(g2 * 255), int(b2 * 255))

        return primary, secondary

    def frosted_glass(self, canvas, box, blur=26, brighten=1.08, tint_alpha=30):
        """Crops the region behind `box` from the canvas itself and blurs
        it in place — a real see-through frosted-glass look instead of a
        flat white rectangle."""
        x0, y0, x1, y1 = box
        pad = blur
        region = canvas.crop((x0 - pad, y0 - pad, x1 + pad, y1 + pad)).convert("RGB")
        region = region.filter(ImageFilter.GaussianBlur(blur))
        region = ImageEnhance.Brightness(region).enhance(brighten)
        region = region.convert("RGBA")
        tint = Image.new("RGBA", region.size, (255, 255, 255, tint_alpha))
        region.alpha_composite(tint)
        canvas.paste(region, (x0 - pad, y0 - pad))

    def glass_patch(self, canvas, box, radius, blur=20, brighten=1.12, tint_alpha=26):
        """Like frosted_glass but clipped to a rounded-rect / ellipse mask
        and returned as its own RGBA layer, so it can be alpha_composited
        in — used to replace flat white fills with a see-through glass
        surface (progress track, handle, badges, etc.)."""
        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        pad = blur
        px0, py0 = max(x0 - pad, 0), max(y0 - pad, 0)
        px1, py1 = min(x1 + pad, canvas.width), min(y1 + pad, canvas.height)
        region = canvas.crop((px0, py0, px1, py1)).convert("RGB")
        region = region.filter(ImageFilter.GaussianBlur(blur))
        region = ImageEnhance.Brightness(region).enhance(brighten)
        region = region.convert("RGBA")

        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        layer.paste(region, (px0, py0))

        mask = Image.new("L", canvas.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=255)

        out = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        out.paste(layer, (0, 0), mask)

        tint = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(tint).rounded_rectangle(
            (x0, y0, x1, y1), radius=radius, fill=(255, 255, 255, tint_alpha)
        )
        out.alpha_composite(tint)
        return out

    def lerp_color(self, c1, c2, t):
        return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))

    # ---------- background ----------

    def build_background(self, cover_img):
        """Blurred, softly darkened version of the song's own thumbnail,
        filling the whole canvas (stable — always fills edge to edge,
        never cropped weirdly since we fit-crop to the full canvas size
        before blurring)."""
        w, h = CANVAS_SIZE
        bg = self.fit_image(cover_img.convert("RGB"), (w, h))
        bg = bg.filter(ImageFilter.GaussianBlur(45))
        bg = ImageEnhance.Brightness(bg).enhance(0.62)
        bg = ImageEnhance.Color(bg).enhance(1.05)

        # gentle pink/purple wash on top so text and icons stay legible
        # and it keeps the same soft aesthetic regardless of the cover
        wash = Image.new("RGBA", (w, h), (60, 20, 70, 70))
        bg = bg.convert("RGBA")
        bg.alpha_composite(wash)
        return bg

    def draw_star(self, draw, cx, cy, size, color, alpha=220):
        pts = [
            (cx, cy - size), (cx + size * 0.18, cy - size * 0.18),
            (cx + size, cy), (cx + size * 0.18, cy + size * 0.18),
            (cx, cy + size), (cx - size * 0.18, cy + size * 0.18),
            (cx - size, cy), (cx - size * 0.18, cy - size * 0.18),
        ]
        draw.polygon(pts, fill=color + (alpha,))

    def add_sparkles(self, canvas):
        overlay = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        rng = random.Random(42)
        for _ in range(14):
            x = rng.randint(20, CANVAS_SIZE[0] - 20)
            y = rng.randint(20, 160)
            size = rng.randint(4, 11)
            self.draw_star(draw, x, y, size, COL_WHITE, alpha=rng.randint(150, 230))
        canvas.alpha_composite(overlay)

    def add_cover_sparkles(self, canvas):
        """Scatters small stars in a halo around the cover-art box (the
        area the person circled), so that box gets its own sparkle accent
        instead of just the plain empty corner it had before."""
        overlay = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        rng = random.Random(7)

        cx0, cy0 = COVER_POS[0] - COVER_BORDER, COVER_POS[1] - COVER_BORDER
        cx1 = COVER_POS[0] + COVER_SIZE[0] + COVER_BORDER
        cy1 = COVER_POS[1] + COVER_SIZE[1] + COVER_BORDER
        pad = 26

        for _ in range(16):
            # pick a point in the padded ring around the cover box, but
            # outside the box itself
            side = rng.choice(["top", "bottom", "left", "right"])
            if side == "top":
                x = rng.randint(cx0 - pad, cx1 + pad)
                y = rng.randint(cy0 - pad, cy0)
            elif side == "bottom":
                x = rng.randint(cx0 - pad, cx1 + pad)
                y = rng.randint(cy1, cy1 + pad)
            elif side == "left":
                x = rng.randint(cx0 - pad, cx0)
                y = rng.randint(cy0 - pad, cy1 + pad)
            else:
                x = rng.randint(cx1, cx1 + pad)
                y = rng.randint(cy0 - pad, cy1 + pad)
            size = rng.randint(5, 13)
            self.draw_star(draw, x, y, size, COL_WHITE, alpha=rng.randint(160, 235))

        canvas.alpha_composite(overlay)

    # ---------- cover art ----------

    def build_cover(self, cover_img, border_color=COL_WHITE):
        w, h = COVER_SIZE
        border = COVER_BORDER
        cover_rgb = cover_img.convert("RGB")

        # single layer: crop-fill the square directly, no separate blurred
        # backdrop underneath (that second layer was causing the double
        # image look around the edges)
        art = self.fit_image(cover_rgb, (w, h)).convert("RGBA")
        art = self.add_round_corners(art, COVER_RADIUS)

        outer_w, outer_h = w + border * 2, h + border * 2
        card = Image.new("RGBA", (outer_w, outer_h), (0, 0, 0, 0))
        border_rgba = tuple(border_color[:3]) + (255,)
        ImageDraw.Draw(card).rounded_rectangle(
            (0, 0, outer_w - 1, outer_h - 1),
            radius=COVER_RADIUS + border,
            fill=border_rgba,
        )
        card.alpha_composite(art, (border, border))

        # --- FIX (rounded-border shadow mismatch) ---------------------
        # Previously the shadow box used a width/height that subtracted
        # `border * 2` from the OUTER card size while still drawing with
        # radius=COVER_RADIUS (the INNER radius). That mismatch made the
        # shadow's corners a different curvature than the border's own
        # corners, so the round border looked uneven/jagged around the
        # edges. The shadow now uses the exact same outer_w/outer_h and
        # the exact same COVER_RADIUS + border used for the card itself,
        # just offset a little downward — so it stays perfectly aligned
        # with the border's rounding at every corner.
        shadow = Image.new("RGBA", (CANVAS_SIZE[0], CANVAS_SIZE[1]), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow)
        sx, sy = COVER_POS[0] - border, COVER_POS[1] - border
        sdraw.rounded_rectangle(
            (sx + 4, sy + 10, sx + outer_w - 4, sy + outer_h + 10),
            radius=COVER_RADIUS + border,
            fill=(0, 0, 0, 60),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(10))

        return card, shadow

    def draw_heart_badge(self, canvas, center):
        """Solid white circular badge (unchanged) — only the progress bar
        track and control pill get the transparent glass treatment."""
        cx, cy = center
        r = 26
        badge = Image.new("RGBA", (r * 2 + 8, r * 2 + 8), (0, 0, 0, 0))
        bd = ImageDraw.Draw(badge)
        bd.ellipse((4, 4, r * 2 + 4, r * 2 + 4), fill=(255, 255, 255, 255))
        hs = r * 0.62
        ox, oy = r + 4, r + 4
        bd.ellipse((ox - hs, oy - hs * 0.6, ox, oy + hs * 0.15), fill=(233, 64, 135, 255))
        bd.ellipse((ox, oy - hs * 0.6, ox + hs, oy + hs * 0.15), fill=(233, 64, 135, 255))
        bd.polygon(
            [
                (ox - hs, oy - hs * 0.05),
                (ox + hs, oy - hs * 0.05),
                (ox, oy + hs * 1.1),
            ],
            fill=(233, 64, 135, 255),
        )

        canvas.alpha_composite(badge, (cx - r - 4, cy - r - 4))

    # ---------- progress bar ----------

    def draw_progress_bar(self, canvas, current_sec, total_sec, grad_a, grad_b):
        draw = ImageDraw.Draw(canvas)
        w = BAR_X1 - BAR_X0
        ratio = 0 if total_sec <= 0 else min(current_sec / total_sec, 1.0)
        handle_x = BAR_X0 + int(w * ratio)

        # track — frosted glass instead of flat white, so the bar reads
        # as a translucent glass strip that still shows the blurred bg
        track_box = (BAR_X0, BAR_Y, BAR_X1, BAR_Y + BAR_H)
        glass_track = self.glass_patch(
            canvas, track_box, radius=BAR_H // 2, blur=18, brighten=1.05, tint_alpha=35
        )
        canvas.alpha_composite(glass_track)
        track_tint = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        ImageDraw.Draw(track_tint).rounded_rectangle(
            track_box, radius=BAR_H // 2, outline=(255, 255, 255, 140), width=1
        )
        canvas.alpha_composite(track_tint)

        # filled gradient portion
        if handle_x > BAR_X0:
            grad = Image.new("RGBA", (handle_x - BAR_X0, BAR_H), (0, 0, 0, 0))
            for i in range(grad.width):
                t = i / max(grad.width - 1, 1)
                color = self.lerp_color(grad_a, grad_b, t)
                for y in range(BAR_H):
                    grad.putpixel((i, y), color + (255,))
            mask = Image.new("L", grad.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                (0, 0, grad.width, BAR_H), radius=BAR_H // 2, fill=255
            )
            canvas.paste(grad, (BAR_X0, BAR_Y), mask)

        # handle — solid white ring (unchanged)
        hr = 12
        draw.ellipse(
            (handle_x - hr - 3, BAR_Y + BAR_H // 2 - hr - 3,
             handle_x + hr + 3, BAR_Y + BAR_H // 2 + hr + 3),
            fill=COL_WHITE,
        )
        draw.ellipse(
            (handle_x - hr, BAR_Y + BAR_H // 2 - hr,
             handle_x + hr, BAR_Y + BAR_H // 2 + hr),
            fill=grad_a,
        )

        draw.text((BAR_X0, TIME_Y), self.fmt_time(current_sec),
                   font=self.font_time, fill=COL_MUTED_TEXT)
        total_text = self.fmt_time(total_sec)
        bbox = draw.textbbox((0, 0), total_text, font=self.font_time)
        tw = bbox[2] - bbox[0]
        draw.text((BAR_X1 - tw, TIME_Y), total_text,
                   font=self.font_time, fill=COL_MUTED_TEXT)

    # ---------- control icons ----------

    def draw_shuffle(self, draw, cx, cy, size, color):
        s = size
        for flip in (1, -1):
            y1, y2 = cy - s * 0.35 * flip, cy + s * 0.35 * flip
            draw.line((cx - s, y1, cx + s * 0.55, y2), fill=color, width=4)
            ah = s * 0.28
            draw.polygon(
                [
                    (cx + s * 0.55, y2 - ah * 0.6),
                    (cx + s * 0.55 + ah, y2),
                    (cx + s * 0.55, y2 + ah * 0.6),
                ],
                fill=color,
            )

    def draw_skip(self, draw, cx, cy, size, color, direction=1):
        s = size
        bar_x = cx + s * 0.9 * direction
        x0, x1 = sorted((bar_x - 2 * direction, bar_x + 2 * direction))
        draw.rectangle((x0, cy - s, x1, cy + s), fill=color)
        for off in (0, s * 0.75):
            x0 = cx + off * direction
            tri = [
                (x0, cy - s),
                (x0, cy + s),
                (x0 + s * 0.85 * direction, cy),
            ]
            draw.polygon(tri, fill=color)

    def draw_play_triangle(self, draw, cx, cy, size, color):
        tri = [
            (cx - size * 0.55, cy - size),
            (cx - size * 0.55, cy + size),
            (cx + size * 0.85, cy),
        ]
        draw.polygon(tri, fill=color)

    def draw_repeat(self, draw, cx, cy, size, color):
        bbox = (cx - size, cy - size, cx + size, cy + size)
        draw.arc(bbox, start=-30, end=250, fill=color, width=4)
        angle = math.radians(250)
        ax = cx + size * math.cos(angle)
        ay = cy + size * math.sin(angle)
        ah = size * 0.4
        draw.polygon(
            [
                (ax, ay - ah * 0.5),
                (ax + ah, ay),
                (ax, ay + ah * 0.5),
            ],
            fill=color,
        )

    def draw_controls(self, canvas, grad_a, grad_b):
        pill_box = (PILL_X0, PILL_Y0, PILL_X0 + PILL_W, PILL_Y0 + PILL_H)

        # true frosted-glass pill: blur what's already behind it on the
        # canvas instead of laying down a flat white rectangle
        mask = Image.new("L", CANVAS_SIZE, 0)
        ImageDraw.Draw(mask).rounded_rectangle(pill_box, radius=PILL_H // 2, fill=255)
        pad = 30
        gx0, gy0 = PILL_X0 - pad, PILL_Y0 - pad
        gx1, gy1 = PILL_X0 + PILL_W + pad, PILL_Y0 + PILL_H + pad
        region = canvas.crop((gx0, gy0, gx1, gy1)).convert("RGB")
        region = region.filter(ImageFilter.GaussianBlur(36))
        region = ImageEnhance.Brightness(region).enhance(1.1)
        region = region.convert("RGBA")
        glass_layer = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        glass_layer.paste(region, (gx0, gy0))
        glass_masked = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        glass_masked.paste(glass_layer, (0, 0), mask)
        canvas.alpha_composite(glass_masked)

        # faint white wash so it still reads as "glass" not just a blurred
        # hole — drawn on its own transparent layer then alpha-composited,
        # since drawing alpha fills directly onto an RGBA canvas overwrites
        # pixels instead of blending (this was the earlier white-block bug)
        tint_layer = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        tdraw = ImageDraw.Draw(tint_layer)
        tdraw.rounded_rectangle(pill_box, radius=PILL_H // 2, fill=(255, 255, 255, 35))
        tdraw.rounded_rectangle(pill_box, radius=PILL_H // 2, outline=(255, 255, 255, 130), width=2)
        canvas.alpha_composite(tint_layer)

        draw = ImageDraw.Draw(canvas, "RGBA")

        cy = PILL_Y0 + PILL_H // 2
        step = PILL_W // 5
        centers = [PILL_X0 + step // 2 + step * i for i in range(5)]

        self.draw_shuffle(draw, centers[0], cy, 13, COL_ICON)
        self.draw_skip(draw, centers[1], cy, 11, COL_ICON, direction=-1)

        # play button (gradient circle, colors follow the song's accent)
        pr = 34
        play_circle = Image.new("RGBA", (pr * 2, pr * 2), (0, 0, 0, 0))
        pdraw = ImageDraw.Draw(play_circle)
        for y in range(pr * 2):
            t = y / (pr * 2 - 1)
            color = self.lerp_color(grad_a, grad_b, t)
            pdraw.line((0, y, pr * 2, y), fill=color + (255,))
        mask2 = Image.new("L", (pr * 2, pr * 2), 0)
        ImageDraw.Draw(mask2).ellipse((0, 0, pr * 2, pr * 2), fill=255)
        canvas.paste(play_circle, (centers[2] - pr, cy - pr), mask2)
        self.draw_play_triangle(draw, centers[2], cy, 15, COL_WHITE)

        self.draw_skip(draw, centers[3], cy, 11, COL_ICON, direction=1)
        self.draw_repeat(draw, centers[4], cy, 13, COL_ICON)

    # ---------- full compose ----------

    def compose(self, cover_img, title: str, subtitle: str, current_sec: int, total_sec: int):
        """Assembles the whole 1280x720 thumbnail from a PIL cover image
        plus the track's title/subtitle/progress. Returns an RGB image
        ready to save/send."""
        canvas = self.build_background(cover_img)

        grad_a, grad_b = self.extract_accent_colors(cover_img)

        self.add_sparkles(canvas)
        self.add_cover_sparkles(canvas)

        card, shadow = self.build_cover(cover_img, border_color=COL_WHITE)
        canvas.alpha_composite(shadow)
        canvas.alpha_composite(
            card, (COVER_POS[0] - COVER_BORDER, COVER_POS[1] - COVER_BORDER)
        )

        heart_cx = COVER_POS[0] + COVER_SIZE[0]
        heart_cy = COVER_POS[1] + COVER_SIZE[1]
        self.draw_heart_badge(canvas, (heart_cx, heart_cy))

        draw = ImageDraw.Draw(canvas)
        title = self.truncate(title, 40)
        font_t = self.fit_title_font(draw, title, BAR_X1 - TEXT_X, base_size=38)
        draw.text((TEXT_X, TITLE_Y), title, font=font_t, fill=COL_DARK_TEXT)
        draw.text((TEXT_X, SUBTITLE_Y), subtitle, font=self.font_subtitle, fill=COL_MUTED_TEXT)

        self.draw_progress_bar(canvas, current_sec, total_sec, grad_a, grad_b)
        self.draw_controls(canvas, grad_a, grad_b)

        return canvas.convert("RGB")

    # ---------- entry point ----------
    # NOTE: renamed from `get_thumb` to `generate` — this is the method
    # name your codebase actually calls (see anony/core/calls.py:
    # `await thumb.generate(media)`), which is what caused the
    # AttributeError: 'Thumbnail' object has no attribute 'generate'.

    async def generate(self, media: Track, current_sec: int = 0, output_path: str = None) -> str:
        """High-level entry point: downloads the track's/media's thumbnail,
        composes the full player-style image, saves it, and returns the
        output path. `media` is whatever object your play_media() call
        passes in (a Track-like object)."""
        thumb_dir = getattr(config, "THUMB_CACHE_DIR", "cache")
        os.makedirs(thumb_dir, exist_ok=True)

        media_id = getattr(media, "id", None) or getattr(media, "vidid", None) or "thumb"
        thumb_url = getattr(media, "thumbnail", None) or getattr(media, "thumb", None)
        title = getattr(media, "title", "Unknown Title")
        channel = getattr(media, "channel", None) or getattr(media, "uploader", "Unknown")
        views = getattr(media, "views", "0")
        duration = getattr(media, "duration", "0:00")

        raw_path = os.path.join(thumb_dir, f"{media_id}_raw.jpg")
        await self.save_thumb(raw_path, thumb_url)
        cover_img = Image.open(raw_path)

        total_sec = self.duration_to_seconds(duration)
        subtitle = f"{channel}  •  {views} views"

        result = self.compose(cover_img, title, subtitle, current_sec, total_sec)

        output_path = output_path or os.path.join(thumb_dir, f"{media_id}.png")
        result.save(output_path)
        return output_path
