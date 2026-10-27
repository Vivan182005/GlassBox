"""
Tailoring by editing the candidate's own PDF in place.

Only the lines of an edited bullet (or skills line) are touched: their words
are removed and the new wording is set in the same embedded font, size and
colour, starting at the same x, on the same baselines, justified to the same
right edge. Bold or italic words keep their style. An edit is applied only if
it fits on the lines the original already occupies and every new letter
exists in the PDF's embedded font subset; otherwise it is skipped with a
reason, so the page layout never changes.
"""
import difflib
import io
import re
import statistics
from typing import Any, Dict, List, Optional, Tuple

import pymupdf

_BULLET_GLYPHS = {"•", "–", "-", "—", "◦", "▪", "‣", "●", "■", "∙", "·"}


_LIGATURES = str.maketrans({"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "’": "'", "–": "-", "—": "-"})


def _flat(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").translate(_LIGATURES).lower())


class _Fonts:
    """Embedded fonts by their visible name ("CMR10"), loaded from the PDF."""

    def __init__(self, doc: pymupdf.Document, page: pymupdf.Page):
        self.doc = doc
        self.builtin: Dict[str, str] = {}  # visible name -> base-14 code, for fonts the PDF doesn't embed
        self.by_name: Dict[str, Tuple[int, Optional[pymupdf.Font]]] = {}
        for xref, _ext, _type, basename, _name, _enc, *_ in page.get_fonts(full=True):
            short = basename.split("+", 1)[-1]
            if short not in self.by_name:
                self.by_name[short] = (xref, None)

    def get(self, name: str) -> Optional[pymupdf.Font]:
        xref, font = self.by_name.get(name, (None, None))
        if xref is None:
            return None
        if font is None:
            try:
                _n, _e, _t, buf = self.doc.extract_font(xref)
                font = pymupdf.Font(fontbuffer=buf) if buf else None
            except Exception:
                font = None
            if font is None:
                code = _base14_code(name)
                if code:
                    self.builtin[name] = code
                    font = pymupdf.Font(fontname=code)
            self.by_name[name] = (xref, font)
        return font


def _base14_code(name: str) -> Optional[str]:
    """A standard PDF font that isn't embedded (viewers draw it from their own
    copy) maps to the same built-in font."""
    n = name.lower()
    bold, italic = "bold" in n, "italic" in n or "oblique" in n
    family = "he" if re.search(r"helvetica|arial", n) else "ti" if "times" in n else "co" if "courier" in n else None
    if not family:
        return None
    regular = {"he": "helv", "ti": "tiro", "co": "cour"}[family]
    return regular if not (bold or italic) else family + ("bi" if bold and italic else "bo" if bold else "it")


def _words(page: pymupdf.Page) -> List[List[Dict[str, Any]]]:
    """Visual lines of words, top to bottom, each word with its style."""
    words = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                # pdfTeX writes one span per word; others may pack several.
                parts = s["text"].split(" ") if " " in s["text"].strip() else [s["text"]]
                if len(parts) == 1:
                    if s["text"].strip():
                        words.append({"text": s["text"].strip(), "font": s["font"], "size": s["size"], "color": s["color"],
                                      "bbox": list(s["bbox"]), "base": s["origin"][1]})
                    continue
                # Split a multi-word span using character positions.
                x = s["bbox"][0]
                chars = page.get_text("rawdict", clip=pymupdf.Rect(s["bbox"]))
                spans_chars = [c for bb in chars["blocks"] for ll in bb.get("lines", []) for ss in ll["spans"] for c in ss["chars"]]
                cur, start = "", None
                for c in spans_chars + [{"c": " ", "bbox": (0, 0, 0, 0)}]:
                    if c["c"] == " ":
                        if cur:
                            words.append({"text": cur, "font": s["font"], "size": s["size"], "color": s["color"],
                                          "bbox": [start, s["bbox"][1], x, s["bbox"][3]], "base": s["origin"][1]})
                        cur, start = "", None
                    else:
                        if start is None:
                            start = c["bbox"][0]
                        cur += c["c"]
                        x = c["bbox"][2]
    words.sort(key=lambda w: (round(w["base"]), w["bbox"][0]))
    lines: List[List[Dict[str, Any]]] = []
    for w in words:
        if lines and abs(lines[-1][0]["base"] - w["base"]) < 1.5:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(l, key=lambda w: w["bbox"][0]) for l in lines]


def _paragraphs(lines: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Bullets (and other wrapped paragraphs): a line that starts with a bullet
    glyph plus the following lines indented to its text."""
    paras = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line[0]["text"] in _BULLET_GLYPHS and len(line) > 1:
            text_x = line[1]["bbox"][0]
            group = [line[1:]]
            j = i + 1
            height = line[1]["size"] * 1.6
            while j < len(lines):
                nxt = lines[j]
                if nxt[0]["text"] in _BULLET_GLYPHS or abs(nxt[0]["bbox"][0] - text_x) > 2.5 or nxt[0]["base"] - group[-1][0]["base"] > height:
                    break
                group.append(nxt)
                j += 1
            paras.append({"lines": group, "x0": text_x, "kind": "bullet"})
            i = j
        else:
            paras.append({"lines": [line], "x0": line[0]["bbox"][0], "kind": "line"})
            i += 1
    return paras


def _para_text(para: Dict[str, Any]) -> str:
    return " ".join(w["text"] for l in para["lines"] for w in l)


def _find(paras: List[Dict[str, Any]], original: str, kind: Optional[str] = None) -> Optional[Dict[str, Any]]:
    target = _flat(original)
    candidates = [p for p in paras if not kind or p["kind"] == kind]
    if kind == "line":
        # A wrapped line ("Product Management: …, North / Star metrics, …")
        # continues on the next line(s) at the same left edge.
        for i, p in enumerate(paras):
            group = [p]
            for q in paras[i + 1:i + 3]:
                prev = group[-1]["lines"][-1]
                if q["kind"] != "line" or abs(q["x0"] - p["x0"]) > 2.5 or q["lines"][0][0]["base"] - prev[0]["base"] > prev[0]["size"] * 1.6:
                    break
                group.append(q)
                if len(group) > 1:
                    candidates.append({"lines": [g["lines"][0] for g in group], "x0": p["x0"], "kind": "line"})
    best, score = None, 0.0
    for p in candidates:
        r = difflib.SequenceMatcher(None, target, _flat(_para_text(p))).ratio()
        if r > score:
            best, score = p, r
    return best if score >= 0.9 else None


def _style_key(w: Dict[str, Any]) -> Tuple[str, float, int]:
    return (w["font"], round(w["size"], 2), w["color"])


def _new_tokens(para: Dict[str, Any], new_text: str) -> List[Dict[str, Any]]:
    """New wording as styled tokens: words kept from the original keep their
    own style (bold stays bold); inserted words take the paragraph's body style."""
    old = [w for l in para["lines"] for w in l]
    styles: Dict[Tuple[str, float, int], int] = {}
    for w in old:
        styles[_style_key(w)] = styles.get(_style_key(w), 0) + len(w["text"])
    body = max(styles, key=styles.get)
    new_words = new_text.split()
    norm = lambda t: t.translate(_LIGATURES)
    sm = difflib.SequenceMatcher(None, [norm(w["text"]) for w in old], [norm(t) for t in new_words], autojunk=False)
    out: List[Dict[str, Any]] = []
    for op, a0, a1, b0, b1 in sm.get_opcodes():
        if op == "equal":
            # The original glyphs (ligatures included) are reused as they were.
            out += [{"text": old[a0 + k]["text"], "style": _style_key(old[a0 + k])} for k in range(b1 - b0)]
        else:
            for k in range(b0, b1):
                # A word that only changed punctuation keeps its old style.
                match = next((w for w in old[a0:a1] if _flat(w["text"]) and _flat(w["text"]) == _flat(new_words[k])), None)
                out.append({"text": match["text"] if match and norm(match["text"]) == norm(new_words[k]) else new_words[k],
                            "style": _style_key(match) if match else body, "new": match is None})
    return out


def _layout(tokens, fonts: _Fonts, x0: float, right: float, n_lines: int, natural_space: float, justify: bool,
            max_space: Optional[float] = None):
    widths = []
    for t in tokens:
        font = fonts.get(t["style"][0])
        if font is None:
            return None, f"the font '{t['style'][0]}' can't be reused"
        missing = sorted({c for c in t["text"] if not font.has_glyph(ord(c))})
        if missing:
            return None, f"your PDF's font has no '{''.join(missing)}' to typeset “{t['text']}”"
        widths.append(font.text_length(t["text"], fontsize=t["style"][1]))
    avail = right - x0
    min_space = natural_space * 0.75
    lines, cur, cur_w = [], [], 0.0
    for t, w in zip(tokens, widths):
        add = w + (min_space if cur else 0)
        if cur and cur_w + add > avail + 0.3:
            lines.append(cur)
            cur, cur_w = [], 0.0
            add = w
        cur.append((t, w))
        cur_w += add
    if cur:
        lines.append(cur)
    if len(lines) > n_lines:
        return None, "it would need an extra line, which would move everything below it"
    placed = []
    for i, line in enumerate(lines):
        if justify and i < len(lines) - 1 and len(line) > 1:
            stretch = (avail - sum(w for _, w in line)) / (len(line) - 1)
            if stretch > (max_space or natural_space * 1.8):
                return None, "it would leave wide gaps between words (your original avoids that with hyphenation)"
        words_w = sum(w for _, w in line)
        gaps = len(line) - 1
        last = i == len(lines) - 1
        space = (avail - words_w) / gaps if (justify and not last and gaps) else natural_space
        if gaps and not (justify and not last):
            space = min(natural_space, (avail - words_w) / gaps) if words_w + natural_space * gaps > avail else natural_space
        x = x0
        row = []
        for t, w in line:
            row.append((t, x))
            x += w + space
        placed.append(row)
    return placed, None


def _natural_space(para: Dict[str, Any]) -> float:
    gaps = []
    for l in para["lines"]:
        for a, b in zip(l, l[1:]):
            gaps.append(b["bbox"][0] - a["bbox"][2])
    last = [b["bbox"][0] - a["bbox"][2] for a, b in zip(para["lines"][-1], para["lines"][-1][1:])]
    pool = last if len(last) >= 2 else gaps
    return statistics.median(pool) if pool else para["lines"][0][0]["size"] * 0.33


def apply_edits(pdf_bytes: bytes, edits: List[Dict[str, str]]) -> Tuple[Optional[bytes], List[Dict[str, Any]]]:
    """edits: [{"id", "original", "text", "kind": "bullet"|"line"}]. Returns the
    edited PDF (None if nothing applied) and a per-edit report."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    report: List[Dict[str, Any]] = []
    pages = []
    for page in doc:
        lines = _words(page)
        pages.append((page, _Fonts(doc, page), _paragraphs(lines),
                      max((w["bbox"][2] for l in lines for w in l), default=page.rect.width - 36)))
    planned: Dict[int, List[Tuple[Dict[str, Any], list]]] = {}
    for e in edits:
        if _flat(e.get("original")) == _flat(e.get("text")):
            continue
        hit = None
        for page, fonts, paras, page_right in pages:
            para = _find(paras, e["original"], e.get("kind"))
            if para:
                hit = (page, fonts, para, page_right)
                break
        if not hit:
            report.append({"id": e.get("id"), "applied": False, "reason": "couldn't find this line in your PDF"})
            continue
        page, fonts, para, page_right = hit
        lines = para["lines"]
        ends = [l[-1]["bbox"][2] for l in lines]
        right = max(ends[:-1]) if len(lines) > 1 else page_right
        justify = len(lines) > 1 and all(abs(x - right) < 2.5 for x in ends[:-1])
        natural = _natural_space(para)
        justified_gaps = [b["bbox"][0] - a["bbox"][2] for l in lines[:-1] for a, b in zip(l, l[1:]) if b["bbox"][0] - a["bbox"][2] > 0.5]
        max_space = max(natural * 1.9, max(justified_gaps, default=natural) * 1.45)
        placed, reason = _layout(_new_tokens(para, e["text"]), fonts, para["x0"], right, len(lines), natural, justify, max_space)
        if not placed:
            report.append({"id": e.get("id"), "applied": False, "reason": reason})
            continue
        planned.setdefault(page.number, []).append((para, placed))
        report.append({"id": e.get("id"), "applied": True})
    if not planned:
        return None, report

    for page, fonts, _paras, _r in pages:
        jobs = planned.get(page.number)
        if not jobs:
            continue
        original_fonts = {f[0] for f in page.get_fonts(full=True)}
        for para, _placed in jobs:
            for l in para["lines"]:
                # A tight band around the baseline, so neighbouring lines are untouched.
                size = max(w["size"] for w in l)
                top, bottom = l[0]["base"] - size * 0.72, l[0]["base"] + size * 0.22
                page.add_redact_annot(pymupdf.Rect(l[0]["bbox"][0] - 0.4, top, l[-1]["bbox"][2] + 0.4, bottom), fill=False)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
        if len(page.get_contents()) > 1:
            page.clean_contents()
        main = page.get_contents()[0]
        for para, placed in jobs:
            for row, l in zip(placed, para["lines"]):
                # One writer per line and colour keeps the block in reading order.
                for color in dict.fromkeys(t["style"][2] for t, _x in row):
                    tw = None
                    for t, x in row:
                        name, size, c = t["style"]
                        if c != color:
                            continue
                        if name in fonts.builtin:
                            # Standard (non-embedded) fonts: written with standard encoding
                            # so the text extracts correctly.
                            page.insert_text((x, l[0]["base"]), t["text"], fontname=fonts.builtin[name], fontsize=size,
                                             color=pymupdf.sRGB_to_pdf(color))
                        else:
                            tw = tw or pymupdf.TextWriter(page.rect)
                            tw.append((x, l[0]["base"]), t["text"], font=fonts.get(name), fontsize=size)
                    if tw:
                        tw.write_text(page, color=pymupdf.sRGB_to_pdf(color))
            added = [x for x in page.get_contents() if x != main]
            blocks = [doc.xref_stream(x) for x in added]
            doc.xref_set_key(page.xref, "Contents", f"{main} 0 R")
            _splice(doc, page, main, page.rect.height - para["lines"][0][0]["base"] - 0.8, blocks)
        _fix_hyphens(doc, page, original_fonts)
    out = io.BytesIO()
    doc.save(out, garbage=3, deflate=True)
    return out.getvalue(), report


def _fix_hyphens(doc: pymupdf.Document, page: pymupdf.Page, original_fonts: set) -> None:
    """MuPDF maps the hyphen glyph of a re-embedded font to U+00AD (soft
    hyphen), which parsers drop ("production-ready" -> "productionready").
    Point it back at the ordinary hyphen in the fonts this module added."""
    for xref, *_ in page.get_fonts(full=True):
        if xref in original_fonts:
            continue
        m = re.search(r"/ToUnicode (\d+) 0 R", doc.xref_object(xref))
        if not m:
            continue
        cmap = doc.xref_stream(int(m.group(1)))
        fixed = re.sub(rb"<00[aA][dD]>", b"<002d>", cmap)
        if fixed != cmap:
            doc.update_stream(int(m.group(1)), fixed)


# ---------------------------------------------------------------------------
# Keeping the text in reading order
# ---------------------------------------------------------------------------
# New text written by PyMuPDF lands at the end of the page's content stream.
# Position-based parsers don't care, but stream-order parsers (Apache Tika /
# PDFBox's default) would read edited bullets after everything else. So each
# new block is spliced into the stream exactly where the removed lines were:
# just before the positioning operator of the first line below them.

_DELIM = b"()<>[]{}/%"
_WS = b" \t\r\n\f\x00"


def _tokens(data: bytes):
    """(kind, value, start, end) for a PDF content stream."""
    i, n = 0, len(data)
    while i < n:
        c = data[i:i + 1]
        if c in (b" ", b"\t", b"\r", b"\n", b"\f", b"\x00"):
            i += 1
        elif c == b"%":
            while i < n and data[i:i + 1] not in (b"\r", b"\n"):
                i += 1
        elif c == b"(":
            start, depth = i, 0
            while i < n:
                ch = data[i:i + 1]
                if ch == b"\\":
                    i += 2
                    continue
                if ch == b"(":
                    depth += 1
                elif ch == b")":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            yield ("str", None, start, i)
        elif c == b"<":
            if data[i:i + 2] == b"<<":
                yield ("dict", b"<<", i, i + 2)
                i += 2
            else:
                j = data.index(b">", i)
                yield ("str", None, i, j + 1)
                i = j + 1
        elif c == b">" and data[i:i + 2] == b">>":
            yield ("dict", b">>", i, i + 2)
            i += 2
        elif c in (b"[", b"]"):
            yield ("arr", c, i, i + 1)
            i += 1
        elif c == b"/":
            j = i + 1
            while j < n and data[j:j + 1] not in _WS and data[j:j + 1] not in _DELIM:
                j += 1
            yield ("name", data[i:j], i, j)
            i = j
        else:
            j = i
            while j < n and data[j:j + 1] not in _WS and data[j:j + 1] not in _DELIM:
                j += 1
            if j == i:
                j = i + 1
            word = data[i:j]
            try:
                yield ("num", float(word), i, j)
            except ValueError:
                yield ("op", word, i, j)
                if word == b"ID":  # inline image data runs to EI
                    k = data.find(b"EI", j)
                    j = k + 2 if k >= 0 else n
            i = j


def _mul(m1, m2):
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (a1 * a2 + b1 * c2, a1 * b2 + b1 * d2, c1 * a2 + d1 * c2, c1 * b2 + d1 * d2,
            e1 * a2 + f1 * c2 + e2, e1 * b2 + f1 * d2 + f2)


_I = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _insertion_point(data: bytes, below_y: float):
    """Offset to splice at and the text line matrix to restore there, for the
    first text drawn below user-space y `below_y` (None: append at the end)."""
    ctm, stack, tlm, tl, in_bt = _I, [], _I, 0.0, False
    operands, op_start = [], None
    last_pos = None  # (offset, tlm before it) of the latest positioning operator
    for kind, val, start, end in _tokens(data):
        if kind != "op":
            if op_start is None:
                op_start = start
            if kind == "num":
                operands.append(val)
            continue
        begin = op_start if op_start is not None else start
        op_start = None
        nums, operands = operands, []
        if val == b"q":
            stack.append(ctm)
        elif val == b"Q":
            ctm = stack.pop() if stack else _I
        elif val == b"cm" and len(nums) >= 6:
            ctm = _mul(tuple(nums[-6:]), ctm)
        elif val == b"BT":
            in_bt, tlm = True, _I
        elif val == b"ET":
            in_bt = False
        elif val in (b"Td", b"TD", b"Tm", b"T*", b"'", b'"'):
            last_pos = (begin, tlm, ctm)
            if val in (b"Td", b"TD") and len(nums) >= 2:
                if val == b"TD":
                    tl = -nums[-1]
                tlm = _mul((1, 0, 0, 1, nums[-2], nums[-1]), tlm)
            elif val == b"Tm" and len(nums) >= 6:
                tlm = tuple(nums[-6:])
            else:
                tlm = _mul((1, 0, 0, 1, 0, -tl), tlm)
        elif val == b"TL" and nums:
            tl = nums[-1]
        if val in (b"Tj", b"TJ", b"'", b'"') and in_bt:
            y = _mul(tlm, ctm)[5]
            if y < below_y and last_pos:
                return last_pos
    return None


def _splice(doc: pymupdf.Document, page: pymupdf.Page, main_xref: int, below_y: float, blocks: List[bytes]) -> None:
    data = doc.xref_stream(main_xref)
    block = b"\n".join(blocks)
    hit = _insertion_point(data, below_y)
    if hit is None:
        data = data + b"\n" + block + b"\n"
    else:
        at, tlm, ctm = hit
        # The block was written for an identity CTM; undo any active cm.
        if ctm != _I:
            a, b, c, d, e, f = ctm
            det = a * d - b * c
            inv = (d / det, -b / det, -c / det, a / det, (c * f - d * e) / det, (b * e - a * f) / det)
            block = b"q " + " ".join(f"{v:.6g}" for v in inv).encode() + b" cm\n" + block + b"\nQ"
        restore = " ".join(f"{v:.6g}" for v in tlm).encode() + b" Tm\n"
        data = data[:at] + b"\nET\n" + block + b"\nBT\n" + restore + data[at:]
    doc.update_stream(main_xref, data)
