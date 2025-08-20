"""Constants used throughout mug generation."""

# Common color constants
BG_COLOR = "transparent"
TEXT_COLOR = "#000000"
CE_GREEN = "#67c52a"
BORDER_COLOR = "#333333"
HEADER_BG = "#f0f0f0"

# Common font and layout constants
FONT_NAME = "DejaVuSansMono.ttf"

# Font size constants
MINIMUM_READABLE_FONT_SIZE = 28  # Minimum font size for any text
DEFAULT_FOOTER_REDUCTION = 8  # Footer font is text_size - this value
MAX_TABLE_FONT_SIZE = 60  # Maximum font size for table content
MIN_TABLE_FONT_SIZE = 32  # Minimum font size for table content
FONT_NAME_EXTRACTION_SIZE = 12  # Font size for extracting font family name (size doesn't matter)

# Common font sizes used across mugs
STANDARD_TITLE_SIZE = 72
STANDARD_HEADER_SIZE = 36
STANDARD_TEXT_SIZE = 48
STANDARD_INFO_TEXT_SIZE = 54

# Architecture-specific table row padding
SYSTEMV_TABLE_ROW_PADDING = 20  # System V ABI row padding
MSVC_TABLE_ROW_PADDING = 20  # MSVC ABI row padding
ARM64_TABLE_ROW_PADDING = 20  # ARM64 ABI row padding
RISCV_TABLE_ROW_PADDING = 20  # RISC-V ABI row padding

# Footer spacing values
STANDARD_FOOTER_SPACING = 40

# Layout spacing constants
DEFAULT_MARGIN = 40  # Default margin around content
CONTINUATION_LINE_SPACING = 0.84  # Spacing multiplier for continuation rows with empty labels
TABLE_CELL_PADDING = 8  # Horizontal padding inside main table cells
INFO_TABLE_HORIZONTAL_PADDING = 12  # Horizontal padding for info table
TITLE_BOTTOM_SPACING = 50  # Space after title
TABLE_TO_INFO_SPACING = 50  # Space between main table and info table
INFO_TO_FOOTER_SPACING = 40  # Space between info table and footer
INFO_TABLE_ROW_HEIGHT = 68  # Row height for info table

# Table row labels
ROW_LABEL_FUNCTION = "func()"
ROW_LABEL_MEMBER = "obj.f()"

# Horizontal table widths (for register names as headers)
REGISTER_COL_WIDTH = 120  # Width for each register column

# Layout constants
TABLE_Y = 150

# Typography and appearance constants
LINE_HEIGHT_MULTIPLIER = 1.2  # Standard line spacing multiplier
TEXT_VERTICAL_CENTER_OFFSET = 3  # Divisor for rough vertical centering (text_size // 3)
FOOTER_OPACITY = 0.6  # Opacity for footer text
ALTERNATING_ROW_COLORS = ("#ffffff", "#f9f9f9")  # Colors for alternating table rows

# SVG rendering constants
SVG_STROKE_WIDTH = 1  # Standard stroke width for borders
INFO_ITEM_DX_SPACING = 8  # Spacing for tspan dx attribute
INFO_ITEM_LINE_SPACING = 28  # Vertical spacing between info items
FONT_SIZE_DECREMENT = 0.5  # Amount to decrease font size when it doesn't fit
FOOTER_FONT_SIZE_DECREMENT = 1  # Amount to decrease footer font size when it doesn't fit

# Positioning constants
DUMMY_IMAGE_SIZE = (1, 1)  # Size for PIL dummy image used for text measurement
HEADER_ROW_COUNT = 1  # Number of header rows in main table

# Default canvas dimensions
DEFAULT_WIDTH = 1400
DEFAULT_HEIGHT = 1000
DEFAULT_DPI = 300
