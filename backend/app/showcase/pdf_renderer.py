"""Pure-Python zlib-compressed %PDF-1.4 renderer using Type1 Helvetica/Courier fonts (zero remote assets)."""

from __future__ import annotations

import textwrap
import zlib
from dataclasses import dataclass

_ASCII_REPLACEMENTS: dict[str, str] = {
    "\u2014": "--",
    "\u2013": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2022": "*",
    "\u2192": "->",
    "\u2265": ">=",
    "\u2264": "<=",
    "\u00a0": " ",
}


def sanitize_pdf_text(text: str) -> str:
    """Normalize common Unicode typography safely to single-byte WinAnsi/ASCII and escape PDF delimiters."""
    out = text
    for src, dst in _ASCII_REPLACEMENTS.items():
        out = out.replace(src, dst)
    encoded = out.encode("cp1252", errors="replace").decode("cp1252")
    return encoded.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


@dataclass(frozen=True)
class PdfLine:
    text: str
    font: str = "F1"  # F1=Helvetica, F2=Helvetica-Bold, F3=Courier
    size: int = 10
    leading: int = 14
    indent: int = 0
    rgb: tuple[float, float, float] = (0.10, 0.14, 0.22)


class SimplePdfDocument:
    """Minimal pure-Python multi-page PDF 1.4 writer with FlateDecode streams and page footers."""

    PAGE_WIDTH = 612
    PAGE_HEIGHT = 792
    MARGIN_X = 48
    TOP_Y = 744
    BOTTOM_Y = 58

    def __init__(self, footer_label: str = "AegisOps Postmortem Export | Sanitized Operational Record") -> None:
        self._lines: list[PdfLine] = []
        self._footer_label = footer_label

    def add_heading(self, text: str) -> None:
        self.add_spacer(6)
        for wrapped in textwrap.wrap(text.strip() or " ", width=70) or [" "]:
            self._lines.append(
                PdfLine(text=wrapped, font="F2", size=13, leading=18, rgb=(0.05, 0.22, 0.45))
            )
        self.add_spacer(2)

    def add_title(self, text: str) -> None:
        for wrapped in textwrap.wrap(text.strip() or " ", width=56) or [" "]:
            self._lines.append(
                PdfLine(text=wrapped, font="F2", size=16, leading=21, rgb=(0.04, 0.12, 0.26))
            )
        self.add_spacer(4)

    def add_paragraph(self, text: str, *, mono: bool = False, indent: int = 0) -> None:
        width = 80 if mono else 88
        font = "F3" if mono else "F1"
        size = 9 if mono else 10
        leading = 13 if mono else 14
        for raw_line in text.splitlines() or [""]:
            wrapped_lines = textwrap.wrap(raw_line, width=max(30, width - indent // 5)) or [""]
            for wl in wrapped_lines:
                self._lines.append(PdfLine(text=wl, font=font, size=size, leading=leading, indent=indent))

    def add_kv(self, key: str, value: str) -> None:
        full = f"{key}: {value}"
        wrapped = textwrap.wrap(full, width=88) or [full]
        for idx, wl in enumerate(wrapped):
            self._lines.append(
                PdfLine(
                    text=wl,
                    font="F1",
                    size=10,
                    leading=14,
                    indent=0 if idx == 0 else 14,
                )
            )

    def add_bullet(self, text: str) -> None:
        wrapped = textwrap.wrap(text, width=82) or [""]
        for idx, wl in enumerate(wrapped):
            prefix = "* " if idx == 0 else "  "
            self._lines.append(PdfLine(text=f"{prefix}{wl}", font="F1", size=10, leading=14, indent=8))

    def add_spacer(self, pts: int = 6) -> None:
        self._lines.append(PdfLine(text="", font="F1", size=10, leading=pts))

    def render_bytes(self) -> bytes:
        """Paginate, zlib-compress content streams, and emit complete %PDF-1.4 bytes."""
        pages_lines: list[list[tuple[int, PdfLine]]] = []
        current_page: list[tuple[int, PdfLine]] = []
        y = self.TOP_Y

        for line in self._lines:
            if y - line.leading < self.BOTTOM_Y and current_page:
                pages_lines.append(current_page)
                current_page = []
                y = self.TOP_Y
            current_page.append((y, line))
            y -= line.leading
        if current_page or not pages_lines:
            pages_lines.append(current_page)

        total_pages = len(pages_lines)
        page_streams: list[bytes] = []
        for page_num, items in enumerate(pages_lines, start=1):
            cmds: list[str] = []
            for y_pos, line in items:
                if not line.text:
                    continue
                x_pos = self.MARGIN_X + line.indent
                r, g, b = line.rgb
                escaped = sanitize_pdf_text(line.text)
                cmds.append(f"BT /{line.font} {line.size} Tf {r:.3f} {g:.3f} {b:.3f} rg 1 0 0 1 {x_pos} {y_pos} Tm ({escaped}) Tj ET")
            footer = sanitize_pdf_text(f"{self._footer_label} | Page {page_num} of {total_pages}")
            cmds.append("0.75 0.78 0.84 RG 0.5 w 48 44 m 564 44 l S")
            cmds.append(f"BT /F1 8 Tf 0.40 0.45 0.52 rg 1 0 0 1 48 30 Tm ({footer}) Tj ET")
            stream_bytes = "\n".join(cmds).encode("latin-1", errors="replace")
            page_streams.append(zlib.compress(stream_bytes, level=6))

        # Objects layout:
        # 1: Catalog, 2: Pages, 3: F1 Helvetica, 4: F2 Helvetica-Bold, 5: F3 Courier
        # Per page i (0..N-1): Page obj = 6 + 2*i, Content stream obj = 7 + 2*i
        objects: list[bytes] = []
        page_obj_ids = [6 + 2 * i for i in range(total_pages)]
        kids_str = " ".join(f"{pid} 0 R" for pid in page_obj_ids)

        objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
        objects.append(f"2 0 obj\n<< /Type /Pages /Kids [{kids_str}] /Count {total_pages} >>\nendobj\n".encode("ascii"))
        objects.append(b"3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\nendobj\n")
        objects.append(b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>\nendobj\n")
        objects.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>\nendobj\n")

        for i, compressed in enumerate(page_streams):
            p_id = 6 + 2 * i
            c_id = 7 + 2 * i
            objects.append(
                (
                    f"{p_id} 0 obj\n"
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.PAGE_WIDTH} {self.PAGE_HEIGHT}] "
                    f"/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> "
                    f"/Contents {c_id} 0 R >>\nendobj\n"
                ).encode("ascii")
            )
            header = f"{c_id} 0 obj\n<< /Length {len(compressed)} /Filter /FlateDecode >>\nstream\n".encode("ascii")
            objects.append(header + compressed + b"\nendstream\nendobj\n")

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets: list[int] = [0]
        for obj in objects:
            offsets.append(len(out))
            out.extend(obj)

        xref_offset = len(out)
        out.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
        for off in offsets[1:]:
            out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
        out.extend(
            (
                f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
                f"startxref\n{xref_offset}\n%%EOF\n"
            ).encode("ascii")
        )
        return bytes(out)
