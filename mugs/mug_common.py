"""Backward compatibility imports from modularized mug generation code."""

# Import constants
from core.constants import *  # noqa: F403, F401

# Import data structures
from core.data_structures import (  # noqa: F401
    ContentBlock,
    InfoItem,
    MugLayout,
    TableRow,
    TextMeasurement,
)

# Import layout engine
from core.layout_engine import LayoutEngine  # noqa: F401

# Import SVG generation functions
from core.svg_generation import (  # noqa: F401
    create_horizontal_table,
    create_info_table,
    create_table_row,
    render_info_items,
    svg_to_png,
)

# Import text measurement
from core.text_measurement import PILTextMeasurer, wrap_text  # noqa: F401
