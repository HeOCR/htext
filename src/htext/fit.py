"""The S10b no-loss wrap rule, checked with the generator's own code.

Every corpus line must render without losing a character in every
``hocrsyngen`` template body that receives corpus text:

- no single word is wider than a body's wrap width, and
- a body that caps its rendered rows never receives more wrapped rows than it
  draws.

The region table below uses the same formulas, from the same ``hocrsyngen``
constants, as ``WRAPPING_BODIES`` in ``hocrsyngen``'s
``tests/test_training_text_corpus.py``. ``tests/test_fit.py`` checks that the two
tables agree when a ``hocrsyngen`` source tree is available
(``HOCRSYNGEN_SOURCE``). The check needs ``hocrsyngen`` and Pillow built with
libraqm; install the ``fit`` extra.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from htext.hebrew import MAQAF

PRINTED_FONT = "Alef-Regular.ttf"
HANDWRITTEN_FONT = "GveretLevin-Regular.ttf"
ARCHIVE_CARD_ROW_CAP = 7
LEDGER_ROW_CAP = 10


@dataclass(frozen=True)
class Body:
    template_id: str
    font_file: str
    size: int
    width: int
    # Rendered rows one corpus line may take, or None when every row is drawn.
    rows_per_line: int | None


def wrapping_bodies() -> tuple[Body, ...]:
    from hocrsyngen.generator import CANVAS_SIZE, PAPER_MARGIN, _recipe_for_template

    letter_body_width = CANVAS_SIZE[0] - (2 * PAPER_MARGIN) - 40
    archive_card_body_width = (CANVAS_SIZE[0] - PAPER_MARGIN - 70 - 10) - (PAPER_MARGIN + 80 + 10) - 340
    ledger_detail_cell_width = 250 - 44
    archive_lines = _recipe_for_template("archive_card").line_count
    return (
        Body("printed_letter", PRINTED_FONT, 42, letter_body_width, None),
        Body("handwritten_note", HANDWRITTEN_FONT, 46, letter_body_width, None),
        Body("archive_card", PRINTED_FONT, 38, archive_card_body_width, ARCHIVE_CARD_ROW_CAP // archive_lines),
        # One corpus line per ledger details cell, which draws up to 10 rows.
        Body("ledger", PRINTED_FONT, 30, ledger_detail_cell_width, LEDGER_ROW_CAP),
    )


def hocrsyngen_commit() -> str | None:
    """The commit recorded for an installed ``hocrsyngen``, when pip recorded one."""

    import json
    from importlib.metadata import distribution

    try:
        direct = distribution("hocrsyngen").read_text("direct_url.json")
    except Exception:
        return None
    if not direct:
        return None
    return json.loads(direct).get("vcs_info", {}).get("commit_id")


class FitChecker:
    """Checks lines against every wrapping body, caching per-token widths."""

    def __init__(self) -> None:
        from PIL import Image, ImageDraw, ImageFont, features

        if not features.check("raqm"):
            raise RuntimeError("Pillow libraqm support is required for the no-loss wrap check")
        from hocrsyngen.assets import synthetic_data_path
        from hocrsyngen.generator import _wrap_hebrew_text

        self._wrap = _wrap_hebrew_text
        self._draw = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        fonts_dir = synthetic_data_path("fonts")
        self.bodies = wrapping_bodies()
        self._fonts = {
            (body.font_file, body.size): ImageFont.truetype(str(fonts_dir / body.font_file), body.size) for body in self.bodies
        }
        self._glyph_fonts = {name: ImageFont.truetype(str(fonts_dir / name), 48) for name in (PRINTED_FONT, HANDWRITTEN_FONT)}
        self._token_width = lru_cache(maxsize=2_000_000)(self._measure)

    def _measure(self, text: str, font_key: tuple[str, int]) -> int:
        left, _top, right, _bottom = self._draw.textbbox((0, 0), text, font=self._fonts[font_key], direction="rtl")
        return right - left

    def has_glyph(self, char: str) -> bool:
        """The S13b glyph check: ``char`` renders, and not as the .notdef box."""

        from PIL import Image, ImageChops, ImageDraw

        for font in self._glyph_fonts.values():

            def render(text: str) -> Image.Image:
                image = Image.new("L", (160, 120), 255)
                ImageDraw.Draw(image).text((40, 20), text, font=font, fill=0)
                return image

            notdef = render("")  # a private-use code point: the font's .notdef box
            image = render(char)
            if (
                image.getbbox() is None
                or ImageChops.invert(image).getbbox() is None
                or ImageChops.difference(image, notdef).getbbox() is None
            ):
                return False
        return True

    def maqaf_allowed(self) -> bool:
        return self.has_glyph(MAQAF)

    def failure(self, line: str) -> str | None:
        """The first body the line does not fit, as ``"<template>:<reason>"``, or None."""

        for body in self.bodies:
            key = (body.font_file, body.size)
            for token in line.split():
                if self._token_width(token, key) > body.width:
                    return f"{body.template_id}:word_too_wide"
            if body.rows_per_line is not None:
                if self._token_width(line, key) <= body.width:
                    continue
                rows = len(self._wrap(self._draw, line, self._fonts[key], body.width))
                if rows > body.rows_per_line:
                    return f"{body.template_id}:too_many_rows"
        return None

