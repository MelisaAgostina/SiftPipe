"""Render the README architecture diagrams as PNGs (English + Spanish).

Every box and arrow is placed by hand on a 120 x 96 grid, so the output shape is
fixed (5:4) and identical on every machine. Only matplotlib is needed.

    python scripts/make_diagrams.py                 # -> docs/diagrams/*.png
    python scripts/make_diagrams.py --out some/dir --dpi 300
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

plt.rcParams["font.family"] = ["Segoe UI", "DejaVu Sans"]

W, H = 120, 96
INK, MUTED, BG = "#1f2933", "#52606d", "#ffffff"

# (fill, edge) pairs; the colour tells the reader what kind of step a box is.
PLAIN = ("#ffffff", "#3e4c59")
LLM = ("#d6f0ee", "#0b6e6e")
AUTO = ("#e0ecfa", "#2f5f9e")
HUMAN = ("#fdf0d5", "#b7791f")
EXTERN = ("#ece6f7", "#6b4fa3")
DATA = ("#eef1f4", "#7b8794")
ZONE_EC2 = "#f4f8fb"
ZONE_TARGET = "#fdf7e8"

TEXT = {
    "en": {
        "topo_title": "SiftPipe: runtime topology",
        "flow_title": "SiftPipe: pipeline data flow",
        "browser": ("Browser", ""),
        "dash": ("React dashboard", "Cloudflare, TanStack Start"),
        "ssm": ("AWS SSM", "Parameter Store"),
        "gha": ("GitHub Actions", "manual deploy"),
        "ec2": "AWS EC2 · Docker Compose",
        "caddy": ("Caddy", "auto-HTTPS :443"),
        "api": ("siftpipe-api", "FastAPI + pipeline blocks"),
        "sidecar": ("sidecar", "Docker control service"),
        "targets": "Targets under test",
        "mm": ("Mattermost + Postgres", ""),
        "naviq": ("NaViQ", ""),
        "sqlite": ("SQLite", "run history"),
        "results": ("results/ + evidence/", "files on disk"),
        "claude": ("Anthropic Claude API", ""),
        "l_https": "HTTPS, session cookie\n+ CSRF header",
        "l_proxy": "reverse proxy\n:8000",
        "l_sidecar": "reset / start /\nstop requests",
        "l_sock": "docker.sock:\nfresh reset",
        "l_pw": "Playwright crawl\n+ attacks",
        "l_llm": "static analysis,\npayloads, results,\ncorrelation",
        "l_writes": "writes",
        "l_oidc": "OIDC + SSM\nRun Command",
        "l_secrets": "secrets at deploy",
        "src": ("Target source", "mattermost-src, naviq-src"),
        "b1": ("B1 Environment prep", "fresh reset + seed"),
        "b3": ("B3 Static analysis", "LLM, OWASP/CWE tags"),
        "b4": ("B4 Dynamic discovery", "Playwright BFS crawl"),
        "b5": ("B5 Payload generation", "LLM"),
        "b6": ("B6 Human review", "approve / filter"),
        "b7": ("B7 Attack execution", "Playwright"),
        "ev": ("Screenshots + video", ""),
        "b8": ("B8 Results analysis", "confirmed / possible / discarded"),
        "b9": ("B9 Correlation + scoring", "CWE, LLM judge, OWASP, text"),
        "b10": ("B10 PDF report", "bilingual, grouped by CWE"),
        "hist": ("Run history", "SQLite"),
        "f_static": "static findings",
        "f_forms": "forms + inputs",
        "f_cand": "candidate\npayloads",
        "f_valid": "validated\npayloads",
        "f_att": "attempts +\nresponses",
        "f_class": "classified\nattempts",
        "f_scored": "scored\nfindings",
        "lg_llm": "LLM step",
        "lg_auto": "Browser automation",
        "lg_human": "Human step",
        "lg_data": "Environment / output",
    },
    "es": {
        "topo_title": "SiftPipe: topología en ejecución",
        "flow_title": "SiftPipe: flujo de datos del pipeline",
        "browser": ("Navegador", ""),
        "dash": ("Dashboard React", "Cloudflare, TanStack Start"),
        "ssm": ("AWS SSM", "Parameter Store"),
        "gha": ("GitHub Actions", "despliegue manual"),
        "ec2": "AWS EC2 · Docker Compose",
        "caddy": ("Caddy", "HTTPS automático :443"),
        "api": ("siftpipe-api", "FastAPI + bloques del pipeline"),
        "sidecar": ("sidecar", "Servicio de control de Docker"),
        "targets": "Objetivos bajo prueba",
        "mm": ("Mattermost + Postgres", ""),
        "naviq": ("NaViQ", ""),
        "sqlite": ("SQLite", "historial de ejecuciones"),
        "results": ("results/ + evidence/", "archivos en disco"),
        "claude": ("API de Anthropic Claude", ""),
        "l_https": "HTTPS, cookie de sesión\n+ cabecera CSRF",
        "l_proxy": "proxy inverso\n:8000",
        "l_sidecar": "pedidos de reset /\ninicio / parada",
        "l_sock": "docker.sock:\nreinicio limpio",
        "l_pw": "Rastreo con Playwright\n+ ataques",
        "l_llm": "análisis estático,\npayloads, resultados,\ncorrelación",
        "l_writes": "escribe",
        "l_oidc": "OIDC + SSM\nRun Command",
        "l_secrets": "secretos al desplegar",
        "src": ("Código del objetivo", "mattermost-src, naviq-src"),
        "b1": ("B1 Preparación del entorno", "reinicio limpio + seed"),
        "b3": ("B3 Análisis estático", "LLM, etiquetas OWASP/CWE"),
        "b4": ("B4 Descubrimiento dinámico", "rastreo BFS con Playwright"),
        "b5": ("B5 Generación de payloads", "LLM"),
        "b6": ("B6 Revisión humana", "aprobar / filtrar"),
        "b7": ("B7 Ejecución de ataques", "Playwright"),
        "ev": ("Capturas + video", ""),
        "b8": ("B8 Análisis de resultados", "confirmado / posible / descartado"),
        "b9": ("B9 Correlación + puntaje", "CWE, juez LLM, OWASP, texto"),
        "b10": ("B10 Informe PDF", "bilingüe, agrupado por CWE"),
        "hist": ("Historial de ejecuciones", "SQLite"),
        "f_static": "hallazgos estáticos",
        "f_forms": "formularios + campos",
        "f_cand": "payloads\ncandidatos",
        "f_valid": "payloads\nvalidados",
        "f_att": "intentos +\nrespuestas",
        "f_class": "intentos\nclasificados",
        "f_scored": "hallazgos\npuntuados",
        "lg_llm": "Paso con LLM",
        "lg_auto": "Automatización del navegador",
        "lg_human": "Paso humano",
        "lg_data": "Entorno / salida",
    },
}


def box(ax, x, y, w, h, text, colors=PLAIN, dashed=False, title_size=8.6, sub_size=7.2):
    """Draw a rounded box at lower-left (x, y); `text` is (title, subtitle)."""
    fill, edge = colors
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0,rounding_size=1.2",
            fc=fill, ec=edge, lw=1.3, ls="--" if dashed else "-", zorder=3,
        )
    )
    title, sub = text
    cx, cy = x + w / 2, y + h / 2
    if sub:
        ax.text(cx, cy + h * 0.17, title, ha="center", va="center", fontsize=title_size,
                fontweight="bold", color=INK, zorder=4)
        ax.text(cx, cy - h * 0.2, sub, ha="center", va="center", fontsize=sub_size,
                color=MUTED, zorder=4, linespacing=1.15)
    else:
        ax.text(cx, cy, title, ha="center", va="center", fontsize=title_size,
                fontweight="bold", color=INK, zorder=4)


def zone(ax, x, y, w, h, label, fill, edge, label_dy=-2.6):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0,rounding_size=1.5",
            fc=fill, ec=edge, lw=1.2, ls="--", zorder=1,
        )
    )
    ax.text(x + 2, y + h + label_dy, label, ha="left", va="center", fontsize=8,
            fontweight="bold", color=edge, zorder=2)


def arrow(ax, pts, dashed=False, color="#3e4c59"):
    """Orthogonal polyline; the arrowhead sits on the last point."""
    xs, ys = zip(*pts[:-1])
    ax.plot(xs, ys, color=color, lw=1.4, ls="--" if dashed else "-", zorder=2,
            solid_capstyle="butt")
    ax.annotate(
        "", xy=pts[-1], xytext=pts[-2], zorder=2,
        arrowprops=dict(arrowstyle="-|>", color=color, lw=1.4, shrinkA=0, shrinkB=0,
                        mutation_scale=11, ls="-"),
    )
    # plot() above stops one point short of the last segment's end; draw its shaft too
    ax.plot([pts[-2][0], pts[-1][0]], [pts[-2][1], pts[-1][1]], color=color, lw=1.4,
            ls="--" if dashed else "-", zorder=2, solid_capstyle="butt")


def label(ax, x, y, text, ha="center", va="center", bg=BG, size=7.2):
    ax.text(x, y, text, ha=ha, va=va, fontsize=size, color=INK, zorder=5, linespacing=1.15,
            bbox=dict(fc=bg, ec="none", pad=1.0) if bg else None)


def new_canvas(title):
    fig, ax = plt.subplots(figsize=(12, 9.6))
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")
    fig.patch.set_facecolor(BG)
    fig.subplots_adjust(0.01, 0.01, 0.99, 0.99)
    ax.text(W / 2, 93.6, title, ha="center", va="center", fontsize=14, fontweight="bold",
            color=INK)
    return fig, ax


def topology(t):
    fig, ax = new_canvas(t["topo_title"])

    # outside the server: client, deploy tooling, external API
    box(ax, 4, 78, 22, 8, t["browser"])
    box(ax, 36, 78, 28, 8, t["dash"], AUTO)
    box(ax, 76, 78, 20, 8, t["ssm"], DATA)
    box(ax, 100, 78, 18, 8, t["gha"], DATA)
    box(ax, 36, 2, 28, 7, t["claude"], EXTERN)

    # the EC2 host
    zone(ax, 2, 12, 116, 56, t["ec2"], ZONE_EC2, "#5d7c9b", label_dy=-53.4)
    box(ax, 6, 52, 18, 9, t["caddy"])
    box(ax, 42, 42, 30, 16, t["api"], LLM, title_size=9.6, sub_size=7.6)
    box(ax, 88, 52, 26, 9, t["sidecar"])
    box(ax, 6, 36, 22, 8, t["sqlite"], DATA)
    box(ax, 6, 22, 22, 8, t["results"], DATA)
    zone(ax, 78, 14, 36, 26, t["targets"], ZONE_TARGET, "#b7791f")
    box(ax, 82, 26, 28, 8, t["mm"], HUMAN)
    box(ax, 82, 17, 28, 7, t["naviq"], HUMAN)

    # request path
    arrow(ax, [(26, 82), (36, 82)])
    arrow(ax, [(50, 78), (50, 73), (15, 73), (15, 61)])
    label(ax, 32, 73, t["l_https"])
    arrow(ax, [(24, 56.5), (42, 56.5)])
    label(ax, 33, 56.5, t["l_proxy"], bg=ZONE_EC2)

    # control + attack paths
    arrow(ax, [(72, 56.5), (88, 56.5)])
    label(ax, 80, 57.8, t["l_sidecar"], va="bottom", bg=None)
    arrow(ax, [(101, 52), (101, 40)])
    label(ax, 102.4, 46, t["l_sock"], ha="left", bg=None)
    arrow(ax, [(64, 42), (64, 27), (78, 27)])
    label(ax, 71, 29.6, t["l_pw"], bg=None, va="bottom")

    # storage and Claude
    arrow(ax, [(42, 46), (35, 46), (35, 40), (28, 40)])
    arrow(ax, [(35, 46), (35, 26), (28, 26)])
    label(ax, 36.5, 33, t["l_writes"], ha="left", bg=None)
    arrow(ax, [(50, 42), (50, 9)])
    label(ax, 51.5, 26, t["l_llm"], ha="left", bg=None)

    # deploy path
    arrow(ax, [(109, 78), (109, 68)])
    label(ax, 107.4, 73, t["l_oidc"], ha="right", bg=None)
    arrow(ax, [(86, 78), (86, 64), (57, 64), (57, 58)], dashed=True, color="#6b4fa3")
    label(ax, 71.5, 64, t["l_secrets"], bg=ZONE_EC2)
    return fig


def flow(t):
    fig, ax = new_canvas(t["flow_title"])
    C1, C2, C3 = 16, 60, 104          # column centres
    R1, R2, R3, R4, R5 = 83, 68, 53, 38, 22  # row centres
    BW, BH = 28, 10

    def node(cx, cy, key, colors=PLAIN, dashed=False, h=BH):
        box(ax, cx - BW / 2, cy - h / 2, BW, h, t[key], colors, dashed)

    node(C1, R1, "src", DATA, dashed=True)
    node(C2, R1, "b1", DATA)
    node(C1, R2, "b3", LLM)
    node(C2, R2, "b4", AUTO)
    node(C2, R3, "b5", LLM)
    node(C2, R4, "b6", HUMAN)
    node(C3, R4, "b7", AUTO)
    node(C3, R3, "ev", DATA, dashed=True, h=8)
    node(C3, R5, "b8", LLM)
    node(C2, R5, "b9", LLM)
    node(C1, R5, "b10", DATA)
    node(C2, 8, "hist", DATA, dashed=True, h=8)

    top = BH / 2  # half box height
    arrow(ax, [(12, R1 - top), (12, R2 + top)])                        # source -> B3
    mid = (R1 - top + R2 + top) / 2
    arrow(ax, [(50, R1 - top), (50, mid), (28, mid), (28, R2 + top)])  # B1 -> B3
    arrow(ax, [(66, R1 - top), (66, R2 + top)])                        # B1 -> B4
    arrow(ax, [(20, R2 - top), (20, R3), (C2 - BW / 2, R3)])           # B3 -> B5
    label(ax, 30, R3 + 1.8, t["f_static"], bg=None, va="bottom")
    arrow(ax, [(C2, R2 - top), (C2, R3 + top)])                        # B4 -> B5
    label(ax, C2 + 1.5, (R2 - top + R3 + top) / 2, t["f_forms"], ha="left")
    arrow(ax, [(C2, R3 - top), (C2, R4 + top)])                        # B5 -> B6
    label(ax, C2 + 1.5, (R3 - top + R4 + top) / 2, t["f_cand"], ha="left")
    arrow(ax, [(C2 + BW / 2, R4), (C3 - BW / 2, R4)])                  # B6 -> B7
    label(ax, (C2 + C3) / 2, R4 + 1.4, t["f_valid"], va="bottom", bg=None)
    arrow(ax, [(C3, R4 + top), (C3, R3 - 4)])                          # B7 -> evidence
    arrow(ax, [(C3, R4 - top), (C3, R5 + top)])                        # B7 -> B8
    label(ax, C3 + 1.5, (R4 - top + R5 + top) / 2, t["f_att"], ha="left")
    arrow(ax, [(C3 - BW / 2, R5), (C2 + BW / 2, R5)])                  # B8 -> B9
    label(ax, (C2 + C3) / 2, R5 + 1.4, t["f_class"], va="bottom", bg=None)
    lane = (R4 - top + R5 + top) / 2
    arrow(ax, [(8, R2 - top), (8, lane), (52, lane), (52, R5 + top)])   # B3 -> B9 (static)
    label(ax, 9.5, 40, t["f_static"], ha="left")
    arrow(ax, [(C2 - BW / 2, R5), (C1 + BW / 2, R5)])                  # B9 -> B10
    label(ax, (C1 + C2) / 2, R5 + 1.4, t["f_scored"], va="bottom", bg=None)
    arrow(ax, [(C2, R5 - top), (C2, 12)])                              # B9 -> history

    # legend
    items = [(LLM, "lg_llm", False), (AUTO, "lg_auto", False),
             (HUMAN, "lg_human", False), (DATA, "lg_data", False)]
    for i, (colors, key, _) in enumerate(items):
        x = 79 if i < 2 else 102
        y = 11 - (i % 2) * 5.5
        ax.add_patch(FancyBboxPatch((x, y - 1.3), 3.4, 2.6, boxstyle="round,pad=0,rounding_size=0.5",
                                    fc=colors[0], ec=colors[1], lw=1.1, zorder=3))
        ax.text(x + 4.6, y, t[key], ha="left", va="center", fontsize=7.4, color=INK)
    return fig


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "docs" / "diagrams")
    parser.add_argument("--dpi", type=int, default=200)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    for lang, strings in TEXT.items():
        for name, build in (("runtime-topology", topology), ("pipeline-data-flow", flow)):
            fig = build(strings)
            path = args.out / f"{name}_{lang}.png"
            fig.savefig(path, dpi=args.dpi, facecolor=BG)
            plt.close(fig)
            print(path)


if __name__ == "__main__":
    main()
