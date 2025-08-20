"""Layout engine for mug generation."""

from typing import Any

from core.constants import (
    CONTINUATION_LINE_SPACING,
    DEFAULT_FOOTER_REDUCTION,
    DEFAULT_MARGIN,
    FONT_SIZE_DECREMENT,
    FOOTER_FONT_SIZE_DECREMENT,
    HEADER_ROW_COUNT,
    INFO_TABLE_HORIZONTAL_PADDING,
    INFO_TABLE_ROW_HEIGHT,
    LINE_HEIGHT_MULTIPLIER,
    MAX_TABLE_FONT_SIZE,
    MIN_TABLE_FONT_SIZE,
    MINIMUM_READABLE_FONT_SIZE,
    TABLE_CELL_PADDING,
    TITLE_BOTTOM_SPACING,
)
from core.data_structures import MugLayout, TextMeasurement
from core.text_measurement import PILTextMeasurer


class LayoutEngine:
    def __init__(self, canvas_width: int, canvas_height: int, margin: int = DEFAULT_MARGIN) -> None:
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.margin = margin
        self.measurer = PILTextMeasurer()
        # Cache the SVG font family name
        self._svg_font_family: str | None = None

    @property
    def svg_font_family(self) -> str:
        """Get the SVG-compatible font family name."""
        if self._svg_font_family is None:
            self._svg_font_family = self.measurer.get_svg_font_family()
        return self._svg_font_family

    def _calculate_table_font_size(self, layout: MugLayout, content_width: int) -> tuple[int, int, int, int]:
        """Calculate optimal table font size, dimensions, and row height."""
        num_registers = len(layout.table_headers)
        max_table_font_size = MAX_TABLE_FONT_SIZE
        min_table_font_size = MIN_TABLE_FONT_SIZE

        table_font_size = max_table_font_size
        while table_font_size >= min_table_font_size:
            # Measure the row labels at this font size
            label_width = int(max([
                self.measurer.measure_text(row.label, table_font_size).width
                for row in layout.table_rows
            ]) + TABLE_CELL_PADDING * 2)

            # Calculate column width for register columns
            register_col_width = (content_width - label_width) // num_registers

            # Check if all table content fits at this size
            all_fits = True

            # Check headers
            for header in layout.table_headers:
                measurement = self.measurer.measure_text(header, layout.header_size)
                if measurement.width + TABLE_CELL_PADDING * 2 > register_col_width:
                    all_fits = False
                    break

            # Check all cell content
            if all_fits:
                for row in layout.table_rows:
                    for cell in row.cells:
                        measurement = self.measurer.measure_text(cell, table_font_size)
                        if measurement.width + TABLE_CELL_PADDING * 2 > register_col_width:
                            all_fits = False
                            break
                    if not all_fits:
                        break

            if all_fits:
                # Calculate dynamic row height based on font metrics + padding
                font_measurement = self.measurer.measure_text("Sample", table_font_size)
                calculated_row_height = int(font_measurement.height + (layout.table_row_padding * 2))
                return table_font_size, label_width, register_col_width, calculated_row_height

            table_font_size = int(table_font_size - FONT_SIZE_DECREMENT)

        raise ValueError(
            f"Cannot fit table content with minimum font size of {min_table_font_size}pt. Content is too wide for the available space."
        )

    def _calculate_footer_positioning(self, layout: MugLayout, content_width: int) -> dict[str, Any]:
        """Calculate footer font size and positioning."""
        if not layout.footer_lines:
            return {
                "x": 0,
                "y": self.canvas_height,
                "size": MINIMUM_READABLE_FONT_SIZE,
                "line_height": MINIMUM_READABLE_FONT_SIZE * LINE_HEIGHT_MULTIPLIER,
                "lines": [],
                "measurements": [],
            }

        max_footer_font_size = layout.text_size - DEFAULT_FOOTER_REDUCTION
        min_footer_font_size = MINIMUM_READABLE_FONT_SIZE

        footer_size = max_footer_font_size
        line_measurements: list[TextMeasurement] = []
        while footer_size >= min_footer_font_size:
            max_width = 0
            line_measurements = []
            for line in layout.footer_lines:
                measurement = self.measurer.measure_text(line, footer_size)
                line_measurements.append(measurement)
                max_width = max(max_width, int(measurement.width))

            if max_width <= content_width:
                break
            footer_size = int(footer_size - FOOTER_FONT_SIZE_DECREMENT)

        # Calculate positioning from bottom upwards
        line_height = footer_size * LINE_HEIGHT_MULTIPLIER
        sample_measurement = (
            line_measurements[0] if line_measurements else self.measurer.measure_text("Sample", footer_size)
        )
        last_line_baseline_y = self.canvas_height - sample_measurement.descent
        footer_start_y = last_line_baseline_y - ((len(layout.footer_lines) - 1) * line_height)

        # Get font ascent for visual positioning
        footer_ascent = sample_measurement.ascent

        return {
            "x": self.canvas_width // 2,
            "y": footer_start_y,
            "size": footer_size,
            "line_height": line_height,
            "lines": layout.footer_lines,
            "measurements": line_measurements,
            "ascent": footer_ascent,
        }

    def _calculate_info_table_dimensions(self, layout: MugLayout) -> tuple[int, int, int]:
        """Calculate info table dimensions and positioning."""
        # Calculate the spacing between first and last row positions
        # This matches exactly what create_info_table() does
        spacing_height = 0
        for i in range(len(layout.info_items) - 1):  # N-1 gaps between N rows
            next_label, _ = layout.info_items[i + 1]
            if next_label.strip() == "":
                spacing_height += int(INFO_TABLE_ROW_HEIGHT * CONTINUATION_LINE_SPACING)
            else:
                spacing_height += INFO_TABLE_ROW_HEIGHT

        # Total visual height: spacing + one row height for the last row's content
        actual_height = spacing_height + INFO_TABLE_ROW_HEIGHT

        # Calculate actual width by measuring content
        max_label_width = 0
        for label, _ in layout.info_items:
            if label.strip():
                measurement = self.measurer.measure_text(label, layout.info_text_size, font_weight="bold")
                max_label_width = max(max_label_width, int(measurement.width))

        max_content_width = 0
        for _, content in layout.info_items:
            measurement = self.measurer.measure_text(content, layout.info_text_size)
            max_content_width = max(max_content_width, int(measurement.width))

        info_label_width = max_label_width + INFO_TABLE_HORIZONTAL_PADDING * 2
        info_content_width = max_content_width + INFO_TABLE_HORIZONTAL_PADDING * 2
        actual_width = info_label_width + info_content_width

        return actual_height, actual_width, info_label_width

    def layout_mug(self, layout: MugLayout) -> dict[str, Any]:
        # Measure title for horizontal placement at top
        title_measurement = self.measurer.measure_text(layout.title, layout.title_size, font_weight="bold")
        title_height_needed = title_measurement.height + TITLE_BOTTOM_SPACING

        # Use full canvas width and start content below title
        content_x = 0
        content_width = self.canvas_width
        content_y = title_height_needed

        positions = {}

        # Title (horizontal at top)
        positions["title"] = {
            "x": self.canvas_width // 2,
            "y": title_measurement.height,
            "size": layout.title_size,
            "measurement": title_measurement,
        }

        # Skip code examples - no longer needed
        positions["code_examples"] = {}

        # Table calculation
        table_y = content_y
        table_font_size, label_width, register_col_width, calculated_row_height = self._calculate_table_font_size(
            layout, content_width
        )

        positions["table"] = {
            "x": content_x,
            "y": table_y,
            "width": content_width,
            "col_width": register_col_width,
            "label_width": label_width,
            "num_cols": len(layout.table_headers),
            "num_rows": len(layout.table_rows),
            "row_height": calculated_row_height,
            "header_size": max(layout.header_size, table_font_size),
            "text_size": table_font_size,
        }

        # Calculate where the main table ends
        main_table_bottom = table_y + calculated_row_height * (
            len(layout.table_rows) + HEADER_ROW_COUNT
        )  # header + data rows

        # Footer calculation
        footer_data = self._calculate_footer_positioning(layout, content_width)
        positions["footer"] = footer_data
        footer_start_y = footer_data["y"]

        # Calculate footer visual top (baseline - ascent) for proper centering
        footer_visual_top = footer_start_y - footer_data["ascent"]

        # Info table calculation
        info_table_height, actual_info_table_width, _ = self._calculate_info_table_dimensions(layout)
        info_table_y = (main_table_bottom + footer_visual_top - info_table_height) // 2
        info_table_x = (self.canvas_width - actual_info_table_width) // 2

        positions["info_items"] = {
            "x": info_table_x,
            "y": info_table_y,
            "width": actual_info_table_width,
            "height": info_table_height,
            "row_height": INFO_TABLE_ROW_HEIGHT,
            "text_size": layout.info_text_size,
        }

        return positions
