import os
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

# Everything is drawn at 2x and downsampled with LANCZOS at the very end —
# this is what gives crisp, anti-aliased edges on the rounded card, badges
# and icons instead of the slightly jagged look of drawing at 1x.
SCALE = 2
FINAL_SIZE = (1280, 720)
CANVAS_SIZE = (FINAL_SIZE[0] * SCALE, FINAL_SIZE[1] * SCALE)
W, H = CANVAS_SIZE


def S(v):
    """Scale a size / coordinate / 4-tuple box by SCALE."""
    if isinstance(v, (tuple, list)):
        return tuple(S(x) for x in v)
    return v * SCALE


# --- Glass card panel (matches the reference "YouTube share card" size,
#     760x545 on a 1280x720 base canvas) ---
CARD_BOX = S((260, 90, 1020, 635))
CARD_RADIUS = S(34)

# --- Widescreen thumbnail inside the card (542x271 on the base canvas) ---
THUMB_BOX = S((368, 125, 910, 396))
THUMB_RADIUS = S(16)

# --- Text (title / subtitle) sits directly under the thumbnail,
#     left-aligned with it ---
TITLE_Y = S(415)
SUBTITLE_Y = S(452)

# --- Progress bar spans the same width as the thumbnail ---
BAR_X0, BAR_X1 = THUMB_BOX[0], THUMB_BOX[2]
BAR_Y = S(500)
BAR_H = S(6)
TIME_Y = BAR_Y + S(20)

# --- Transport controls (shuffle / prev / play / next / repeat) ---
CONTROLS_Y = BAR_Y + S(80)

# --- Palette ---
COL_BG_BASE = (10, 8, 6)
COL_TITLE = (22, 20, 18)
COL_SUBTITLE_MUTED = (95, 90, 85)
COL_WHITE = (255, 255, 255)
COL_DARK_ICON = (30, 28, 26)
GOLD = (223, 178, 110)
TRACK_BG = (210, 206, 200)
ACCENT_FALLBACK = (230, 40, 60)


class Thumbnail:
    def __init__(self):
        base = "auro/helpers"
        self.title_font_path = f"{base}/Poppins-ExtraBold.ttf"
        self.subtitle_font_path = f"{base}/Raleway-Bold.ttf"
        self.font_subtitle = ImageFont.truetype(self.subtitle_font_path, S(22))
        self.font_time = ImageFont.truetype(self.subtitle_font_path, S(18))
        self.font_badge = ImageFont.truetype(self.subtitle_font_path, S(20))
        self.font_badge_sub = ImageFont.truetype(self.subtitle_font_path, S(13))

    # ---------- generic helpers ----------

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

    def fit_title_font(self, draw, text, max_width, base_size, min_size):
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

    def accent_from_cover(self, cover_img):
        """Pulls a vivid, legible accent color out of the cover art so the
        progress bar / play button feel designed around the track instead
        of a fixed generic color."""
        small = cover_img.convert("RGB").resize((60, 60))
        quant = small.quantize(colors=6, method=Image.MEDIANCUT)
        palette = quant.getpalette()[: 6 * 3]
        counts = sorted(quant.getcolors() or [], key=lambda c: -c[0])

        if counts:
            _, idx = counts[0]
            r, g, b = palette[idx * 3: idx * 3 + 3]
        else:
            r, g, b = ACCENT_FALLBACK

        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        s = min(max(s, 0.55), 0.85)
        v = min(max(v, 0.55), 0.8)
        rr, gg, bb = colorsys.hsv_to_rgb(h, s, v)
        return (int(rr * 255), int(gg * 255), int(bb * 255))

    def glass_patch(self, canvas, box, radius, blur=20, brighten=1.12,
                     tint_alpha=26, tint_color=(20, 17, 13),
                     outline_color=(150, 130, 100, 90)):
        """Crops/blurs the canvas behind `box` and returns a rounded,
        semi-transparent 'frosted glass' layer to alpha-composite in."""
        x0, y0, x1, y1 = box
        pad = blur
        px0, py0 = max(int(x0 - pad), 0), max(int(y0 - pad), 0)
        px1, py1 = min(int(x1 + pad), canvas.width), min(int(y1 + pad), canvas.height)
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
            (x0, y0, x1, y1), radius=radius, outline=outline_color, width=max(1, S(1) // 2),
            fill=(*tint_color, tint_alpha),
        )
        out.alpha_composite(tint)
        return out

    def glass_sheen(self, box, radius):
        """A soft diagonal light streak across the top of the card — the
        detail that sells 'glass' rather than just 'translucent panel'."""
        x0, y0, x1, y1 = box
        layer = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        sheen = Image.new("L", CANVAS_SIZE, 0)
        sd = ImageDraw.Draw(sheen)
        band_w = (x1 - x0) * 0.55
        sd.polygon(
            [
                (x0, y0),
                (x0 + band_w, y0),
                (x0 + band_w * 0.35, y0 + (y1 - y0) * 0.62),
                (x0, y0 + (y1 - y0) * 0.62),
            ],
            fill=70,
        )
        sheen = sheen.filter(ImageFilter.GaussianBlur(S(18)))
        white = Image.new("RGBA", CANVAS_SIZE, (255, 255, 255, 255))
        layer = Image.composite(white, layer, sheen)

        mask = Image.new("L", CANVAS_SIZE, 0)
        ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=255)
        out = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        out.paste(layer, (0, 0), mask)
        return out

    # ---------- background ----------

    def build_background(self, cover_img):
        """Colorful ambient 'aura' background — instead of one uniform
        blur, sample a small grid of colors from the cover art and paint
        each as a big soft glowing blob at roughly its own position, then
        blend that over a heavier blur of the full image. This is what
        gives the distinct, multi-hued blurred-light look (like Spotify
        Canvas / YouTube's ambient mode) rather than a flat wash."""
        cover_rgb = cover_img.convert("RGB")

        # base: a strong, dim blur of the whole image so there's no
        # visible seams between blobs
        base = self.fit_image(cover_rgb, CANVAS_SIZE)
        base = base.filter(ImageFilter.GaussianBlur(S(80)))
        base = ImageEnhance.Brightness(base).enhance(0.42)
        base = ImageEnhance.Color(base).enhance(1.2)
        bg = Image.blend(Image.new("RGB", CANVAS_SIZE, COL_BG_BASE), base, 0.9).convert("RGBA")

        # blobs: sample a coarse grid of dominant-ish colors and splash
        # each one as a soft radial blob near its source position
        grid = 5
        small = cover_rgb.resize((grid, grid), Image.Resampling.BILINEAR)
        pixels = small.load()

        blob_layer = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        for gy in range(grid):
            for gx in range(grid):
                r, g, b = pixels[gx, gy]
                # skip near-black/near-white cells so blobs stay colorful
                mx, mn = max(r, g, b), min(r, g, b)
                if mx < 40 or mn > 235:
                    continue
                px = int((gx + 0.5) / grid * W)
                py = int((gy + 0.5) / grid * H)
                radius = int(min(W, H) * 0.28)
                blob = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
                ImageDraw.Draw(blob).ellipse(
                    (px - radius, py - radius, px + radius, py + radius),
                    fill=(r, g, b, 150),
                )
                blob = blob.filter(ImageFilter.GaussianBlur(S(55)))
                blob_layer = Image.alpha_composite(blob_layer, blob)

        bg.alpha_composite(blob_layer)
        bg = ImageEnhance.Brightness(bg.convert("RGB")).enhance(0.9).convert("RGBA")
        return bg

    # ---------- glass card ----------

    def draw_ambient_glow(self, canvas, accent):
        """A soft, large colored glow bleeding out from behind the card,
        tinted with the track's accent color — the kind of ambient light
        premium album-art UIs use to feel 'designed around the art'."""
        x0, y0, x1, y1 = CARD_BOX
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        glow = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        rw, rh = (x1 - x0) * 0.75, (y1 - y0) * 0.7
        gd.ellipse((cx - rw, cy - rh, cx + rw, cy + rh), fill=(*accent, 90))
        glow = glow.filter(ImageFilter.GaussianBlur(S(70)))
        canvas.alpha_composite(glow)

    def draw_card_shadow(self, canvas):
        """Soft ambient shadow beneath the whole card so it reads as a
        lifted object floating over the background, not a flat sticker."""
        x0, y0, x1, y1 = CARD_BOX
        shadow = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle(
            (x0 + S(6), y0 + S(22), x1 + S(6), y1 + S(22)),
            radius=CARD_RADIUS, fill=(0, 0, 0, 130),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(S(28)))
        canvas.alpha_composite(shadow)

    def draw_glass_card(self, canvas, accent):
        """Big frosted-glass panel behind everything, sized/positioned to
        match the reference share-card exactly. Translucent tint keeps the
        blurred background visible through it, like real glass, and a
        soft sheen + hairline border sell the material."""
        self.draw_ambient_glow(canvas, accent)
        self.draw_card_shadow(canvas)
        glass = self.glass_patch(
            canvas, CARD_BOX, radius=CARD_RADIUS, blur=S(30), brighten=1.5,
            tint_alpha=108, tint_color=(255, 255, 255),
            outline_color=(255, 255, 255, 170),
        )
        canvas.alpha_composite(glass)
        canvas.alpha_composite(self.glass_sheen(CARD_BOX, CARD_RADIUS))

    # ---------- thumbnail ----------

    def build_thumbnail(self, cover_img):
        x0, y0, x1, y1 = THUMB_BOX
        w, h = x1 - x0, y1 - y0
        art = self.fit_image(cover_img.convert("RGB"), (w, h)).convert("RGBA")
        art = self.add_round_corners(art, THUMB_RADIUS)

        # cinematic dark gradient across the bottom third — badges sit on
        # real contrast instead of relying only on their own pill fill
        grad = Image.new("L", (w, h), 0)
        gd = ImageDraw.Draw(grad)
        fade_start = int(h * 0.55)
        for yy in range(fade_start, h):
            t = (yy - fade_start) / max(h - fade_start - 1, 1)
            gd.line((0, yy, w, yy), fill=int(130 * t))
        shade = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        shade.putalpha(grad)
        art.alpha_composite(shade)

        outline = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(outline).rounded_rectangle(
            (0, 0, w - 1, h - 1), radius=THUMB_RADIUS, outline=(0, 0, 0, 35), width=max(1, S(1) // 2)
        )
        art.alpha_composite(outline)

        shadow = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle(
            (x0 + S(4), y0 + S(10), x1 - S(4), y1 + S(10)), radius=THUMB_RADIUS, fill=(0, 0, 0, 75)
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(S(12)))

        return art, shadow

    def draw_thumb_badges(self, canvas, views_label, quality_label):
        """Small pill badges on the bottom corners of the thumbnail — a
        views counter (bottom-left) and a quality tag (bottom-right),
        with a subtle top-to-bottom gradient instead of flat black."""
        draw = ImageDraw.Draw(canvas, "RGBA")
        tx0, ty0, tx1, ty1 = THUMB_BOX
        pad = S(10)

        def pill(x0, y0, w, h):
            grad = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
            gd = ImageDraw.Draw(grad)
            for yy in range(int(h)):
                t = yy / max(h - 1, 1)
                alpha = int(150 + 40 * t)
                gd.line((0, yy, w, yy), fill=(0, 0, 0, alpha))
            mask = Image.new("L", (int(w), int(h)), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=h / 2, fill=255)
            out = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
            out.paste(grad, (0, 0), mask)
            canvas.alpha_composite(out, (int(x0), int(y0)))

        if views_label:
            bbox = draw.textbbox((0, 0), views_label, font=self.font_badge)
            bw, bh = bbox[2] - bbox[0] + S(26), bbox[3] - bbox[1] + S(16)
            bx0, by0 = tx0 + pad, ty1 - pad - bh
            pill(bx0, by0, bw, bh)
            draw.text((bx0 + S(13), by0 + S(8)), views_label, font=self.font_badge, fill=COL_WHITE)

        if quality_label:
            bbox = draw.textbbox((0, 0), quality_label, font=self.font_badge_sub)
            bw, bh = bbox[2] - bbox[0] + S(22), bbox[3] - bbox[1] + S(12)
            bx1, by0 = tx1 - pad, ty1 - pad - bh
            bx0 = bx1 - bw
            pill(bx0, by0, bw, bh)
            draw.text((bx0 + S(11), by0 + S(6)), quality_label, font=self.font_badge_sub, fill=COL_WHITE)

    # ---------- title / subtitle ----------

    def draw_title_subtitle(self, canvas, title, subtitle):
        draw = ImageDraw.Draw(canvas, "RGBA")
        title = self.truncate(title, 46)
        font_t = self.fit_title_font(draw, title, BAR_X1 - BAR_X0, base_size=S(30), min_size=S(18))
        draw.text((BAR_X0, TITLE_Y), title, font=font_t, fill=COL_TITLE)
        draw.text((BAR_X0, SUBTITLE_Y), self.truncate(subtitle, 60), font=self.font_subtitle, fill=COL_SUBTITLE_MUTED)

    # ---------- progress bar ----------

    def draw_progress_bar(self, canvas, current_sec, total_sec, accent):
        draw = ImageDraw.Draw(canvas, "RGBA")
        width = BAR_X1 - BAR_X0
        ratio = 0 if total_sec <= 0 else min(current_sec / total_sec, 1.0)
        handle_x = BAR_X0 + width * ratio

        draw.rounded_rectangle(
            (BAR_X0, BAR_Y, BAR_X1, BAR_Y + BAR_H), radius=BAR_H // 2, fill=TRACK_BG
        )
        if handle_x > BAR_X0:
            draw.rounded_rectangle(
                (BAR_X0, BAR_Y, handle_x, BAR_Y + BAR_H), radius=BAR_H // 2, fill=accent
            )

        # soft glow behind the knob, then a crisp white knob on top —
        # a small touch that reads as "polished" rather than flat
        knob_r = S(7)
        glow = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse(
            (handle_x - knob_r * 2, BAR_Y + BAR_H / 2 - knob_r * 2,
             handle_x + knob_r * 2, BAR_Y + BAR_H / 2 + knob_r * 2),
            fill=(*accent, 120),
        )
        glow = glow.filter(ImageFilter.GaussianBlur(S(6)))
        canvas.alpha_composite(glow)
        draw.ellipse(
            (handle_x - knob_r, BAR_Y + BAR_H / 2 - knob_r,
             handle_x + knob_r, BAR_Y + BAR_H / 2 + knob_r),
            fill=COL_WHITE, outline=accent, width=max(1, S(1) // 2),
        )

        draw.text((BAR_X0, TIME_Y), self.fmt_time(current_sec), font=self.font_time, fill=COL_SUBTITLE_MUTED)
        remaining = self.fmt_time(total_sec) if total_sec > 0 else "LIVE"
        bbox = draw.textbbox((0, 0), remaining, font=self.font_time)
        rw = bbox[2] - bbox[0]
        draw.text((BAR_X1 - rw, TIME_Y), remaining, font=self.font_time, fill=COL_SUBTITLE_MUTED)

    # ---------- transport controls (shuffle / prev / play / next / repeat) ----------

    def draw_shuffle_icon(self, draw, cx, cy, size, color):
        r = size / 2
        w = max(1, S(1))
        draw.line((cx - r, cy - r * 0.5, cx + r, cy + r * 0.5), fill=color, width=w)
        draw.line((cx - r, cy + r * 0.5, cx + r, cy - r * 0.5), fill=color, width=w)
        tip = S(6)
        draw.polygon([(cx + r, cy - r * 0.5 - S(4)), (cx + r, cy - r * 0.5 + S(4)), (cx + r + tip, cy - r * 0.5)], fill=color)
        draw.polygon([(cx + r, cy + r * 0.5 - S(4)), (cx + r, cy + r * 0.5 + S(4)), (cx + r + tip, cy + r * 0.5)], fill=color)

    def draw_repeat_icon(self, draw, cx, cy, size, color):
        r = size / 2
        w = max(1, S(1))
        draw.arc((cx - r, cy - r, cx + r, cy + r), 200, 340, fill=color, width=w)
        draw.arc((cx - r, cy - r, cx + r, cy + r), 20, 160, fill=color, width=w)
        draw.polygon([(cx + r - S(2), cy - r * 0.35), (cx + r + S(6), cy - r * 0.35), (cx + r + S(2), cy - r * 0.75)], fill=color)
        draw.polygon([(cx - r + S(2), cy + r * 0.35), (cx - r - S(6), cy + r * 0.35), (cx - r - S(2), cy + r * 0.75)], fill=color)

    def draw_double_triangle(self, draw, cx, cy, size, color, direction):
        offset = size * 0.55
        for i in (-1, 1):
            x0 = cx + i * offset * direction
            if direction == 1:
                pts = [(x0 - size / 2, cy - size / 2), (x0 - size / 2, cy + size / 2), (x0 + size / 2, cy)]
            else:
                pts = [(x0 + size / 2, cy - size / 2), (x0 + size / 2, cy + size / 2), (x0 - size / 2, cy)]
            draw.polygon(pts, fill=color)

    def draw_play_pause(self, canvas, cx, cy, is_playing, accent, size):
        r = size / 2
        pad = S(8)
        # soft drop shadow under the button for a lifted, premium feel
        shadow = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        ImageDraw.Draw(shadow).ellipse(
            (cx - r - pad, cy - r - pad + S(4), cx + r + pad, cy + r + pad + S(4)), fill=(0, 0, 0, 100)
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(S(8)))
        canvas.alpha_composite(shadow)

        draw = ImageDraw.Draw(canvas, "RGBA")
        # subtle radial gradient fill (lighter center, deeper edge) instead
        # of a flat color disc — small detail that reads as "designed"
        btn_size = int((r + pad) * 2)
        btn = Image.new("RGBA", (btn_size, btn_size), (0, 0, 0, 0))
        bd = ImageDraw.Draw(btn)
        light = tuple(min(255, int(c * 1.25) + 20) for c in accent)
        for i in range(btn_size // 2, 0, -1):
            t = i / (btn_size / 2)
            col = tuple(int(light[k] * t + accent[k] * (1 - t)) for k in range(3))
            bd.ellipse((btn_size / 2 - i, btn_size / 2 - i, btn_size / 2 + i, btn_size / 2 + i), fill=col)
        canvas.alpha_composite(btn, (int(cx - btn_size / 2), int(cy - btn_size / 2)))
        if is_playing:
            bar_w, gap, h = S(5), S(6), size * 0.7
            draw.rounded_rectangle((cx - gap / 2 - bar_w, cy - h / 2, cx - gap / 2, cy + h / 2), radius=S(2), fill=COL_WHITE)
            draw.rounded_rectangle((cx + gap / 2, cy - h / 2, cx + gap / 2 + bar_w, cy + h / 2), radius=S(2), fill=COL_WHITE)
        else:
            s = size * 0.55
            draw.polygon([(cx - s / 2 + S(2), cy - s / 2), (cx - s / 2 + S(2), cy + s / 2), (cx + s / 2 + S(2), cy)], fill=COL_WHITE)

    def draw_transport_controls(self, canvas, is_playing, accent):
        draw = ImageDraw.Draw(canvas, "RGBA")
        cy = CONTROLS_Y
        span = BAR_X1 - BAR_X0
        positions = [BAR_X0 + span * f for f in (0.0, 0.24, 0.5, 0.76, 1.0)]
        icon_color = COL_DARK_ICON

        self.draw_shuffle_icon(draw, positions[0], cy, S(18), icon_color)
        self.draw_double_triangle(draw, positions[1], cy, S(20), icon_color, direction=-1)
        self.draw_play_pause(canvas, positions[2], cy, is_playing, accent, S(26))
        self.draw_double_triangle(draw, positions[3], cy, S(20), icon_color, direction=1)
        self.draw_repeat_icon(draw, positions[4], cy, S(18), icon_color)

    def apply_grain(self, canvas, opacity=10):
        """Very subtle film grain over the whole frame — the kind of
        texture that keeps a flat digital render from looking sterile."""
        import random
        w, h = canvas.size
        small_w, small_h = w // 3, h // 3
        noise = Image.new("L", (small_w, small_h))
        rnd = random.Random(7)
        noise.putdata([rnd.randint(0, 255) for _ in range(small_w * small_h)])
        noise = noise.resize((w, h), Image.Resampling.BILINEAR)
        grain = Image.new("RGBA", (w, h), (128, 128, 128, 0))
        grain.putalpha(noise.point(lambda p: opacity))
        canvas.alpha_composite(grain)

    # ---------- full compose ----------

    def compose(
        self,
        cover_img,
        title: str,
        subtitle: str,
        current_sec: int,
        total_sec: int,
        views_label: str = "",
        quality_label: str = "HD",
        is_playing: bool = True,
    ):
        canvas = self.build_background(cover_img)
        accent = self.accent_from_cover(cover_img)

        self.draw_glass_card(canvas, accent)

        thumb, thumb_shadow = self.build_thumbnail(cover_img)
        canvas.alpha_composite(thumb_shadow)
        canvas.alpha_composite(thumb, THUMB_BOX[:2])
        self.draw_thumb_badges(canvas, views_label, quality_label)

        self.draw_title_subtitle(canvas, title, subtitle)
        self.draw_progress_bar(canvas, current_sec, total_sec, accent)
        self.draw_transport_controls(canvas, is_playing, accent)
        self.apply_grain(canvas, opacity=8)

        # downsample from 2x render to the final delivered size — this is
        # what removes jagged edges from every rounded rect / circle / arc
        return canvas.convert("RGB").resize(FINAL_SIZE, Image.Resampling.LANCZOS)

    # ---------- entry point ----------
    # kept as `generate` — this is the method name the rest of the
    # codebase calls (see anony/core/calls.py: `await thumb.generate(media)`)

    async def generate(self, media: Track, current_sec: int = 0, output_path: str = None) -> str:
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
        subtitle = f"{channel} | {views} views"
        views_label = f"{views}" if views else ""

        result = self.compose(
            cover_img,
            title,
            subtitle,
            current_sec,
            total_sec,
            views_label=views_label,
            quality_label="HD",
            is_playing=True,
        )

        output_path = output_path or os.path.join(thumb_dir, f"{media_id}.jpg")
        result.save(output_path, quality=95)
        return output_path
