import csv
#!/usr/bin/env python3
"""Relatório em PDF da liga: rankings + uma página por time (estilo research de banco de investimento).

Usa os mesmos cálculos do rankings.py (valor atual, teto calibrado, starting five por posição).
Os gráficos são desenhados direto no ReportLab, então o PDF sai igual em qualquer máquina.

Uso:
    python make_report.py                 # gera reports/<liga>_preseason.pdf
    python make_report.py caminho.pdf     # gera em outro caminho
Requer: reportlab (pip install reportlab).
"""
import datetime
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from xml.sax.saxutils import escape as xesc

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, FrameBreak, KeepTogether,
                                NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

import rankings as rk
from config import DATA_DIR, LEAGUE_ID

LEAGUE_NAME = "Basquetobol Teorico Diplos"
SEASON_LABEL = "2026-27"
ROOT = Path(__file__).parent

# ---------------------------------------------------------------- paleta (neutra, azul-marinho)
NAVY = colors.HexColor("#0B2545")
BLUE = colors.HexColor("#1D5FA8")
LIGHT = colors.HexColor("#A9C7EA")
PALE = colors.HexColor("#EEF3F9")
INK = colors.HexColor("#1A2230")
GREY = colors.HexColor("#5B6573")
MUTED = colors.HexColor("#8A94A3")
RULE = colors.HexColor("#C9D1DC")
GREEN = colors.HexColor("#1E7A5A")
RUST = colors.HexColor("#B3412E")
AMBER = colors.HexColor("#C4733B")

W_PAGE, H_PAGE = A4
MARGIN_X = 18 * mm
CONTENT_W = W_PAGE - 2 * MARGIN_X

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]

METRICS = [
    ("power", "Power rank", "FP/jogo, 10 melhores"),
    ("starting_five", "Starting five", "FP/jogo, uma vaga por posição"),
    ("depth", "Depth", "FP/jogo, 8 seguintes"),
    ("teto_time", "Teto", "FP/jogo, 10 maiores tetos"),
    ("proj_temporada", "Projeção de temporada", "FP totais ESPN"),
]
LABEL = {k: l for k, l, _ in METRICS}
RATING_COLOR = {"Overweight": GREEN, "Equal-weight": GREY, "Underweight": RUST}
RATING_DESC = {"Overweight": "acima da média da liga", "Equal-weight": "em linha com a liga",
               "Underweight": "abaixo da média da liga"}


# ---------------------------------------------------------------- estilos
def S(name, **kw):
    base = dict(fontName="Helvetica", fontSize=9.3, leading=13, textColor=INK)
    base.update(kw)
    return ParagraphStyle(name, **base)


ST = {
    "kicker": S("kicker", fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=BLUE, charSpace=1.2),
    "title": S("title", fontName="Helvetica-Bold", fontSize=23, leading=26, textColor=NAVY),
    "sub": S("sub", fontSize=11.5, leading=15.5, textColor=GREY),
    "h1": S("h1", fontName="Helvetica-Bold", fontSize=15.5, leading=19, textColor=NAVY),
    "h2": S("h2", fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=NAVY, spaceBefore=8, spaceAfter=3),
    "body": S("body"),
    "bullet": S("bullet", leftIndent=11, bulletIndent=0, spaceAfter=3.2),
    "small": S("small", fontSize=7.6, leading=10.2, textColor=GREY),
    "cell": S("cell", fontSize=8.2, leading=10.2),
    "cellb": S("cellb", fontName="Helvetica-Bold", fontSize=8.2, leading=10.2),
    "cellr": S("cellr", fontSize=8.2, leading=10.2, alignment=TA_RIGHT),
    "th": S("th", fontName="Helvetica-Bold", fontSize=7.2, leading=9, textColor=NAVY),
    "thr": S("thr", fontName="Helvetica-Bold", fontSize=7.2, leading=9, textColor=NAVY, alignment=TA_RIGHT),
    "box_h": S("box_h", fontName="Helvetica-Bold", fontSize=7.4, leading=9.5, textColor=BLUE, charSpace=1),
    "box": S("box", fontSize=8.4, leading=11.2),
    "team": S("team", fontName="Helvetica-Bold", fontSize=19, leading=22, textColor=NAVY),
}


def esc(s):
    return xesc(str(s))


def P(text, style="body"):
    return Paragraph(text, ST[style])


def bullets(items, style="bullet"):
    return [Paragraph(t, ST[style], bulletText="•") for t in items]


def data_extenso(d):
    return "%d de %s de %d" % (d.day, MESES[d.month - 1], d.year)


def pt(x, n=1):
    """Número no formato pt-BR."""
    s = f"{x:,.{n}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def signed(x, n=1):
    s = pt(abs(x), n)
    return ("+" if x >= 0 else "-") + s


def short_name(n):
    parts = n.split()
    if len(parts) == 1 or (parts[0].isupper() and len(parts[0]) <= 3):
        return n
    return "%s. %s" % (parts[0][0], " ".join(parts[1:]))


def compact_name(n):
    s = short_name(n)
    s = s if len(s) <= 18 else " ".join(n.split()[1:])
    if len(s) > 15:
        i, _, rest = s.partition(" ")
        s = (i + " " if rest else "") + (rest or i)[:12].rstrip("-") + "."
    return s


def join_pt(items):
    items = list(items)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " e " + items[-1]


# ---------------------------------------------------------------- dados
def val(p):
    return p["value"] if p["value"] != "" else 0.0


def parse_calibration():
    tiers, rookies = [], []
    f = DATA_DIR / "teto_calibration.md"
    if not f.exists():
        return tiers, rookies
    num_row = re.compile(r"^\|\s*(.+?)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|$")
    for line in f.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith(("| Elite", "| Médio", "| Baixo")):
            tiers.append(cells)
        else:
            m = num_row.match(line)
            if m:
                rookies.append((m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4))))
    return tiers, rookies


def build():
    players = rk.load()
    rows = rk.team_table(players)
    by_team = defaultdict(list)
    for p in players:
        by_team[p["team_name"]].append(p)
    ranked_players = sorted(players, key=val, reverse=True)
    for i, p in enumerate(ranked_players, 1):
        p["lrank"] = i

    conf_map = {}
    with open(DATA_DIR / "teams.csv", encoding="utf-8") as fh:
        conf_map = {r["team_name"]: r["conferencia"] for r in csv.DictReader(fh)}
    teams = {}
    for r in rows:
        ps = sorted(by_team[r["time"]], key=val, reverse=True)
        lineup, depth = rk.best_five(ps)
        teams[r["time"]] = {"name": r["time"], "owner": r["dono"], "m": {k: r[k] for k, _, _ in METRICS},
                            "players": ps, "lineup": lineup, "depth": depth, "rank": {}, "conf": conf_map.get(r["time"], "")}
    for key, _, _ in METRICS:
        order = sorted(teams.values(), key=lambda t: t["m"][key], reverse=True)
        for i, t in enumerate(order, 1):
            t["rank"][key] = i
    means = {k: statistics.mean(t["m"][k] for t in teams.values()) for k, _, _ in METRICS}
    for t in teams.values():
        t["avg_rank"] = statistics.mean(t["rank"].values())
    order = sorted(teams.values(), key=lambda t: (t["avg_rank"], t["rank"]["power"]))
    for i, t in enumerate(order):
        t["overall"] = i + 1
        t["rating"] = "Overweight" if i < 4 else "Equal-weight" if i < 8 else "Underweight"

    for t in teams.values():
        ps = t["players"]
        healthy = sorted([p for p in ps if p["saudavel"]], key=lambda p: p["value_atual"], reverse=True)
        t["out"] = [p for p in ps if not p["saudavel"]]
        t["dtd"] = [p for p in ps if p["injury_status"] == "DAY_TO_DAY"]
        t["rookies"] = [p for p in ps if p["prev_fp"] == "" and p["proj_fp"] != ""]
        t["nodata"] = [p for p in ps if p["fonte_valor"] == "sem dado"]
        t["top10"] = healthy[:10]
        power = t["m"]["power"]
        t["top3_share"] = (sum(p["value_atual"] for p in healthy[:3]) / power) if power else 0.0
        t["gap"] = t["m"]["teto_time"] - power
        t["fallback"] = [(s, p) for s, (p, fb) in t["lineup"].items() if fb]
    gaps = sorted(teams.values(), key=lambda t: t["gap"], reverse=True)
    for i, t in enumerate(gaps, 1):
        t["gap_rank"] = i

    tiers, rookies = parse_calibration()
    try:
        params = json.loads((DATA_DIR / "teto_params.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        params = {}
    ctx = {
        "players": players, "teams": teams, "order": order, "means": means, "tiers": tiers,
        "rookies": rookies, "params": params,
        "pos_count": Counter(p["position"] for p in players),
        "top3_median": statistics.median(t["top3_share"] for t in teams.values()),
        "n_out": sum(1 for p in players if not p["saudavel"]),
        "n_dtd": sum(1 for p in players if p["injury_status"] == "DAY_TO_DAY"),
        "today": datetime.date.today(),
    }
    return ctx


def fmt_metric(key, v):
    return pt(v, 0) if key == "proj_temporada" else pt(v, 1)


# ---------------------------------------------------------------- flowables gráficos
class DevBars(Flowable):
    """Barras de desvio em relação à média da liga; o valor absoluto fica na coluna da direita."""

    def __init__(self, rows, width, mean, key, row_h=21):
        super().__init__()
        self.rows, self.width, self.mean, self.key, self.row_h = rows, width, mean, key, row_h
        self.height = row_h * len(rows) + 22

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c, W, H = self.canv, self.width, self.height
        rank_w, name_w, val_w, pad = 16, 150, 52, 6
        x0, x1 = rank_w + name_w, W - val_w
        area = x1 - x0 - 2 * pad
        devs = [r["value"] - self.mean for r in self.rows]
        lo, hi = min(min(devs), 0), max(max(devs), 0)
        span = (hi - lo) or 1
        sc = area / span
        zero = x0 + pad + (-lo) * sc
        top = H - 22
        c.setFont("Helvetica-Bold", 6.8)
        c.setFillColor(GREY)
        c.drawString(0, H - 11, "#")
        c.drawString(rank_w, H - 11, "TIME / DONO")
        c.drawRightString(W, H - 11, "VALOR")
        c.drawCentredString((x0 + x1) / 2, H - 11, "DESVIO VS MÉDIA DA LIGA (%s)" % fmt_metric(self.key, self.mean))
        c.setStrokeColor(NAVY)
        c.setLineWidth(1)
        c.line(0, top, W, top)
        for i, r in enumerate(self.rows):
            y = top - (i + 1) * self.row_h
            c.setStrokeColor(RULE)
            c.setLineWidth(0.4)
            c.line(0, y, W, y)
            c.setFillColor(GREY)
            c.setFont("Helvetica-Bold", 8)
            c.drawString(0, y + self.row_h / 2 - 3, str(r["rank"]))
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 8.3)
            c.drawString(rank_w, y + self.row_h - 9, r["name"])
            c.setFillColor(GREY)
            c.setFont("Helvetica", 6.8)
            c.drawString(rank_w, y + 4, r["owner"])
            d = r["value"] - self.mean
            bh = 8.5
            by = y + (self.row_h - bh) / 2
            c.setFillColor(BLUE if d >= 0 else AMBER)
            if d >= 0:
                c.rect(zero, by, max(d * sc, 0.8), bh, fill=1, stroke=0)
            else:
                c.rect(zero + d * sc, by, -d * sc, bh, fill=1, stroke=0)
            c.setFillColor(NAVY)
            c.setFont("Helvetica-Bold", 9)
            c.drawRightString(W, y + self.row_h / 2 - 3, fmt_metric(self.key, r["value"]))
        c.setStrokeColor(NAVY)
        c.setLineWidth(0.9)
        c.line(zero, 0, zero, top)


class PlayerBar(Flowable):
    """Barra de valor atual com faixa clara até o teto."""

    def __init__(self, value, teto, maxv, width=150, height=9, out=False):
        super().__init__()
        self.value, self.teto, self.maxv, self.width, self.height, self.out = value, teto, maxv, width, height, out

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c = self.canv
        sc = self.width / self.maxv
        h = self.height
        if self.value == "":
            c.setFillColor(MUTED)
            c.setFont("Helvetica-Oblique", 7)
            c.drawString(0, 1.5, "sem dados")
            return
        if self.out:
            c.setStrokeColor(MUTED)
            c.setDash(2, 2)
            c.setLineWidth(0.8)
            c.rect(0, 0, self.value * sc, h, fill=0, stroke=1)
            c.setDash()
            return
        if self.teto != "" and self.teto > self.value:
            c.setFillColor(LIGHT)
            c.rect(self.value * sc, 0, (self.teto - self.value) * sc, h, fill=1, stroke=0)
        c.setFillColor(BLUE)
        c.rect(0, 0, self.value * sc, h, fill=1, stroke=0)


class Pill(Flowable):
    def __init__(self, text, color, width=92, height=19):
        super().__init__()
        self.text, self.color, self.width, self.height = text, color, width, height

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(self.color)
        c.roundRect(0, 0, self.width, self.height, 4, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8.4)
        c.drawCentredString(self.width / 2, self.height / 2 - 3, self.text.upper())


class KPIStrip(Flowable):
    def __init__(self, items, width, height=54):
        super().__init__()
        self.items, self.width, self.height = items, width, height

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c = self.canv
        n = len(self.items)
        gap = 6
        bw = (self.width - gap * (n - 1)) / n
        for i, (label, big, sub) in enumerate(self.items):
            x = i * (bw + gap)
            c.setFillColor(PALE)
            c.rect(x, 0, bw, self.height, fill=1, stroke=0)
            c.setFillColor(BLUE)
            c.rect(x, self.height - 2, bw, 2, fill=1, stroke=0)
            c.setFillColor(GREY)
            c.setFont("Helvetica-Bold", 6.6)
            c.drawString(x + 6, self.height - 13, label.upper())
            c.setFillColor(NAVY)
            c.setFont("Helvetica-Bold", 17)
            c.drawString(x + 6, self.height - 33, big)
            c.setFillColor(GREY)
            c.setFont("Helvetica", 7)
            c.drawString(x + 6, 6, sub)


class Scatter(Flowable):
    """Piso (power) x teto, com tendência linear e rótulos sem colisão."""

    def __init__(self, pts, width, height, xlabel, ylabel):
        super().__init__()
        self.pts, self.width, self.height, self.xlabel, self.ylabel = pts, width, height, xlabel, ylabel

    def wrap(self, aw, ah):
        return self.width, self.height

    @staticmethod
    def nice_ticks(lo, hi, n=5):
        raw = (hi - lo) / n
        mag = 10 ** int(math.floor(math.log10(raw)))
        step = min((m * mag for m in (1, 2, 5, 10) if m * mag >= raw), default=mag)
        start = int(lo // step) * step
        ticks, t = [], start
        while t <= hi + 1e-9:
            if t >= lo - 1e-9:
                ticks.append(t)
            t += step
        return ticks

    def draw(self):
        c = self.canv
        L, B, T, R = 44, 34, 8, 16
        pw, ph = self.width - L - R, self.height - B - T
        xs = [p[1] for p in self.pts]
        ys = [p[2] for p in self.pts]
        px, py = (max(xs) - min(xs)) * 0.12, (max(ys) - min(ys)) * 0.14
        x0, x1, y0, y1 = min(xs) - px, max(xs) + px, min(ys) - py, max(ys) + py
        fx = lambda v: L + (v - x0) / (x1 - x0) * pw
        fy = lambda v: B + (v - y0) / (y1 - y0) * ph
        c.setFont("Helvetica", 7)
        for tv in self.nice_ticks(x0, x1):
            c.setStrokeColor(RULE)
            c.setLineWidth(0.4)
            c.line(fx(tv), B, fx(tv), B + ph)
            c.setFillColor(GREY)
            c.drawCentredString(fx(tv), B - 11, pt(tv, 0))
        for tv in self.nice_ticks(y0, y1):
            c.setStrokeColor(RULE)
            c.setLineWidth(0.4)
            c.line(L, fy(tv), L + pw, fy(tv))
            c.setFillColor(GREY)
            c.drawRightString(L - 5, fy(tv) - 2.5, pt(tv, 0))
        c.setStrokeColor(NAVY)
        c.setLineWidth(0.9)
        c.line(L, B, L + pw, B)
        c.line(L, B, L, B + ph)
        c.setFillColor(GREY)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(L + pw / 2, 4, self.xlabel)
        c.saveState()
        c.translate(10, B + ph / 2)
        c.rotate(90)
        c.drawCentredString(0, 0, self.ylabel)
        c.restoreState()
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        sxx = sum((x - mx) ** 2 for x in xs)
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0
        c.setStrokeColor(MUTED)
        c.setLineWidth(0.9)
        c.setDash(3, 3)
        c.line(fx(x0), fy(my + slope * (x0 - mx)), fx(x1), fy(my + slope * (x1 - mx)))
        c.setDash()
        placed = [(fx(x) - 4, fy(y) - 4, fx(x) + 4, fy(y) + 4) for _, x, y in self.pts]
        c.setFont("Helvetica-Bold", 7.2)
        for label, x, y in self.pts:
            cx, cy = fx(x), fy(y)
            c.setFillColor(BLUE)
            c.setStrokeColor(colors.white)
            c.setLineWidth(1)
            c.circle(cx, cy, 3.6, fill=1, stroke=1)
            w = stringWidth(label, "Helvetica-Bold", 7.2)
            cands = [(6, -2.5), (-6 - w, -2.5), (-w / 2, 6), (-w / 2, -12), (6, 5), (-6 - w, 5), (6, -10), (-6 - w, -10)]
            best, best_ov = None, None
            for dx, dy in cands:
                r = (cx + dx, cy + dy, cx + dx + w, cy + dy + 8)
                inside = r[0] >= L and r[2] <= self.width and r[1] >= B and r[3] <= B + ph + T
                ov = 0 if inside else 1e6
                for q in placed:
                    ox = min(r[2], q[2]) - max(r[0], q[0])
                    oy = min(r[3], q[3]) - max(r[1], q[1])
                    if ox > 0 and oy > 0:
                        ov += ox * oy
                if best_ov is None or ov < best_ov:
                    best, best_ov = r, ov
                if ov == 0:
                    break
            placed.append(best)
            c.setFillColor(INK)
            c.drawString(best[0], best[1] + 1.5, label)


# ---------------------------------------------------------------- tabelas
def base_table_style(extra=None):
    st = [("LINEBELOW", (0, 0), (-1, 0), 1, NAVY),
          ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
          ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    return TableStyle(st + (extra or []))


def make_table(header, rows, widths, right_cols=(), extra=None, repeat=1):
    head = [Paragraph(esc(h), ST["thr"] if i in right_cols else ST["th"]) for i, h in enumerate(header)]
    body = []
    for r in rows:
        line = []
        for i, cell in enumerate(r):
            if isinstance(cell, str):
                line.append(Paragraph(cell, ST["cellr"] if i in right_cols else ST["cell"]))
            else:
                line.append(cell)
        body.append(line)
    t = Table([head] + body, colWidths=widths, repeatRows=repeat)
    t.setStyle(base_table_style(extra))
    return t


# ---------------------------------------------------------------- páginas de chrome
def chrome_factory(ctx):
    date_txt = data_extenso(ctx["today"])

    def chrome(canv, doc):
        canv.saveState()
        canv.setFillColor(NAVY)
        canv.rect(0, H_PAGE - 6, W_PAGE, 6, fill=1, stroke=0)
        canv.setFont("Helvetica-Bold", 7.4)
        canv.drawString(MARGIN_X, H_PAGE - 19 * mm + 4, LEAGUE_NAME.upper())
        canv.setFont("Helvetica", 7.4)
        canv.setFillColor(GREY)
        canv.drawRightString(W_PAGE - MARGIN_X, H_PAGE - 19 * mm + 4, "Fantasy NBA Research  |  Preseason %s  |  %s" % (SEASON_LABEL, date_txt))
        canv.setStrokeColor(RULE)
        canv.setLineWidth(0.5)
        canv.line(MARGIN_X, H_PAGE - 19 * mm, W_PAGE - MARGIN_X, H_PAGE - 19 * mm)
        footer(canv)
        canv.restoreState()

    def cover(canv, doc):
        canv.saveState()
        bh = 40 * mm
        canv.setFillColor(NAVY)
        canv.rect(0, H_PAGE - bh, W_PAGE, bh, fill=1, stroke=0)
        canv.setFillColor(LIGHT)
        canv.setFont("Helvetica-Bold", 7.6)
        canv.drawString(MARGIN_X, H_PAGE - 13 * mm, "FANTASY NBA RESEARCH   |   PRESEASON %s" % SEASON_LABEL)
        canv.setFillColor(colors.white)
        canv.setFont("Helvetica-Bold", 25)
        canv.drawString(MARGIN_X, H_PAGE - 25 * mm, LEAGUE_NAME)
        canv.setFont("Helvetica", 9.5)
        canv.setFillColor(LIGHT)
        canv.drawString(MARGIN_X, H_PAGE - 33 * mm, "Rankings da liga e análise por time  |  Liga ESPN %s" % LEAGUE_ID)
        canv.drawRightString(W_PAGE - MARGIN_X, H_PAGE - 33 * mm, date_txt)
        footer(canv)
        canv.restoreState()

    def footer(canv):
        canv.setStrokeColor(RULE)
        canv.setLineWidth(0.5)
        canv.line(MARGIN_X, 17 * mm, W_PAGE - MARGIN_X, 17 * mm)
        canv.setFont("Helvetica", 6.8)
        canv.setFillColor(GREY)
        canv.drawString(MARGIN_X, 13 * mm, "Fonte: ESPN Fantasy Basketball, NBA Stats; cálculos próprios. Valores em fantasy points (FP) no scoring da liga.")
        canv.drawString(MARGIN_X, 9.5 * mm, "Documento informal entre amigos. Não constitui recomendação de investimento.")
        canv.setFont("Helvetica-Bold", 7.4)
        canv.drawRightString(W_PAGE - MARGIN_X, 13 * mm, "Página %d" % canv.getPageNumber())

    return chrome, cover


# ---------------------------------------------------------------- texto analítico
def strengths_weaknesses(t, ctx):
    R, M, means = t["rank"], t["m"], ctx["means"]
    out, dtd, rookies = t["out"], t["dtd"], t["rookies"]

    def metric_line(key):
        d = M[key] - means[key]
        unit = "FP" if key == "proj_temporada" else "FP/jogo"
        return "<b>%s: %dº de 12</b> (%s %s, %s vs a média da liga)." % (
            LABEL[key], R[key], fmt_metric(key, M[key]), unit, signed(d, 0 if key == "proj_temporada" else 1))

    by_rank = sorted([k for k, _, _ in METRICS], key=lambda k: R[k])
    s, w = [], []
    for k in by_rank:
        if R[k] <= 5 and M[k] > means[k] and len(s) < 2:
            s.append(metric_line(k))
    best = max([p for p in t["players"] if p["saudavel"]], key=lambda p: p["value_atual"])
    if best["lrank"] <= 8:
        s.append("<b>Âncora de elite:</b> %s, %s FP/jogo, o %dº maior valor entre os 156 jogadores draftados." % (
            esc(best["player_name"]), pt(best["value_atual"]), best["lrank"]))
    if t["gap_rank"] <= 3:
        s.append("<b>Margem de crescimento:</b> o teto soma %s FP/jogo sobre o power, o %dº maior espaço da liga." % (
            signed(t["gap"]), t["gap_rank"]))
    bets = sorted([p for p in rookies if p["proj_fp"] >= 28 and p["teto"] != ""], key=lambda p: p["teto"], reverse=True)[:2]
    if bets:
        s.append("<b>Apostas de upside:</b> %s." % join_pt(
            "%s (projeção %s, teto %s)" % (esc(p["player_name"]), pt(p["proj_fp"]), pt(p["teto"])) for p in bets))
    if not out and not dtd:
        s.append("<b>Elenco saudável:</b> nenhum jogador fora ou em dúvida no momento.")
    if not t["fallback"]:
        s.append("<b>Starting five completo:</b> há titular natural nas cinco posições, sem improviso.")
    if len(s) < 2:
        s.append("Melhor frente: " + metric_line(by_rank[0]))
    s = s[:4]

    for k in reversed(by_rank):
        if R[k] >= 8 and M[k] < means[k] and len(w) < 2:
            w.append(metric_line(k))
    if out:
        w.append("<b>Desfalques:</b> %s fora (somam %s FP/jogo que não entram no valor atual)." % (
            join_pt(esc(p["player_name"]) for p in out), pt(sum(val(p) for p in out))))
    if t["fallback"]:
        w.append("<b>Posição sem titular natural:</b> %s." % join_pt(
            "%s improvisado com %s (%s)" % (slot, esc(p["player_name"]), p["position"]) for slot, p in t["fallback"]))
    if len(t["depth"]) < 8:
        w.append("<b>Banco curto:</b> só %d jogadores saudáveis além do starting five (o cálculo prevê 8)." % len(t["depth"]))
    if t["top3_share"] >= ctx["top3_median"] + 0.02:
        w.append("<b>Concentração:</b> os 3 maiores valores respondem por %s%% do power (mediana da liga: %s%%)." % (
            pt(t["top3_share"] * 100, 0), pt(ctx["top3_median"] * 100, 0)))
    if len(dtd) >= 2:
        w.append("<b>Dúvidas físicas:</b> %s aparecem como day-to-day e o valor atual os conta como disponíveis." % join_pt(
            esc(p["player_name"]) for p in dtd))
    top10_rookies = [p for p in t["top10"] if p in rookies]
    if len(top10_rookies) >= 2 and ctx["rookies"]:
        ratios = [r[3] for r in ctx["rookies"]]
        w.append("<b>Dependência de estreantes:</b> %d dos 10 maiores valores são rookies, e a turma de 2025-26 rendeu de %s a %s da projeção (mediana %s)." % (
            len(top10_rookies), pt(min(ratios), 2), pt(max(ratios), 2), pt(statistics.median(ratios), 2)))
    if t["gap_rank"] >= 10:
        w.append("<b>Pouca folga de crescimento:</b> o teto soma só %s FP/jogo sobre o power, o %dº espaço entre 12 times." % (
            signed(t["gap"]), t["gap_rank"]))
    if t["nodata"]:
        w.append("<b>Sem dados:</b> %s sem projeção nem histórico no ESPN, fora do cálculo." % join_pt(
            esc(p["player_name"]) for p in t["nodata"]))
    if len(w) < 2:
        w.append("Pior frente: " + metric_line(by_rank[-1]))
    w = w[:4]
    return s, w


def ranking_commentary(key, ctx):
    teams = list(ctx["teams"].values())
    order = sorted(teams, key=lambda t: t["m"][key], reverse=True)
    a, b, z = order[0], order[1], order[-1]
    spread = a["m"][key] - z["m"][key]
    mean = ctx["means"][key]
    nf = 0 if key == "proj_temporada" else 1
    unit = "FP" if key == "proj_temporada" else "FP/jogo"
    paras = []
    p1 = "<b>%s</b> lidera com %s %s, %s à frente de %s. O último, %s, tem %s; a distância entre os extremos é de %s %s (%s%% do valor do último)." % (
        esc(a["name"]), fmt_metric(key, a["m"][key]), unit, pt(a["m"][key] - b["m"][key], nf), esc(b["name"]),
        esc(z["name"]), fmt_metric(key, z["m"][key]), pt(spread, nf), unit, pt(spread / z["m"][key] * 100, 0))
    paras.append(p1)
    return paras, order, mean


# ---------------------------------------------------------------- montagem do documento
def build_story(ctx):
    teams, order, means = ctx["teams"], ctx["order"], ctx["means"]
    n_teams = len(teams)
    story = []

    # ---------- capa: coluna principal
    lead = order[0]
    first_metrics = [LABEL[k] for k, _, _ in METRICS if lead["rank"][k] == 1]
    story += [Spacer(1, 4), P("PRESEASON %s  |  VISÃO GERAL DA LIGA" % SEASON_LABEL, "kicker"), Spacer(1, 4),
              P("%s abre a pré-temporada como favorito" % esc(lead["name"]), "title"), Spacer(1, 6),
              P("Cinco rankings, um rating por time e uma página de análise para cada elenco, calculados em fantasy points "
                "com os dados do draft de %s." % data_extenso(ctx["today"]), "sub"), Spacer(1, 10)]

    takeaways = []
    takeaways.append("<b>%s</b> (%s) tem o melhor rank médio dos cinco rankings (%s)%s. Completam o bloco de cima %s." % (
        esc(lead["name"]), esc(lead["owner"]), pt(lead["avg_rank"], 1),
        (", liderando em " + join_pt(first_metrics)) if first_metrics else "",
        join_pt("<b>%s</b>" % esc(t["name"]) for t in order[1:4])))
    spread = sorted(teams.values(), key=lambda t: max(t["rank"].values()) - min(t["rank"].values()), reverse=True)[0]
    bk = min(spread["rank"], key=lambda k: spread["rank"][k])
    wk = max(spread["rank"], key=lambda k: spread["rank"][k])
    takeaways.append("<b>%s</b> é o time mais desbalanceado: %dº em %s, mas %dº em %s." % (
        esc(spread["name"]), spread["rank"][bk], LABEL[bk], spread["rank"][wk], LABEL[wk]))
    teto_order = sorted(teams.values(), key=lambda t: t["m"]["teto_time"], reverse=True)
    d12 = teto_order[0]["m"]["teto_time"] - teto_order[1]["m"]["teto_time"]
    takeaways.append("No teto, <b>%s</b> (%s) e <b>%s</b> (%s) lideram%s." % (
        esc(teto_order[0]["name"]), pt(teto_order[0]["m"]["teto_time"]), esc(teto_order[1]["name"]),
        pt(teto_order[1]["m"]["teto_time"]), " com diferença menor que 1 ponto, um empate técnico" if d12 < 1 else ""))
    pc = ctx["pos_count"]
    scarce = min(pc, key=lambda k: pc[k])
    plenty = max(pc, key=lambda k: pc[k])
    n_fb = sum(len(t["fallback"]) for t in teams.values())
    takeaways.append("<b>%s</b> é a posição mais escassa (%d jogadores, contra %d em %s); %d time(s) tiveram de improvisar uma vaga no starting five." % (
        scarce, pc[scarce], pc[plenty], plenty, n_fb))
    takeaways.append("Só %d jogador(es) estão fora e %d aparecem em dúvida (day-to-day); lesão pesa pouco hoje, mas muda rápido." % (
        ctx["n_out"], ctx["n_dtd"]))
    story += [P("PRINCIPAIS CONCLUSÕES", "box_h"), Spacer(1, 3)] + bullets(takeaways)
    story += [Spacer(1, 6), P("COMO LER", "box_h"), Spacer(1, 3),
              P("<b>Valor</b> é a média de fantasy points por jogo (80% temporada passada, 20% projeção ESPN). <b>Teto</b> é o melhor cenário "
                "realista da temporada: a projeção multiplicada pelo percentil 80 de quanto jogadores do mesmo nível superaram a projeção em 2025-26. "
                "O <b>rating</b> divide os 12 times em terços pelo rank médio. A metodologia completa está na página 3.", "body")]
    story.append(FrameBreak())

    # ---------- capa: barra lateral
    def sidebox(title, lines):
        rows = [[Paragraph(title, ST["box_h"])]] + [[Paragraph(l, ST["box"])] for l in lines]
        tb = Table(rows, colWidths=[145])
        tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE), ("LINEABOVE", (0, 0), (-1, 0), 2, BLUE),
                                ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                                ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
                                ("TOPPADDING", (0, 0), (-1, 0), 6)]))
        return tb

    for rating in ("Overweight", "Equal-weight", "Underweight"):
        names = [t for t in order if t["rating"] == rating]
        col = RATING_COLOR[rating].hexval()[2:]
        story.append(sidebox('<font color="#%s">%s</font>  <font color="#5B6573">%s</font>' % (col, rating.upper(), RATING_DESC[rating]),
                             ["%d. %s" % (t["overall"], esc(t["name"])) for t in names]))
        story.append(Spacer(1, 7))
    best_depth = min(teams.values(), key=lambda t: t["rank"]["depth"])
    best_five = min(teams.values(), key=lambda t: t["rank"]["starting_five"])
    best_teto = min(teams.values(), key=lambda t: t["rank"]["teto_time"])
    story.append(sidebox("DESTAQUES", [
        "<b>Melhor starting five</b><br/>%s (%s)" % (esc(best_five["name"]), pt(best_five["m"]["starting_five"])),
        "<b>Melhor banco</b><br/>%s (%s)" % (esc(best_depth["name"]), pt(best_depth["m"]["depth"])),
        "<b>Maior teto</b><br/>%s (%s)" % (esc(best_teto["name"]), pt(best_teto["m"]["teto_time"]))]))
    story.append(Spacer(1, 7))
    story.append(sidebox("A LIGA", [
        "12 times, 156 jogadores", "Pontos por jogo (scoring ESPN)", "Draft realizado em %s" % data_extenso(ctx["today"])]))
    story += [NextPageTemplate("main"), PageBreak()]

    # ---------- página 2: scorecard + piso x teto
    story += [P("SCORECARD", "kicker"), P("Os cinco rankings lado a lado", "h1"), Spacer(1, 6)]
    header = ["#", "Time / dono", "Power", "Starting five", "Depth", "Teto", "Proj. temporada", "Rank médio", "Rating"]
    rows = []
    for t in order:
        cells = [str(t["overall"]), "<b>%s</b><br/><font size=6.8 color='#5B6573'>%s</font>" % (esc(t["name"]), esc(t["owner"]))]
        for k, _, _ in METRICS:
            cells.append("%s <font size=6.6 color='#8A94A3'>#%d</font>" % (fmt_metric(k, t["m"][k]), t["rank"][k]))
        cells.append(pt(t["avg_rank"], 1))
        cells.append('<font color="#%s"><b>%s</b></font>' % (RATING_COLOR[t["rating"]].hexval()[2:], t["rating"]))
        rows.append(cells)
    widths = [16, 110, 50, 52, 46, 46, 58, 36, 79]
    story.append(make_table(header, rows, widths, right_cols=(2, 3, 4, 5, 6, 7),
                            extra=[("ALIGN", (0, 0), (0, -1), "CENTER")]))
    story += [Spacer(1, 3), P("Rating pelo rank médio: os 4 primeiros são Overweight, os 4 seguintes Equal-weight e os 4 últimos Underweight. "
                              "Os números em cinza são a posição em cada ranking.", "small"), Spacer(1, 10)]
    pts = [(t["name"], t["m"]["power"], t["m"]["teto_time"]) for t in teams.values()]
    xs = [p[1] for p in pts]
    ys = [p[2] for p in pts]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    resid = {nm: y - (my + slope * (x - mx)) for nm, x, y in pts}
    up = max(resid, key=resid.get)
    dn = min(resid, key=resid.get)
    story += [P("PISO X TETO", "kicker"), P("Quem tem mais espaço acima da força atual", "h1"), Spacer(1, 4),
              Scatter(pts, CONTENT_W, 230, "POWER RANK (valor atual dos 10 melhores, FP/jogo)", "TETO (FP/jogo)"), Spacer(1, 4),
              P("A linha tracejada é a tendência da liga: times acima dela têm mais teto do que a força atual sugere. "
                "<b>%s</b> está mais acima da tendência (%s FP/jogo) e <b>%s</b> mais abaixo (%s)." % (
                    esc(up), signed(resid[up]), esc(dn), signed(resid[dn])), "body"), PageBreak()]

    # ---------- página 3: metodologia
    story += [P("METODOLOGIA", "kicker"), P("Como os números foram construídos", "h1"), Spacer(1, 6)]
    defs = [
        ("Fonte dos dados", "Elencos, lesões, draft, projeções e médias em fantasy points vêm do ESPN Fantasy da liga (scoring de pontos). "
                            "As estatísticas da NBA (2024-25, 2025-26 e pré-temporada 2026-27) identificam a turma de rookies e conferem os dados."),
        ("Valor atual", "Média de FP por jogo: 80% da média real de 2025-26 e 20% da projeção ESPN 2026-27. Rookies usam a projeção. "
                        "Jogadores OUT valem 0; day-to-day contam como disponíveis."),
        ("Power rank", "Soma dos 10 melhores valores atuais do elenco."),
        ("Starting five", "Uma vaga por posição (PG, SG, SF, PF, C). Cada jogador pode ocupar qualquer vaga para a qual é elegível no ESPN (um PF que também é C pode ser o C). A escolha é a combinação de maior soma; se faltar elegível saudável, entra o melhor disponível."),
        ("Depth", "Soma dos 8 melhores jogadores saudáveis fora do starting five."),
        ("Projeção de temporada", "Soma das projeções totais do ESPN para 2026-27, que embutem os jogos esperados de cada jogador (por isso lesionados ainda contam)."),
        ("Teto", "Projeção ESPN multiplicada pelo percentil 80 de real ÷ projeção do nível do jogador em 2025-26. O teto do time soma os 10 maiores."),
        ("Rating", "Rank médio nos cinco rankings: terço de cima Overweight, do meio Equal-weight, de baixo Underweight."),
    ]
    rows = [[Paragraph("<b>%s</b>" % esc(a), ST["cell"]), Paragraph(esc(b), ST["cell"])] for a, b in defs]
    dt = Table(rows, colWidths=[100, CONTENT_W - 100])
    dt.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                            ("LINEABOVE", (0, 0), (-1, 0), 1, NAVY)]))
    story += [dt, Spacer(1, 10), P("CALIBRAÇÃO DO TETO", "kicker"), Spacer(1, 3)]
    if ctx["tiers"]:
        rows = []
        for c in ctx["tiers"]:
            rows.append([esc(c[0]), c[1], c[2].replace(".", ","), c[4].replace(".", ","), c[6], "<b>%s</b>" % c[7].replace("*", "").replace(".", ",")])
        story.append(make_table(["Nível (ranking de projeções)", "n", "Mediana real ÷ proj.", "Percentil 80", "% que bateu a projeção", "Multiplicador"],
                                rows, [150, 34, 88, 66, 92, 63], right_cols=(1, 2, 3, 4, 5)))
        p = ctx["params"]
        rr = [r[3] for r in ctx["rookies"]]
        story += [Spacer(1, 4), P("Cortes de projeção: elite acima de %s FP/jogo, médio acima de %s. Rookies: multiplicador %s (percentil 80 da turma de 2025-26, "
                                  "%d jogadores com até 24 anos) e %s para os dois primeiros picks (percentil 90). A turma teve mediana de %s da projeção, "
                                  "de %s a %s." % (
                                      pt(p.get("edges", [0, 0])[0], 1), pt(p.get("edges", [0, 0])[1], 1), pt(p.get("rookie_default", 0), 3),
                                      p.get("n_rookies", len(rr)), pt(p.get("rookie_top", 0), 3), pt(statistics.median(rr), 2) if rr else "-",
                                      pt(min(rr), 2) if rr else "-", pt(max(rr), 2) if rr else "-"), "body")]
    story += [Spacer(1, 8), P("LIMITAÇÕES", "kicker"), Spacer(1, 3)] + bullets([
        "A projeção do ESPN foi otimista em 2025-26: a mediana de real ÷ projeção ficou abaixo de 1,0 nos três níveis. Os valores usam a projeção como ela vem.",
        "A elegibilidade vem do eligibleSlots do ESPN. G e F aparecem sempre junto de PG/SG ou SF/PF, então não criam vagas extras no starting five.",
        "A amostra de rookies para o teto é pequena e muito dispersa; o teto de estreantes é a estimativa menos firme do relatório.",
        "Lesões são um retrato de hoje (%s): os rankings de valor atual mudam com o boletim médico." % data_extenso(ctx["today"]),
    ]) + [PageBreak()]

    # ---------- páginas de ranking
    def ranking_page(key, kicker, title, intro_extra, extra_flowables, row_h=21):
        paras, order_k, mean = ranking_commentary(key, ctx)
        rows = [{"rank": i + 1, "name": t["name"], "owner": t["owner"], "value": t["m"][key]} for i, t in enumerate(order_k)]
        fl = [P(kicker, "kicker"), P(title, "h1"), Spacer(1, 4),
              P("Unidade: %s. Barras mostram o desvio em relação à média da liga." % esc(dict((k, d) for k, _, d in METRICS)[key]), "small"), Spacer(1, 4),
              DevBars(rows, CONTENT_W, mean, key, row_h=row_h), Spacer(1, 8)]
        fl += [P(x, "body") for x in paras + intro_extra]
        fl += extra_flowables
        fl.append(PageBreak())
        return fl

    # power
    extra = [Spacer(1, 8), P("OS TRÊS MAIORES VALORES DE CADA TIME", "box_h"), Spacer(1, 3)]
    rows = []
    for t in sorted(teams.values(), key=lambda t: t["m"]["power"], reverse=True):
        rows.append([esc(t["name"])] + ["%s <font color='#5B6573'>%s</font>" % (esc(short_name(p["player_name"])), pt(p["value_atual"])) for p in t["top10"][:3]])
    extra.append(make_table(["Time", "1º", "2º", "3º"], rows, [120, 124, 124, 125]))
    pw_order = sorted(teams.values(), key=lambda t: t["m"]["power"], reverse=True)
    pwv = [t["m"]["power"] for t in pw_order]
    intro = ["Do 1º ao 4º colocado há %s FP/jogo de diferença; do 4º ao 10º, %s; do 10º ao 12º, %s. Jogadores OUT valem 0 neste ranking, "
             "e os day-to-day contam como disponíveis." % (pt(pwv[0] - pwv[3]), pt(pwv[3] - pwv[9]), pt(pwv[9] - pwv[11]))]
    story += ranking_page("power", "RANKING 1 DE 5", "Power rank: a força de hoje", intro, extra)

    # projeção
    pr = sorted(teams.values(), key=lambda t: t["m"]["proj_temporada"], reverse=True)
    deltas = {t["name"]: t["rank"]["power"] - t["rank"]["proj_temporada"] for t in teams.values()}
    riser = max(deltas, key=deltas.get)
    faller = min(deltas, key=deltas.get)
    rows = []
    for t in pr:
        d = deltas[t["name"]]
        rows.append([esc(t["name"]), pt(t["m"]["proj_temporada"], 0), "%dº" % t["rank"]["proj_temporada"], "%dº" % t["rank"]["power"],
                     ("%+d" % d) if d else "0"])
    intro = ["Comparada ao power rank, a projeção de temporada sobe mais <b>%s</b> (%+d posições) e derruba mais <b>%s</b> (%+d). "
             "A projeção soma os totais dos 13 jogadores e embute os jogos esperados de cada um; por isso não zera quem hoje está fora e valoriza o elenco inteiro, não só os 10 melhores." % (
                 esc(riser), deltas[riser], esc(faller), deltas[faller])]
    extra = [Spacer(1, 8), P("PROJEÇÃO CONTRA POWER RANK", "box_h"), Spacer(1, 3),
             make_table(["Time", "Projeção (FP)", "Rank projeção", "Rank power", "Variação"], rows, [170, 80, 80, 80, 83], right_cols=(1, 2, 3, 4))]
    story += ranking_page("proj_temporada", "RANKING 2 DE 5", "Projeção de temporada: o que o ESPN espera", intro, extra)

    # starting five
    rows = []
    for t in sorted(teams.values(), key=lambda t: t["m"]["starting_five"], reverse=True):
        line = [esc(t["name"])]
        for slot in rk.SLOTS:
            pl = t["lineup"].get(slot)
            if not pl:
                line.append("-")
            else:
                p, fb = pl
                line.append("%s%s" % (esc(compact_name(p["player_name"])), "<font color='#B3412E'><b>*</b></font>" if fb else ""))
        rows.append(line)
    pc = ctx["pos_count"]
    pos_txt = ", ".join("%s %d" % (k, pc[k]) for k in rk.SLOTS)
    intro = ["Oferta de jogadores por posição na liga: %s. Cada time escolhe a melhor combinação de elegíveis; vaga sem elegível saudável recebe o melhor disponível (marcado com asterisco)." % pos_txt]
    extra = [Spacer(1, 8), P("STARTING FIVE POR TIME", "box_h"), Spacer(1, 3),
             make_table(["Time"] + rk.SLOTS, rows, [108, 77, 77, 77, 77, 77],
                        extra=[("TOPPADDING", (0, 0), (-1, -1), 2.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6)]),
             Spacer(1, 3), P("* vaga sem elegível saudável; preenchida com o melhor disponível.", "small")]
    story += ranking_page("starting_five", "RANKING 3 DE 5", "Starting five: um titular por posição", intro, extra)

    # depth
    rows = []
    for t in sorted(teams.values(), key=lambda t: t["m"]["depth"], reverse=True):
        dl = t["depth"]
        avg = (t["m"]["depth"] / len(dl)) if dl else 0
        rows.append([esc(t["name"]), "%d" % len(dl), pt(avg), ", ".join("%s %s" % (esc(short_name(p["player_name"])), pt(p["value_atual"])) for p in dl[:3])])
    worst = min(teams.values(), key=lambda t: t["m"]["depth"])
    why = []
    if worst["out"]:
        why.append("%d jogador(es) fora" % len(worst["out"]))
    if worst["nodata"]:
        why.append("%d sem dados (valor 0)" % len(worst["nodata"]))
    intro = ["O depth soma os 8 melhores saudáveis depois do starting five. Quando há menos de 8 disponíveis, a soma cai por quantidade, não só por qualidade: "
             "<b>%s</b> tem %d jogadores no banco%s." % (esc(worst["name"]), len(worst["depth"]), (" (" + join_pt(why) + ")") if why else "")]
    extra = [Spacer(1, 8), P("COMPOSIÇÃO DO BANCO", "box_h"), Spacer(1, 3),
             make_table(["Time", "Jogadores", "Valor médio", "Três melhores do banco"], rows, [118, 50, 62, 263], right_cols=(1, 2))]
    story += ranking_page("depth", "RANKING 4 DE 5", "Depth: quem aguenta lesão e calendário", intro, extra)

    # teto
    par = ctx["params"]
    e1, e2 = par.get("edges", [50, 35])

    def nivel(p):
        if p["prev_fp"] == "":
            return "Rookie"
        b = p["proj_fp"] if p["proj_fp"] != "" else p["prev_fp"]
        return "Elite" if b >= e1 else "Médio" if b >= e2 else "Baixo"

    cand = [p for p in ctx["players"] if p["teto"] != "" and p["proj_fp"] != ""]
    top_teto = sorted(cand, key=lambda p: p["teto"], reverse=True)[:8]
    top_margem = sorted(cand, key=lambda p: p["teto"] - p["proj_fp"], reverse=True)[:6]
    n_rk = sum(1 for p in top_margem if nivel(p) == "Rookie")
    mults = par.get("mults", [0, 0, 0])
    intro = ["O teto aplica à projeção o multiplicador do nível (%s para elite, %s para médio, %s para baixo; rookies %s, %s para o top-2). "
             "Quanto menor o nível, maior o espaço para superar a projeção. O teto do time soma os 10 maiores tetos individuais, o que supõe que todos "
             "tenham uma boa temporada ao mesmo tempo: é um limite superior, não uma previsão." % (
                 pt(mults[0], 3), pt(mults[1], 3), pt(mults[2], 3), pt(par.get("rookie_default", 0), 3), pt(par.get("rookie_top", 0), 3)),
             "Os maiores tetos absolutos são todos de jogadores de elite, com margem de cerca de %s%% sobre a projeção. Quem tem mais espaço para "
             "surpreender está nos níveis de baixo: os %d maiores acréscimos sobre a projeção são de jogadores de nível %s." % (pt((mults[0] - 1) * 100, 1), len(top_margem), "Baixo" if all(nivel(p) == "Baixo" for p in top_margem) else "Médio ou Baixo")]

    def teto_rows(lst, numbered):
        rr = []
        for i, p in enumerate(lst):
            cells = [esc(p["player_name"]), esc(p["team_name"]), p["position"], nivel(p), pt(p["proj_fp"]), pt(p["teto"]), signed(p["teto"] - p["proj_fp"])]
            rr.append((["%d" % (i + 1)] if numbered else []) + cells)
        return rr

    ex = [("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    extra = [Spacer(1, 6), P("8 MAIORES TETOS INDIVIDUAIS", "box_h"), Spacer(1, 3),
             make_table(["#", "Jogador", "Time", "Pos", "Nível", "Proj.", "Teto", "Margem (FP/jogo)"], teto_rows(top_teto, True),
                        [18, 120, 125, 28, 44, 38, 38, 82], right_cols=(5, 6, 7), extra=ex),
             Spacer(1, 8), P("QUEM MAIS PODE SURPREENDER: 6 MAIORES MARGENS SOBRE A PROJEÇÃO", "box_h"), Spacer(1, 3),
             make_table(["Jogador", "Time", "Pos", "Nível", "Proj.", "Teto", "Margem (FP/jogo)"], teto_rows(top_margem, False),
                        [138, 125, 28, 44, 38, 38, 82], right_cols=(4, 5, 6), extra=ex)]
    story += ranking_page("teto_time", "RANKING 5 DE 5", "Teto: o melhor cenário realista", intro, extra, row_h=20.5)

    # ---------- uma página por time (na ordem do rating)
    for t in order:
        s, w = strengths_weaknesses(t, ctx)
        pill = Pill(t["rating"], RATING_COLOR[t["rating"]])
        head = Table([[[P("TIME %d DE %d  |  %s  |  %s" % (t["overall"], n_teams, esc(t.get("conf", "")).upper(), esc(t["owner"]).upper()), "kicker"), Spacer(1, 2), P(esc(t["name"]), "team")], pill]],
                     colWidths=[CONTENT_W - 100, 100])
        head.setStyle(TableStyle([("VALIGN", (0, 0), (0, 0), "TOP"), ("VALIGN", (1, 0), (1, 0), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        kpis = []
        for k, lbl, _ in METRICS:
            d = t["m"][k] - means[k]
            kpis.append((lbl.replace("Projeção de temporada", "Proj. temporada"), fmt_metric(k, t["m"][k]),
                         "%dº de 12 | %s" % (t["rank"][k], signed(d, 0 if k == "proj_temporada" else 1))))
        half = (CONTENT_W - 12) / 2

        def col(title, color, items):
            rows_ = [[Paragraph('<font color="%s">%s</font>' % (color, title), ST["box_h"])]] + [[Paragraph(x, ST["bullet"], bulletText="•")] for x in items]
            tb = Table(rows_, colWidths=[half])
            tb.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 2, colors.HexColor(color)), ("BACKGROUND", (0, 0), (-1, -1), PALE),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                                    ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                                    ("TOPPADDING", (0, 0), (-1, 0), 6)]))
            return tb
        sw = Table([[col("PONTOS FORTES", "#1E7A5A", s), col("PONTOS FRÁGEIS", "#B3412E", w)]], colWidths=[half + 6, half + 6])
        sw.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                                ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        lu_cells = []
        for slot in rk.SLOTS:
            pl = t["lineup"].get(slot)
            if pl:
                p, fb = pl
                lu_cells.append(Paragraph("%s%s<br/><font size=7 color='#5B6573'>%s FP/jogo</font>" % (
                    esc(compact_name(p["player_name"])), "<font color='#B3412E'><b>*</b></font>" if fb else "", pt(p["value_atual"])), ST["cell"]))
            else:
                lu_cells.append(Paragraph("-", ST["cell"]))
        lu = Table([[Paragraph(sl, ST["th"]) for sl in rk.SLOTS], lu_cells], colWidths=[CONTENT_W / 5.0] * 5)
        lu.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 1, NAVY), ("LINEBELOW", (0, 1), (-1, 1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LEFTPADDING", (0, 0), (-1, -1), 3)]))
        bench = ", ".join("%s %s" % (esc(compact_name(p["player_name"])), pt(p["value_atual"])) for p in t["depth"])
        lu_fl = [P("STARTING FIVE E BANCO", "box_h"), Spacer(1, 3), lu, Spacer(1, 3),
                 P("<b>Banco (%d):</b> %s." % (len(t["depth"]), bench), "cell")]
        if t["fallback"]:
            lu_fl.append(P("* vaga sem elegível saudável; preenchida com o melhor disponível.", "small"))
        lu_fl.append(Spacer(1, 9))
        maxv = max([val(p) for p in t["players"]] + [float(p["teto"]) for p in t["players"] if p["teto"] != ""]) * 1.02
        rows = []
        for p in t["players"]:
            status = {"ACTIVE": "", "DAY_TO_DAY": "<font color='#C4733B'><b>DTD</b></font>", "OUT": "<font color='#B3412E'><b>OUT</b></font>"}.get(
                p["injury_status"], esc(p["injury_status"]))
            name = esc(p["player_name"]) + (" <font color='#5B6573'>(R)</font>" if p["prev_fp"] == "" and p["proj_fp"] != "" else "")
            rows.append([name, p["position"], status,
                         pt(val(p)) if p["value"] != "" else "-", pt(float(p["proj_fp"])) if p["proj_fp"] != "" else "-",
                         pt(p["teto"]) if p["teto"] != "" else "-",
                         PlayerBar(p["value"], p["teto"], maxv, width=140, out=not p["saudavel"])])
        rt = make_table(["Jogador", "Pos", "Status", "Valor", "Proj.", "Teto", "Valor atual e faixa até o teto"], rows,
                        [128, 28, 32, 34, 34, 34, 203], right_cols=(3, 4, 5),
                        extra=[("TOPPADDING", (0, 0), (-1, -1), 3.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2), ("LEFTPADDING", (6, 1), (6, -1), 10)])
        story += [head, Spacer(1, 8), KPIStrip(kpis, CONTENT_W), Spacer(1, 10), sw, Spacer(1, 10)] + lu_fl + [
                  P("ELENCO", "box_h"), Spacer(1, 3), rt, Spacer(1, 4),
                  P("Valor = média de FP por jogo (80%% 2025-26, 20%% projeção); (R) = rookie, valor igual à projeção. Barra azul: valor atual; faixa clara: até o teto; "
                    "tracejado: jogador fora (valor não conta). Rating %s: rank médio %s." % (t["rating"], pt(t["avg_rank"], 1)), "small"), PageBreak()]

    # ---------- aviso final
    story += [P("AVISO", "kicker"), P("Sobre este documento", "h1"), Spacer(1, 6)] + bullets([
        "Este relatório é uma brincadeira entre amigos, escrita em linguagem de research de investimentos. Ratings, tetos e comentários são "
        "resultado de fórmulas simples e não constituem recomendação de investimento de nenhum tipo.",
        "Os números vêm de projeções e estatísticas do ESPN Fantasy e da NBA, com a data de %s. Lesões, trocas e rotações mudam; o relatório "
        "pode ser gerado de novo a qualquer momento com <i>python make_report.py</i>." % data_extenso(ctx["today"]),
        "Projeções são estimativas: na temporada passada a mediana do que os jogadores renderam ficou abaixo da projeção do ESPN em todos os níveis.",
        "Os nomes de ratings (Overweight, Equal-weight, Underweight) são apenas rótulos de leitura rápida para terços do ranking.",
    ])
    return story


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / ("%s_preseason.pdf" % LEAGUE_NAME.replace(" ", "_"))
    out.parent.mkdir(parents=True, exist_ok=True)
    ctx = build()
    chrome, cover = chrome_factory(ctx)
    doc = BaseDocTemplate(str(out), pagesize=A4, title="%s - Preseason %s" % (LEAGUE_NAME, SEASON_LABEL),
                          author="Fantasy NBA Research - %s" % LEAGUE_NAME, subject="Rankings e análise por time",
                          leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=26 * mm, bottomMargin=22 * mm)
    top_cover = H_PAGE - 40 * mm - 8 * mm
    bottom = 22 * mm
    main_w, gap, side_w = 330, 18, CONTENT_W - 330 - 18
    cover_main = Frame(MARGIN_X, bottom, main_w, top_cover - bottom, id="cm", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    cover_side = Frame(MARGIN_X + main_w + gap, bottom, side_w, top_cover - bottom, id="cs", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    main_frame = Frame(MARGIN_X, bottom, CONTENT_W, H_PAGE - 26 * mm - bottom, id="m", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="cover", frames=[cover_main, cover_side], onPage=cover),
                          PageTemplate(id="main", frames=[main_frame], onPage=chrome)])
    doc.build(build_story(ctx))
    print("PDF gerado:", out)


if __name__ == "__main__":
    main()
