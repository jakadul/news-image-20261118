"""The front page renderer for THE WORLD, Wednesday 18 November 2026.

Deterministic by construction: no randomness, no clock, no network, no
environment lookups.  The layout is expressed in *design pixels* on a
1200 x 1600 page and painted on a canvas SS times larger, then downsampled
with a high quality filter, which is what makes the type read as printed.

The page sits on one grid: margins of 64 pixels give a 1072 pixel measure,
divided into three columns of exactly 340 pixels with 26 pixel gutters, so
the two vertical rules fall on x = 417 and x = 783.  The three-column band,
the deck / explainer split and the closing strip all hang from those lines,
and the foot rule is set so the bottom margin equals the side margins.

Composition is two-pass: the page is stacked once to measure its natural
depth, then the remaining space is shared out among five elastic gaps so the
closing strip lands exactly on the foot rule.  Nothing is guessed at.

Public API
----------
render_page(audit=None)   -> PIL.Image, RGB, 1200 x 1600
save_page(path, audit=None)
overruns(audit)           -> blocks wider than the column they sit in
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------------------------------
# page geometry and the grid
# --------------------------------------------------------------------------

PAGE_W = 1200
PAGE_H = 1600
SS = 2                                  # supersample factor

MARGIN_X = 64
MARGIN_TOP = 40

CONTENT_X0 = MARGIN_X
CONTENT_X1 = PAGE_W - MARGIN_X
CONTENT_W = CONTENT_X1 - CONTENT_X0     # 1072

COLUMNS_N = 3
COL_GUTTER = 26.0                       # clear space between two columns
COL_RULE = 1.0                          # the hairline that splits them
COL_W = (CONTENT_W - (COLUMNS_N - 1) * COL_GUTTER) / COLUMNS_N     # 340.0
COL_X = tuple(CONTENT_X0 + i * (COL_W + COL_GUTTER) for i in range(COLUMNS_N))
COL_RULE_X = tuple(x + COL_W + COL_GUTTER / 2.0 for x in COL_X[:-1])
SPAN2_W = 2 * COL_W + COL_GUTTER        # 706: columns one and two

FOOT_RULE = 1516.0                      # 1600 - 1516 - 8 = the 64px margin
FOOT_BASELINE = 1534.0
TARGET_END = FOOT_RULE - 22.0           # where the closing strip must finish

# --------------------------------------------------------------------------
# palette: newsprint cream, ink black, one spot red in two strengths
# --------------------------------------------------------------------------

PAPER = (245, 240, 226)
PAPER_FIELD = (251, 247, 236)
PANEL = (17, 18, 22)                    # the lead picture's deep-space black
PANEL_INK = (238, 232, 214)
PANEL_DIM = (152, 150, 144)
INK = (24, 22, 20)
INK_SOFT = (78, 73, 66)
RED = (150, 30, 28)                     # the lead only
RED_QUIET = (168, 74, 64)               # briefs and the closing strip

STAR_WARM = (250, 246, 230)
STAR_COOL = (206, 214, 234)
STAR_FAINT = (150, 152, 158)

# --------------------------------------------------------------------------
# type
# --------------------------------------------------------------------------

_FONT_DIRS = (
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/liberation",
    "/usr/local/share/fonts",
    "/usr/share/fonts/truetype/dejavu",
    "/System/Library/Fonts/Supplemental",
    "C:/Windows/Fonts",
)

_FONT_FILES = {
    ("serif", "regular"): ("LiberationSerif-Regular.ttf", "DejaVuSerif.ttf"),
    ("serif", "bold"): ("LiberationSerif-Bold.ttf", "DejaVuSerif-Bold.ttf"),
    ("serif", "italic"): ("LiberationSerif-Italic.ttf", "DejaVuSerif-Italic.ttf"),
    ("serif", "bolditalic"): ("LiberationSerif-BoldItalic.ttf", "DejaVuSerif-BoldItalic.ttf"),
    ("sans", "regular"): ("LiberationSans-Regular.ttf", "DejaVuSans.ttf"),
    ("sans", "bold"): ("LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf"),
    ("sans", "italic"): ("LiberationSans-Italic.ttf", "DejaVuSans-Italic.ttf"),
    ("narrow", "bold"): ("LiberationSansNarrow-Bold.ttf", "DejaVuSans-Bold.ttf"),
    ("narrow", "regular"): ("LiberationSansNarrow-Regular.ttf", "DejaVuSans.ttf"),
}


def _resolve_font(family: str, style: str) -> Optional[str]:
    """First existing candidate file for a family/style, or None."""
    names = _FONT_FILES.get((family, style), ())
    for directory in _FONT_DIRS:
        if not os.path.isdir(directory):
            continue
        for name in names:
            path = os.path.join(directory, name)
            if os.path.isfile(path):
                return path
    return None


class Type:
    """Font cache.  Sizes are design pixels; the face is built at SS x size."""

    def __init__(self, scale: int) -> None:
        self.scale = scale
        self._cache = {}

    def get(self, family: str, style: str, size: float) -> ImageFont.FreeTypeFont:
        px = max(1, int(round(size * self.scale)))
        key = (family, style, px)
        if key not in self._cache:
            path = _resolve_font(family, style)
            if path is None:
                font = ImageFont.load_default(px)
            else:
                font = ImageFont.truetype(path, px)
            self._cache[key] = font
        return self._cache[key]


# --------------------------------------------------------------------------
# canvas: draws in design pixels, paints in supersampled pixels
# --------------------------------------------------------------------------


class Canvas:
    def __init__(self, scale: int) -> None:
        self.scale = scale
        self.image = Image.new("RGB", (PAGE_W * scale, PAGE_H * scale), PAPER)
        self.draw = ImageDraw.Draw(self.image)
        self.type = Type(scale)

    # -- geometry ---------------------------------------------------------

    def _s(self, value: float) -> float:
        return value * self.scale

    def _px(self, width: float) -> int:
        return max(1, int(round(width * self.scale)))

    # -- rules ------------------------------------------------------------

    def rule(self, x0: float, y0: float, x1: float, y1: float,
             width: float = 1.0, fill=INK) -> None:
        self.draw.line(
            [self._s(x0), self._s(y0), self._s(x1), self._s(y1)],
            fill=fill, width=self._px(width))

    def dashed(self, x0: float, y0: float, x1: float, y1: float,
               dash: float = 7.0, gap: float = 5.0,
               width: float = 1.4, fill=INK) -> None:
        total = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        if total <= 0:
            return
        ux, uy = (x1 - x0) / total, (y1 - y0) / total
        pos = 0.0
        while pos < total:
            end = min(pos + dash, total)
            self.draw.line(
                [self._s(x0 + ux * pos), self._s(y0 + uy * pos),
                 self._s(x0 + ux * end), self._s(y0 + uy * end)],
                fill=fill, width=self._px(width))
            pos = end + gap

    def rect(self, x0, y0, x1, y1, fill=None, outline=None,
             width: float = 1.0) -> None:
        self.draw.rectangle(
            [self._s(x0), self._s(y0), self._s(x1), self._s(y1)],
            fill=fill, outline=outline, width=self._px(width))

    def ellipse(self, x0, y0, x1, y1, outline=None, fill=None,
                width: float = 1.0) -> None:
        self.draw.ellipse(
            [self._s(x0), self._s(y0), self._s(x1), self._s(y1)],
            outline=outline, fill=fill, width=self._px(width))

    def polygon(self, points: Sequence[Tuple[float, float]], outline=INK,
                fill=None, width: float = 1.0) -> None:
        pts = [(self._s(x), self._s(y)) for x, y in points]
        self.draw.polygon(pts, outline=outline, fill=fill)
        if fill is None:
            self.draw.line(list(pts) + [pts[0]], fill=outline,
                           width=self._px(width), joint="curve")

    def dot(self, cx: float, cy: float, r: float, fill=INK) -> None:
        self.draw.ellipse(
            [self._s(cx - r), self._s(cy - r), self._s(cx + r), self._s(cy + r)],
            fill=fill)

    def ring(self, cx: float, cy: float, r: float, width: float = 1.4,
             fill=INK) -> None:
        self.draw.ellipse(
            [self._s(cx - r), self._s(cy - r), self._s(cx + r), self._s(cy + r)],
            outline=fill, width=self._px(width))

    # -- measuring --------------------------------------------------------

    def width(self, text: str, font: ImageFont.FreeTypeFont) -> float:
        return self.draw.textlength(text, font=font) / self.scale

    def advance(self, ch: str, font) -> float:
        return self.draw.textlength(ch, font=font) / self.scale

    def tracked_width(self, text: str, font, tracking: float,
                      word_extra: float = 0.0) -> float:
        if not text:
            return 0.0
        total = 0.0
        for i, ch in enumerate(text):
            total += self.advance(ch, font)
            if i:
                total += word_extra if text[i - 1] == " " else tracking
        return total

    def cap_height(self, font) -> float:
        box = self.draw.textbbox((0, 0), "H", font=font, anchor="ls")
        return -box[1] / self.scale

    def ascent(self, font) -> float:
        return font.getmetrics()[0] / self.scale

    def descent(self, font) -> float:
        return font.getmetrics()[1] / self.scale

    # -- drawing text -----------------------------------------------------

    def text(self, x: float, y: float, text: str, font, fill=INK,
             anchor: str = "ls") -> None:
        self.draw.text((self._s(x), self._s(y)), text, font=font, fill=fill,
                       anchor=anchor)

    def tracked(self, x: float, y: float, text: str, font, tracking: float,
                fill=INK, anchor: str = "ls", word_extra: float = 0.0) -> float:
        """Letterspaced text on a baseline.  Returns the width used."""
        if not text:
            return 0.0
        total = self.tracked_width(text, font, tracking, word_extra)
        if anchor[0] == "m":
            cursor = x - total / 2.0
        elif anchor[0] == "r":
            cursor = x - total
        else:
            cursor = x
        for i, ch in enumerate(text):
            if ch != " ":
                self.draw.text((self._s(cursor), self._s(y)), ch, font=font,
                               fill=fill, anchor="ls")
            cursor += self.advance(ch, font)
            if i + 1 < len(text):
                cursor += word_extra if ch == " " else tracking
        return total

    def justify(self, x0: float, x1: float, y: float, text: str, font,
                fill=INK, word_extra_ratio: float = 0.06) -> float:
        """Set text so its tracked width is exactly x1 - x0.

        The tracking is solved rather than guessed, so the nameplate is flush
        to the measure on both sides rather than near it.
        """
        target = x1 - x0
        gaps = len(text) - 1
        if gaps <= 0:
            self.text(x0, y, text, font, fill=fill)
            return target
        natural = self.width(text, font)
        word_extra = word_extra_ratio * (natural / max(1, len(text)))
        fixed = text.count(" ") * word_extra
        track = (target - natural - fixed) / gaps
        self.tracked(x0, y, text, font, track, fill=fill, word_extra=word_extra)
        return target

    # -- wrapping ---------------------------------------------------------

    def wrap(self, text: str, font, max_w: float) -> List[str]:
        """Greedy wrap measured in pixels, never in characters."""
        words = text.split()
        lines: List[str] = []
        current = ""
        for word in words:
            trial = word if not current else current + " " + word
            if self.width(trial, font) <= max_w or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    def wrap_balanced(self, text: str, font, max_w: float) -> List[str]:
        """A wrap that refuses to leave a single word alone on the last line."""
        lines = self.wrap(text, font, max_w)
        if len(lines) < 2:
            return lines
        last = lines[-1].split()
        if len(last) == 1:
            prev = lines[-2].split()
            if len(prev) > 1:
                moved = prev[-1]
                trial_prev = " ".join(prev[:-1])
                trial_last = moved + " " + lines[-1]
                if (self.width(trial_prev, font) <= max_w
                        and self.width(trial_last, font) <= max_w):
                    lines[-2] = trial_prev
                    lines[-1] = trial_last
        return lines

    def wrap_even(self, text: str, font, max_widths: Sequence[float],
                  n_lines: int) -> List[str]:
        """Set text over exactly n_lines lines with the ragging evened out.

        The greedy wrap leaves whatever is left on the last line, which is how
        a brief ends on a single word.  This solves the break points so the
        slack is shared between the lines instead: it minimises the sum of the
        squared shortfalls against each line's own measure, and forbids a
        one-word last line when there is more than one line to fill.
        """
        words = text.split()
        n = len(words)
        if n_lines < 2 or n < 2:
            return self.wrap(text, font, max_widths[0])

        space = self.width(" ", font)
        wide = [[0.0] * (n + 1) for _ in range(n)]
        for i in range(n):
            acc = 0.0
            for j in range(i + 1, n + 1):
                acc += self.width(words[j - 1], font)
                if j - 1 > i:
                    acc += space
                wide[i][j] = acc

        inf = float("inf")
        best = [[inf] * (n + 1) for _ in range(n_lines + 1)]
        back = [[-1] * (n + 1) for _ in range(n_lines + 1)]
        best[0][0] = 0.0
        for k in range(1, n_lines + 1):
            limit = max_widths[min(k - 1, len(max_widths) - 1)]
            for j in range(1, n + 1):
                for i in range(j - 1, -1, -1):
                    if wide[i][j] > limit:
                        break
                    if best[k - 1][i] == inf:
                        continue
                    slack = limit - wide[i][j]
                    penalty = 0.0
                    if k == n_lines and j == n and (j - i) < 2 and n > 2:
                        penalty = 1.0e7
                    cost = best[k - 1][i] + slack * slack + penalty
                    if cost < best[k][j]:
                        best[k][j] = cost
                        back[k][j] = i
        if best[n_lines][n] == inf:
            return self.wrap(text, font, max_widths[0])

        lines: List[str] = []
        j = n
        for k in range(n_lines, 0, -1):
            i = back[k][j]
            lines.append(" ".join(words[i:j]))
            j = i
        lines.reverse()
        return lines

    def fit_lines(self, text: str, family: str, style: str, max_w: float,
                  lines_wanted: int, lo: float, hi: float,
                  step: float = 0.25):
        """Largest size whose balanced wrap makes exactly lines_wanted lines."""
        size = hi
        while size >= lo:
            font = self.type.get(family, style, size)
            lines = self.wrap_balanced(text, font, max_w)
            if len(lines) == lines_wanted:
                return size, lines
            size -= step
        fallback = self.wrap_balanced(text, self.type.get(family, style, lo),
                                      max_w)
        return lo, fallback

    def fit_balanced(self, text: str, family: str, style: str, measure: float,
                     lines_wanted: int, lo: float, hi: float,
                     max_fill: float = 0.95, min_fill: float = 0.55):
        """Largest-and-fullest wrap: no line crowds the measure, none is a stub.

        Every size that yields exactly lines_wanted lines within
        max_fill * measure is scored by the fill of its shortest line, and the
        fullest wins.  That is what stops a headline running a line to within
        a few pixels of the trim while leaving a widow under it.
        """
        best = None
        size = lo
        while size <= hi:
            font = self.type.get(family, style, size)
            lines = self.wrap_balanced(text, font, measure * max_fill)
            if len(lines) == lines_wanted:
                widths = [self.width(line, font) for line in lines]
                if max(widths) <= measure * max_fill:
                    fill = min(widths) / measure
                    if fill >= min_fill and (best is None or fill > best[2]):
                        best = (size, lines, fill)
            size += 0.25
        if best is not None:
            return best[0], best[1]
        return self.fit_lines(text, family, style, measure * max_fill,
                              lines_wanted, lo, hi)

    def fit_one_line(self, text: str, family: str, style: str, measure: float,
                     lo: float, hi: float, max_fill: float = 0.97):
        """Largest size at which the text still sets on a single line."""
        best_size = lo
        size = lo
        while size <= hi:
            if self.width(text, self.type.get(family, style, size)) \
                    <= measure * max_fill:
                best_size = size
                size += 0.25
            else:
                break
        return best_size, self.type.get(family, style, best_size)

    def fit_tracked(self, text: str, family: str, style: str, target: float,
                    tracking_ratio: float, lo: float = 20.0, hi: float = 260.0,
                    word_extra_ratio: float = 0.0):
        """Largest size whose tracked width fits target."""
        best_font = self.type.get(family, style, lo)
        best_track = tracking_ratio * lo
        best_word = word_extra_ratio * lo
        size = lo
        while size <= hi:
            font = self.type.get(family, style, size)
            track = tracking_ratio * size
            word = word_extra_ratio * size
            if self.tracked_width(text, font, track, word) <= target:
                best_font, best_track, best_word = font, track, word
                size += 0.25
            else:
                break
        return best_font, best_track, best_word


# --------------------------------------------------------------------------
# the copy: wire register, factual, no exclamation marks
# --------------------------------------------------------------------------

LAUNCH_YEAR = 1977
DATELINE_YEAR = 2026
YEARS_OUT = DATELINE_YEAR - LAUNCH_YEAR          # solved, never asserted

MASTHEAD = "THE WORLD"
DATELINE_LEFT = "WEDNESDAY, NOVEMBER 18, 2026"
DATELINE_CENTRE = "ONE LIGHT-DAY"
DATELINE_RIGHT = "Vol. XI \u00b7 No. 265"

WEATHER = ("WEATHER: NEW YORK 9\u00b0C OVERCAST \u00b7 LONDON 7\u00b0C RAIN "
           "\u00b7 MANILA 31\u00b0C STORMS")
MARKETS = ("MARKETS: S&P 500 5,842.10 +0.6% \u00b7 NASDAQ 19,204.55 +1.1% "
           "\u00b7 BRENT $81.44")

# the kicker carries no number the dateline can contradict
LEAD_KICKER = "DEEP SPACE \u00b7 %d YEARS OUT" % YEARS_OUT
LEAD_HEADLINE = ("Voyager 1 Becomes the First Thing Built by Humans to "
                 "Reach One Light-Day From Earth")
LEAD_STANDFIRST = "Forty-nine years out, it is farther than anything else we have built."
LEAD_DECK = (
    "The spacecraft is now 25.9 billion kilometres from Earth, or 173 "
    "astronomical units. Launched in 1977 on a mission planned to last five "
    "years, it is still transmitting from interstellar space, and its radio "
    "signal now takes a full day to reach the antennas on the ground that "
    "listen for it, on a plutonium supply that fades within a decade."
)
LEAD_EXPLAINER_LABEL = "EXPLAINER \u00b7 THE UNIT"
LEAD_EXPLAINER = (
    "A light-day is the distance light covers in 24 hours: 25.9 billion "
    "kilometres, or 173 times the Earth-Sun distance."
)
LEAD_BYLINE = "BY THE WORLD SCIENCE DESK"
LEAD_JUMP = "LIGHT-DAY EXPLAINER, PAGE 6"
PANEL_CAPTION = "VOYAGER 1 \u00b7 ARTIST'S IMPRESSION"
PANEL_CREDIT = "ILLUSTRATION: THE WORLD \u00b7 DATA: NASA / JPL"

SCHEMATIC_LEGEND_LEFT = ("DISTANCE FROM EARTH \u00b7 GRADUATIONS EVERY 20 AU "
                         "\u00b7 1 AU = 149.6 MILLION KM")
SCHEMATIC_LEGEND_RIGHT = "SOURCE: NASA / JET PROPULSION LABORATORY"

COLUMNS = (
    (
        "MANILA",
        "Trump Presses Supply Pact at ASEAN and Quad Summits",
        "President Trump attended the 49th ASEAN Summit and a Quad leaders "
        "meeting in Manila, pressing a supply-chain pact reported as Pax "
        "Silica. Thousands protested his arrival.",
    ),
    (
        "STRAIT OF HORMUZ",
        "Iran Claims Strike on US Radar as Gulf Tankers Burn",
        "Iran\u2019s Revolutionary Guard Corps said it hit a US radar at "
        "Sheikh Isa Air Base in Bahrain. Tankers caught fire in the strait, "
        "and a dirty-bomb threat was taken seriously.",
    ),
    (
        "SILICON VALLEY",
        "Nvidia Turmoil Turns Political; Earnings Lift the Nasdaq",
        "Nvidia\u2019s turmoil over CEO Jensen Huang turned political when "
        "Trump backed a campaign for his return, presuming an exit Nvidia has "
        "not announced. Earnings steadied markets.",
    ),
)
WIRE_CREDIT = "WIRE REPORTS"

STRIP_HEADING = "ALSO IN THIS EDITION"
STRIP_ITEMS = (
    ("FILM", "Robert Pattinson is named the new James Bond."),
    ("HEALTH", "World COPD Day 2026 presses for early diagnosis."),
    ("CRICKET", "M. S. Dhoni leaves the IPL to mentor Chennai Super Kings."),
)

FOOT_LEFT = "THE WORLD \u00b7 WEDNESDAY, NOVEMBER 18, 2026"
FOOT_RIGHT = "PAGE 1 \u00b7 CITY FINAL EDITION \u00b7 PRICE 3.50"

# --------------------------------------------------------------------------
# type scale (design pixels)
# --------------------------------------------------------------------------

SZ_DATUM = 11.0
SZ_DATELINE = 14.5
SZ_KICKER = 18.5
SZ_DECK = 19.0
SZ_EXPLAINER_LABEL = 11.0
SZ_BYLINE = 11.0
SZ_COL_KICKER = 13.0
SZ_COL_BODY = 16.5
SZ_WIRE = 10.5
SZ_STRIP_HEAD = 11.5
SZ_STRIP_TAG = 12.0
SZ_STRIP_ITEM = 16.0
SZ_FOOT = 11.0
SZ_PANEL_CAPTION = 11.0
SZ_GRAPHIC = 11.5
SZ_GRAPHIC_TICK = 10.0

TRACK_NAMEPLATE = 0.045
TRACK_SMALLCAPS = 0.14
TRACK_KICKER = 0.12
TRACK_TINY = 0.10

DECK_LEADING = 26.5
EXPLAINER_LEADING_RATIO = 1.28
COL_HEAD_LEADING = 29.0
COL_BODY_LEADING = 23.0
STRIP_LEADING = 22.0

PANEL_H = 196.0                         # the lead picture
SCHEMATIC_H = 150.0                     # the drawn scale graphic

# elastic gaps: base depth, then the share of slack each one absorbs
GAP_BASE: Dict[str, float] = {
    "masthead_lead": 22.0,
    "head_visual": 20.0,
    "visual_deck": 20.0,
    "deck_band": 30.0,
    "band_strip": 28.0,
}
GAP_WEIGHT: Dict[str, float] = {
    "masthead_lead": 0.7,
    "head_visual": 1.0,
    "visual_deck": 0.9,
    "deck_band": 1.3,
    "band_strip": 1.6,
}
GAP_FLOOR = 0.35      # a gap never shrinks below this share of its base
GAP_USES = {          # how many times each gap is applied down the page
    "masthead_lead": 1,
    "head_visual": 2,
    "visual_deck": 2,
    "deck_band": 1,
    "band_strip": 1,
}


# --------------------------------------------------------------------------
# sections
# --------------------------------------------------------------------------


def _datum(c: Canvas, audit: list) -> float:
    """The weather and market line: the page's first small type."""
    font = c.type.get("sans", "bold", SZ_DATUM)
    base = MARGIN_TOP + c.cap_height(font)
    left = c.tracked(CONTENT_X0, base, WEATHER, font, SZ_DATUM * TRACK_TINY,
                     fill=INK_SOFT)
    right = c.tracked(CONTENT_X1, base, MARKETS, font, SZ_DATUM * TRACK_TINY,
                      fill=INK_SOFT, anchor="rs")
    audit.append(("datum_row_w", left + right + 30, CONTENT_W))
    rule_y = base + c.descent(font) + 11
    c.rule(CONTENT_X0, rule_y, CONTENT_X1, rule_y, width=1.0)
    return rule_y


def _masthead(c: Canvas, y: float, audit: list) -> float:
    """Nameplate flush to the measure, with even air above and below."""
    air = 30.0

    probe = c.type.get("serif", "bold", 100.0)
    ratio = c.width(MASTHEAD, probe) / 100.0
    gaps = len(MASTHEAD) - 1
    size = min(CONTENT_W / (ratio + TRACK_NAMEPLATE * gaps), 176.0)
    font = c.type.get("serif", "bold", size)
    cap = c.cap_height(font)

    baseline = y + air + cap
    used = c.justify(CONTENT_X0, CONTENT_X1, baseline, MASTHEAD, font,
                     fill=INK, word_extra_ratio=0.02)
    audit.append(("nameplate_w", used, CONTENT_W))
    audit.append(("nameplate_size", size, 0.0))
    audit.append(("nameplate_air_above", air, 0.0))

    rule_y = baseline + air
    c.rule(CONTENT_X0, rule_y, CONTENT_X1, rule_y, width=1.4)

    # dateline strap: a clear x-height or more above and below the strap
    d_font = c.type.get("sans", "bold", SZ_DATELINE)
    d_cap = c.cap_height(d_font)
    d_x = c.draw.textbbox((0, 0), "x", font=d_font, anchor="ls")
    x_height = -d_x[1] / c.scale
    pad = 20.0
    d_base = rule_y + pad + d_cap
    c.tracked(CONTENT_X0, d_base, DATELINE_LEFT, d_font, SZ_DATELINE * TRACK_SMALLCAPS,
              fill=INK)
    c.tracked(PAGE_W / 2.0, d_base, DATELINE_CENTRE, d_font,
              SZ_DATELINE * TRACK_SMALLCAPS, fill=INK, anchor="ms")
    c.tracked(CONTENT_X1, d_base, DATELINE_RIGHT, d_font,
              SZ_DATELINE * TRACK_SMALLCAPS, fill=INK, anchor="rs")

    heavy = d_base + c.descent(d_font) + pad
    c.rule(CONTENT_X0, heavy, CONTENT_X1, heavy, width=3.0)
    audit.append(("dateline_clear_above", pad - x_height, 0.0))
    audit.append(("dateline_clear_below", pad - x_height, 0.0))
    return heavy


def _panel(c: Canvas, top: float, audit: list) -> float:
    """The lead picture: deep space, a starfield, Voyager drawn large."""
    x0, x1 = CONTENT_X0, CONTENT_X1
    bottom = top + PANEL_H
    c.rect(x0, top, x1, bottom, fill=PANEL, outline=INK, width=1.0)

    field_w = x1 - x0
    cx = x0 + field_w * 0.54
    cy = top + PANEL_H * 0.50
    s = 1.58

    # starfield: a low-discrepancy sequence, so it is dense, even and
    # identical on every run without a random number generator anywhere.
    # Stars are held out of the spacecraft's own area and out of the caption
    # band, so figure and ground separate and the credit stays legible.
    for i in range(240):
        fx = (i * 0.6180339887498949) % 1.0
        fy = (i * 0.7548776662466927) % 1.0
        fr = (i * 0.4142135623730951) % 1.0
        ft = (i * 0.7320508075688772) % 1.0
        sx = x0 + fx * field_w
        sy = top + fy * PANEL_H
        if sy > bottom - 32.0:
            continue
        if ((sx - cx) / 78.0) ** 2 + ((sy - cy) / 52.0) ** 2 < 1.0:
            continue
        if ft < 0.74:
            fill = STAR_WARM
        elif ft < 0.93:
            fill = STAR_COOL
        else:
            fill = STAR_FAINT
        c.dot(sx, sy, 0.40 + fr * 0.62, fill=fill)
    for i in range(9):
        fx = (i * 0.6180339887498949 + 0.31) % 1.0
        fy = (i * 0.7548776662466927 + 0.17) % 1.0
        sx = x0 + fx * field_w
        sy = top + 12 + fy * (PANEL_H - 24)
        if sy > bottom - 32.0:
            continue
        if ((sx - cx) / 78.0) ** 2 + ((sy - cy) / 52.0) ** 2 < 1.0:
            continue
        c.dot(sx, sy, 1.35, fill=STAR_WARM)
        c.ring(sx, sy, 2.9, width=0.6, fill=(78, 78, 76))

    # the spacecraft, at picture scale, in a heavier stroke than the stars so
    # that it reads as one object and not as a bright patch of the field
    _voyager(c, cx, cy, s, ink=(252, 249, 240), lw=1.7)

    cap_font = c.type.get("sans", "bold", SZ_PANEL_CAPTION)
    base = bottom - 15
    c.tracked(x0 + 16, base, PANEL_CAPTION, cap_font,
              SZ_PANEL_CAPTION * TRACK_SMALLCAPS, fill=PANEL_INK)
    c.tracked(x1 - 16, base, PANEL_CREDIT, cap_font,
              SZ_PANEL_CAPTION * TRACK_TINY, fill=PANEL_DIM, anchor="rs")
    audit.append(("panel_credit_w",
                  c.tracked_width(PANEL_CREDIT, cap_font,
                                  SZ_PANEL_CAPTION * TRACK_TINY) + 32,
                  CONTENT_W))
    return bottom


def _voyager(c: Canvas, cx: float, cy: float, s: float, ink=INK,
             lw: float = 1.2) -> None:
    """Voyager's real geometry in profile, at one stroke weight.

    A high-gain antenna with its feed horn and feed struts, the bus behind
    it, a science boom carrying the instrument cluster, a boom carrying the
    three radioisotope thermoelectric generators, and the long magnetometer
    boom trailing away.  Everything is in local units scaled by s, so the
    same drawing serves the big picture panel and the small scale graphic;
    that is what keeps the glyph from becoming a smudge.
    """
    def p(x, y):
        return cx + x * s, cy + y * s

    def seg(x0, y0, x1, y1, w=lw):
        a, b = p(x0, y0), p(x1, y1)
        c.rule(a[0], a[1], b[0], b[1], width=w, fill=ink)

    def ell(x0, y0, rx, ry, w=lw):
        X, Y = p(x0, y0)
        c.ellipse(X - rx * s, Y - ry * s, X + rx * s, Y + ry * s,
                  outline=ink, width=w)

    def box(x0, y0, x1, y1, w=lw):
        X0, Y0 = p(x0, y0)
        X1, Y1 = p(x1, y1)
        c.rect(X0, Y0, X1, Y1, outline=ink, width=w)

    # high-gain antenna: rim, bowl, feed horn, three feed struts
    ell(0, 0, 30, 20)
    ell(0, 4, 25, 15)
    seg(-26, 8, 0, 3)
    seg(26, 8, 0, 3)
    seg(0, -19, 0, 3)
    c.dot(*p(0, 3), r=2.4 * s, fill=ink)

    # the bus, a ten-sided body, seen as a cut-corner block
    c.polygon([p(14, 16), p(46, 16), p(52, 22), p(52, 32),
               p(46, 38), p(14, 38), p(8, 32), p(8, 22)],
              outline=ink, width=lw)

    # science boom, carrying the instrument cluster, away to the left
    seg(16, 34, -48, 54)
    box(-4, 31, 4, 38)
    box(-20, 37, -12, 44)
    box(-36, 43, -29, 49)

    # RTG boom, with three generators
    seg(48, 36, 96, 34)
    box(56, 26, 68, 38)
    box(70, 26, 82, 38)
    box(84, 26, 96, 38)

    # magnetometer boom, the longest element on the spacecraft
    seg(-8, 10, -98, -2, w=lw * 0.8)
    box(-46, 1, -41, 6, w=lw * 0.8)
    box(-88, -8, -83, -3, w=lw * 0.8)


def _schematic(c: Canvas, top: float, audit: list) -> float:
    """The measured scale graphic: Sun, Earth, Voyager, one light-day.

    One horizontal only.  From the Sun to the Earth the line is a dashed
    notional leader, cut by an axis break, because one astronomical unit
    inside a span of 173 cannot be drawn to the bar's scale.  From the Earth
    to the spacecraft the line *is* the bar: solid, capped at both ends,
    graduated every 20 AU and labelled 0 at its origin and 173 at its
    terminus, so the reading is closed at both ends instead of implied.  The
    bar's right cap lands on the spacecraft's own position and the leader
    stops at the same point, so the drawn span and the measured span are one
    length and not two.
    """
    x0, x1 = CONTENT_X0, CONTENT_X1
    bottom = top + SCHEMATIC_H
    c.rect(x0, top, x1, bottom, fill=PAPER_FIELD, outline=INK, width=1.0)
    pad = 14.0

    y = top + 56.0
    x_sun = x0 + 58.0
    x_break = x_sun + 74.0
    x_earth = x0 + 292.0
    x_voy = x1 - 104.0                     # the spacecraft's own position

    # the notional leader, cut by the break so the mark excises the line
    c.dashed(x_sun + 9.0, y, x_break - 7.0, y, dash=7, gap=5, width=1.0,
             fill=INK_SOFT)
    c.dashed(x_break + 16.0, y, x_earth, y, dash=7, gap=5, width=1.0,
             fill=INK_SOFT)
    for bx in (x_break + 2.0, x_break + 11.0):
        c.rule(bx - 3.0, y + 9.0, bx + 3.0, y - 9.0, width=1.2, fill=INK_SOFT)

    # every marker label on the same side of the line: above it
    lab = c.type.get("sans", "bold", SZ_GRAPHIC)
    tr = SZ_GRAPHIC * 0.16
    label_base = y - 22.0

    c.dot(x_sun, y, 9.0)
    c.tracked(x_sun, label_base, "SUN", lab, tr, fill=INK, anchor="ms")

    c.dot(x_earth, y, 4.5)
    c.tracked(x_earth, label_base, "EARTH", lab, tr, fill=INK, anchor="ms")

    _voyager(c, x_voy, y - 8.0, 0.58, ink=INK, lw=1.2)
    c.tracked(x_voy, label_base, "VOYAGER 1", lab, tr, fill=INK, anchor="ms")

    # the bar itself, from the Earth to the spacecraft's position
    span = x_voy - x_earth
    au_total = 173.0
    au_step = 20.0
    px_per_au = span / au_total

    c.rule(x_earth, y, x_voy, y, width=1.8)
    for cap_x in (x_earth, x_voy):
        c.rule(cap_x, y - 11.0, cap_x, y + 11.0, width=2.2)

    tick_font = c.type.get("sans", "bold", SZ_GRAPHIC_TICK)
    tick_tr = SZ_GRAPHIC_TICK * 0.04
    num_base = y + 40.0
    au = au_step
    while au < au_total:
        tx = x_earth + au * px_per_au
        major = abs(au % 40.0) < 0.01
        c.rule(tx, y, tx, y + (11.0 if major else 6.0),
               width=1.7 if major else 1.2,
               fill=INK if major else INK_SOFT)
        if major:
            c.tracked(tx, num_base, "%d" % int(au), tick_font, tick_tr,
                      fill=INK, anchor="ms")
        au += au_step

    # both ends of the scale carry a number, so the datum and the terminus
    # are stated rather than left to be inferred
    c.tracked(x_earth + 2.0, num_base, "0", tick_font, tick_tr, fill=INK)
    c.tracked(x_voy + 15.0, num_base, "173 AU", tick_font, tick_tr,
              fill=INK)

    # the quantity, spelled out under the bar it belongs to
    big = c.type.get("sans", "bold", SZ_GRAPHIC + 2)
    c.tracked((x_earth + x_voy) / 2.0, y + 62.0,
              "EARTH TO VOYAGER 1 = 1 LIGHT-DAY = 173 AU = 25.9 BILLION KM",
              big, (SZ_GRAPHIC + 2) * 0.09, fill=INK, anchor="ms")

    audit.append(("scale_px_per_au", px_per_au, 0.0))
    audit.append(("scale_bar_span", span, 0.0))
    audit.append(("scale_glyph_in_panel", x1 - pad - (x_voy + 96 * 0.58), 0.0))
    audit.append(("scale_quantity_w",
                  c.tracked_width(
                      "EARTH TO VOYAGER 1 = 1 LIGHT-DAY = 173 AU = "
                      "25.9 BILLION KM", big, (SZ_GRAPHIC + 2) * 0.09),
                  span))

    leg = c.type.get("sans", "regular", SZ_GRAPHIC_TICK)
    leg_tr = SZ_GRAPHIC_TICK * TRACK_TINY
    leg_base = bottom - 12.0
    c.tracked(x0 + pad, leg_base, SCHEMATIC_LEGEND_LEFT, leg, leg_tr,
              fill=INK_SOFT)
    c.tracked(x1 - pad, leg_base, SCHEMATIC_LEGEND_RIGHT, leg, leg_tr,
              fill=INK_SOFT, anchor="rs")
    return bottom


def _lead(c: Canvas, y: float, gap: Dict[str, float], audit: list) -> float:
    kick = c.type.get("sans", "bold", SZ_KICKER)
    k_base = y + gap["masthead_lead"] + c.cap_height(kick)
    c.tracked(CONTENT_X0, k_base, LEAD_KICKER, kick, SZ_KICKER * TRACK_KICKER,
              fill=RED)

    # headline: full without crowding the measure, and no widow on the last
    # line: every line lands between 72 and 95 per cent of the measure
    head_size, lines = c.fit_balanced(LEAD_HEADLINE, "serif", "bold",
                                      CONTENT_W, 3, 34.0, 70.0,
                                      max_fill=0.95, min_fill=0.72)
    head_leading = head_size * 1.06
    head = c.type.get("serif", "bold", head_size)
    audit.append(("lead_headline_lines", len(lines), 3))
    baseline = k_base + 14 + c.cap_height(head)
    widths = []
    for line in lines:
        c.text(CONTENT_X0, baseline, line, head, fill=INK)
        widths.append(c.width(line, head))
        audit.append(("lead_headline_w", widths[-1], CONTENT_W))
        baseline += head_leading
    baseline -= head_leading
    audit.append(("lead_headline_size", head_size, 70.0))
    audit.append(("lead_headline_rag", min(widths) / max(widths), 0.86))

    # the standfirst: the size that sits between the kicker and the headline
    stand_size, stand_font = c.fit_one_line(LEAD_STANDFIRST, "serif",
                                            "regular", CONTENT_W, 20.0, 29.0,
                                            max_fill=0.96)
    stand_base = baseline + c.descent(head) + gap["head_visual"] \
        + c.cap_height(stand_font)
    stand_w = c.width(LEAD_STANDFIRST, stand_font)
    c.text(CONTENT_X0, stand_base, LEAD_STANDFIRST, stand_font, fill=INK)
    audit.append(("standfirst_w", stand_w, CONTENT_W))
    audit.append(("standfirst_size", stand_size, 29.0))
    stand_bottom = stand_base + c.descent(stand_font)

    panel_top = stand_bottom + gap["head_visual"]
    panel_bottom = _panel(c, panel_top, audit)

    schem_top = panel_bottom + gap["visual_deck"]
    schem_bottom = _schematic(c, schem_top, audit)

    # deck on the left two columns, explainer on the right one
    deck_x, deck_w = CONTENT_X0, SPAN2_W
    exp_x, exp_w = COL_X[2], COL_W
    deck_font = c.type.get("serif", "regular", SZ_DECK)
    exp_lab = c.type.get("sans", "bold", SZ_EXPLAINER_LABEL)

    row_top = schem_bottom + gap["visual_deck"]
    deck_top = row_top + 2.0
    deck_greedy = c.wrap(LEAD_DECK, deck_font, deck_w)
    deck_lines = c.wrap_even(LEAD_DECK, deck_font, [deck_w] * len(deck_greedy),
                             len(deck_greedy))
    audit.append(("deck_lines", len(deck_lines), 5))
    deck_base = deck_top + c.cap_height(deck_font)
    deck_widths = []
    for line in deck_lines:
        c.text(deck_x, deck_base, line, deck_font, fill=INK)
        deck_widths.append(c.width(line, deck_font))
        audit.append(("deck_w", deck_widths[-1], deck_w))
        deck_base += DECK_LEADING
    deck_bottom = deck_base - DECK_LEADING + c.descent(deck_font)
    # the last line of the deck must not be a stub either
    audit.append(("deck_last_line_short", deck_w - deck_widths[-1], 220.0))

    # the rule sits on the deck's cap line; the explainer hangs from it and is
    # set to the deck's depth, so the divider has type on both sides of it all
    # the way down instead of a hairline beside nothing
    c.rule(COL_RULE_X[1], deck_top, CONTENT_X1, deck_top, width=2.2, fill=RED)
    lab_base = deck_top + 13 + c.cap_height(exp_lab)
    c.tracked(exp_x, lab_base, LEAD_EXPLAINER_LABEL, exp_lab,
              SZ_EXPLAINER_LABEL * TRACK_SMALLCAPS, fill=RED)

    text_top = lab_base + 9.0

    # set the explainer to the deck's depth: choose the size whose required
    # leading is nearest the comfortable one, then solve that leading exactly.
    # The result is that both blocks end on the same line, so the divider
    # between them has type on both sides for its whole length.
    best = None
    size = 23.0
    while size >= 16.0:
        font = c.type.get("serif", "italic", size)
        exp_lines = c.wrap(LEAD_EXPLAINER, font, exp_w)
        gaps_n = len(exp_lines) - 1
        if gaps_n > 0:
            room = (deck_bottom - text_top - c.cap_height(font)
                    - c.descent(font))
            leading = room / gaps_n
            ratio = leading / size
            if 1.14 <= ratio <= 1.52:
                score = abs(ratio - EXPLAINER_LEADING_RATIO)
                if best is None or score < best[0]:
                    best = (score, size, exp_lines, leading)
        size -= 0.25
    if best is None:
        exp_size = 20.0
        exp_font = c.type.get("serif", "italic", exp_size)
        exp_lines = c.wrap(LEAD_EXPLAINER, exp_font, exp_w)
        exp_leading = exp_size * EXPLAINER_LEADING_RATIO
    else:
        _score, exp_size, exp_lines, exp_leading = best
        exp_font = c.type.get("serif", "italic", exp_size)

    exp_base = text_top + c.cap_height(exp_font)
    for line in exp_lines:
        c.text(exp_x, exp_base, line, exp_font, fill=INK)
        audit.append(("explainer_w", c.width(line, exp_font), exp_w))
        exp_base += exp_leading
    exp_bottom = exp_base - exp_leading + c.descent(exp_font)
    audit.append(("explainer_size", exp_size, 23.0))
    audit.append(("explainer_leading_ratio", exp_leading / exp_size, 1.52))
    audit.append(("lead_blocks_depth", abs(deck_bottom - exp_bottom), 1.0))

    rule_top = deck_top - 2.0
    c.rule(COL_RULE_X[1], rule_top, COL_RULE_X[1], max(deck_bottom, exp_bottom),
           width=1.0)

    # the lead's foot: byline flush left, jump line flush right
    foot_font = c.type.get("sans", "bold", SZ_BYLINE)
    foot_base = max(deck_bottom, exp_bottom) + 17 + c.cap_height(foot_font)
    c.tracked(CONTENT_X0, foot_base, LEAD_BYLINE, foot_font,
              SZ_BYLINE * TRACK_TINY, fill=INK)
    c.tracked(CONTENT_X1, foot_base, LEAD_JUMP, foot_font,
              SZ_BYLINE * TRACK_TINY, fill=INK, anchor="rs")
    return foot_base + c.descent(foot_font)


def _band(c: Canvas, y: float, audit: list) -> float:
    """Three columns of one width on one grid, bodies on one baseline."""
    kick = c.type.get("sans", "bold", SZ_COL_KICKER)
    body = c.type.get("serif", "regular", SZ_COL_BODY)
    wire = c.type.get("sans", "bold", SZ_WIRE)

    # one headline size for all three, chosen so each wraps to two lines
    head_size = None
    size = 27.0
    while size >= 20.0:
        font = c.type.get("serif", "bold", size)
        if all(len(c.wrap_balanced(h, font, COL_W)) == 2
               for _, h, _ in COLUMNS):
            head_size = size
            break
        size -= 0.25
    if head_size is None:
        head_size = 22.0
    head = c.type.get("serif", "bold", head_size)
    audit.append(("band_headline_size", head_size, 27.0))

    top = y + 4.0
    prepared = []
    head_bottom = top
    for i, (kicker, headline, text) in enumerate(COLUMNS):
        x = COL_X[i]
        k_base = top + 14.0 + c.cap_height(kick)
        c.tracked(x, k_base, kicker, kick, SZ_COL_KICKER * TRACK_KICKER,
                  fill=RED_QUIET)
        head_lines = c.wrap_balanced(headline, head, COL_W)
        audit.append(("col_head_lines", len(head_lines), 2))
        baseline = k_base + 9.0 + c.cap_height(head)
        for line in head_lines:
            c.text(x, baseline, line, head, fill=INK)
            audit.append(("col_head_w", c.width(line, head), COL_W))
            baseline += COL_HEAD_LEADING
        head_bottom = max(head_bottom, baseline - COL_HEAD_LEADING)
        prepared.append((x, text))

    bottoms = []
    for (x, text) in prepared:
        by = head_bottom + 17.0 + c.cap_height(body)
        greedy = c.wrap(text, body, COL_W)
        body_lines = c.wrap_even(text, body, [COL_W] * len(greedy),
                                 len(greedy))
        audit.append(("col_body_lines", len(body_lines), 4))
        for line in body_lines:
            c.text(x, by, line, body, fill=INK)
            audit.append(("col_body_w", c.width(line, body), COL_W))
            by += COL_BODY_LEADING
        audit.append(("col_last_line_short",
                      COL_W - c.width(body_lines[-1], body), 250.0))
        wy = by - COL_BODY_LEADING + 17.0 + c.cap_height(wire)
        c.tracked(x, wy, WIRE_CREDIT, wire, SZ_WIRE * TRACK_TINY,
                  fill=INK_SOFT)
        bottoms.append(by - COL_BODY_LEADING + c.descent(body))

    band_mid = max(bottoms)
    audit.append(("band_column_depth", max(bottoms) - min(bottoms), 1.0))
    for i in range(COLUMNS_N - 1):
        c.rule(COL_RULE_X[i], top + 6.0, COL_RULE_X[i], band_mid, width=1.0)
    return band_mid


def _strip(c: Canvas, y: float, audit: list) -> float:
    """ALSO IN THIS EDITION, on the same three columns as the band."""
    head = c.type.get("sans", "bold", SZ_STRIP_HEAD)
    tag = c.type.get("sans", "bold", SZ_STRIP_TAG)
    item = c.type.get("serif", "regular", SZ_STRIP_ITEM)

    top_rule = y
    c.rule(CONTENT_X0, top_rule, CONTENT_X1, top_rule, width=1.0)

    base = top_rule + 15.0 + c.cap_height(head)
    c.tracked(CONTENT_X0, base, STRIP_HEADING, head,
              SZ_STRIP_HEAD * TRACK_SMALLCAPS, fill=INK)

    first = base + 24.0
    deepest = first
    for i, (label, text) in enumerate(STRIP_ITEMS):
        x = COL_X[i]
        tag_w = c.tracked(x, first, label, tag, SZ_STRIP_TAG * TRACK_KICKER,
                          fill=RED_QUIET)
        text_x = x + tag_w + 10.0
        lead_in = text_x - x
        greedy = c.wrap(text, item, COL_W - lead_in)
        lines = c.wrap_even(text, item, [COL_W - lead_in, COL_W], len(greedy))
        audit.append(("strip_lines", len(lines), 2))
        y_line = first
        for j, line in enumerate(lines):
            indent = lead_in if j == 0 else 0.0
            c.text(text_x if j == 0 else x, y_line, line, item, fill=INK)
            audit.append(("strip_w", c.width(line, item) + indent, COL_W))
            deepest = max(deepest, y_line)
            y_line += STRIP_LEADING
        audit.append(("strip_last_line_short",
                      COL_W - c.width(lines[-1], item), 190.0))

    closing = deepest + 17.0
    c.rule(CONTENT_X0, closing, CONTENT_X1, closing, width=1.0)
    return closing


def _foot(c: Canvas, audit: list) -> None:
    """The folio: real newspaper furniture, flush left and flush right."""
    font = c.type.get("sans", "bold", SZ_FOOT)
    c.rule(CONTENT_X0, FOOT_RULE, CONTENT_X1, FOOT_RULE, width=1.0)
    left = c.tracked(CONTENT_X0, FOOT_BASELINE, FOOT_LEFT, font,
                     SZ_FOOT * TRACK_SMALLCAPS, fill=INK_SOFT)
    right = c.tracked(CONTENT_X1, FOOT_BASELINE, FOOT_RIGHT, font,
                      SZ_FOOT * TRACK_SMALLCAPS, fill=INK_SOFT, anchor="rs")
    audit.append(("foot_w", left + right + 40, CONTENT_W))


# --------------------------------------------------------------------------
# composition: two passes, so the page lands on the foot rule exactly
# --------------------------------------------------------------------------


def _compose(c: Canvas, extra: Dict[str, float], audit: list) -> float:
    gap = {k: GAP_BASE[k] + extra.get(k, 0.0) for k in GAP_BASE}

    y = _datum(c, audit)
    y = _masthead(c, y, audit)
    y = _lead(c, y, gap, audit)
    band_rule = y + gap["deck_band"] - 8.0
    c.rule(CONTENT_X0, band_rule, CONTENT_X1, band_rule, width=1.6)
    y = _band(c, y + gap["deck_band"], audit)
    y = _strip(c, y + gap["band_strip"], audit)
    _foot(c, audit)
    return y


def _distribute(slack: float) -> Dict[str, float]:
    """Share slack out so the closing strip lands on TARGET_END exactly.

    Two of the gaps are used twice on the page (above and below the lead's
    standfirst, and around the diagram), so sharing the slack by weight alone
    would push the strip past its rule.  The shares are solved against the
    number of times each gap is actually applied, with the gaps that hit
    their floor dropped and the rest re-solved.
    """
    uses = GAP_USES
    floor = {k: -GAP_BASE[k] * (1.0 - GAP_FLOOR) for k in GAP_BASE}
    extra = {k: 0.0 for k in GAP_BASE}
    active = set(GAP_BASE)

    for _ in range(8):
        denom = sum(GAP_WEIGHT[k] * uses[k] for k in active)
        if denom <= 0.0:
            break
        achieved = sum(extra[k] * uses[k] for k in GAP_BASE)
        need = slack - achieved
        if abs(need) < 0.02:
            break
        for k in active:
            extra[k] += need * GAP_WEIGHT[k] / denom
        for k in [k for k in active if extra[k] < floor[k]]:
            extra[k] = floor[k]
            active.discard(k)
    return extra


def render_page(audit: Optional[list] = None) -> Image.Image:
    """Draw the whole front page and return the downsampled RGB image.

    Pass one stacks the page at its base gaps and measures where it lands;
    pass two re-stacks it with the slack shared out, so the closing rule sits
    on TARGET_END whatever the copy does.
    """
    report: list = audit if audit is not None else []

    measured = _compose(Canvas(SS), {}, [])
    slack = TARGET_END - measured
    extra = _distribute(slack)

    final_canvas = Canvas(SS)
    landed = _compose(final_canvas, extra, report)
    report.append(("natural_end", measured, 0.0))
    report.append(("slack_distributed", slack, 0.0))
    report.append(("strip_closing_rule", landed, TARGET_END))

    return final_canvas.image.resize((PAGE_W, PAGE_H), _resample())


def _resample():
    try:
        return Image.Resampling.LANCZOS
    except AttributeError:      # Pillow < 9.1
        return Image.LANCZOS


def save_page(path: str, audit: Optional[list] = None) -> Tuple[int, int]:
    """Render and write the page.  Returns (width, height)."""
    image = render_page(audit=audit)
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    image.save(path, format="PNG")
    return image.width, image.height


def overruns(audit, tolerance: float = 0.5) -> List[Tuple[str, float, float]]:
    """Every measured block wider or deeper than the limit it must respect."""
    bad = []
    for label, used, limit in audit:
        if limit > 0 and used > limit + tolerance:
            bad.append((label, used, limit))
    return bad
