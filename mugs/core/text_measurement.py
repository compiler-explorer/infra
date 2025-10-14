"""Text measurement utilities using PIL."""

from PIL import Image, ImageDraw, ImageFont

from core.constants import DUMMY_IMAGE_SIZE, FONT_NAME, FONT_NAME_EXTRACTION_SIZE
from core.data_structures import TextMeasurement


class PILTextMeasurer:
    """Text measurer using PIL ImageDraw for accurate pixel measurements."""

    def __init__(self) -> None:
        self._font_cache: dict[tuple[int, str, str], ImageFont.FreeTypeFont] = {}

    def _get_font(
        self, font_size: int, font_family: str = FONT_NAME, font_weight: str = "normal"
    ) -> ImageFont.FreeTypeFont:
        """Get or create a PIL font object."""
        cache_key = (font_size, font_family, font_weight)
        if cache_key not in self._font_cache:
            font = ImageFont.truetype(font_family, font_size)
            self._font_cache[cache_key] = font

        return self._font_cache[cache_key]

    def measure_text(
        self, text: str, font_size: int, font_family: str = FONT_NAME, font_weight: str = "normal"
    ) -> TextMeasurement:
        font = self._get_font(font_size, font_family, font_weight)

        # Create a dummy image to get text dimensions
        dummy_img = Image.new("RGB", DUMMY_IMAGE_SIZE)
        draw = ImageDraw.Draw(dummy_img)

        # Use getbbox for more accurate measurements
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]

        # Get font metrics for ascent/descent
        ascent, descent = font.getmetrics()

        return TextMeasurement(width=float(width), height=float(height), ascent=float(ascent), descent=float(descent))

    def get_svg_font_family(self, font_filename: str = FONT_NAME) -> str:
        """Get the SVG-compatible font family name from a font file."""
        # Load font and extract family name
        font = ImageFont.truetype(font_filename, FONT_NAME_EXTRACTION_SIZE)  # Size doesn't matter for name extraction
        family_name, _ = font.getname()
        return family_name


def wrap_text(
    text: str,
    max_width: int,
    measurer: PILTextMeasurer,
    font_size: int,
    font_family: str = FONT_NAME,
    font_weight: str = "normal",
) -> list[str]:
    """Wrap text to fit within max_width, breaking at word boundaries."""
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        # Try adding this word to current line
        test_line = current_line + (" " if current_line else "") + word
        measurement = measurer.measure_text(test_line, font_size, font_family, font_weight)

        if measurement.width <= max_width:
            # Word fits, add it to current line
            current_line = test_line
        else:
            # Word doesn't fit, start new line
            if current_line:
                lines.append(current_line)
            current_line = word

    # Add final line if not empty
    if current_line:
        lines.append(current_line)

    return lines
