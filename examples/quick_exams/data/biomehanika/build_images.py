"""Draws the diagrams of the Biomehanika question bank into ./images (needs matplotlib)."""

import sys
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, FancyArrowPatch, Rectangle, Circle
from pathlib import Path

OUT = (
    sys.argv[1]
    if len(sys.argv) > 1
    else str(Path(__file__).resolve().parent / "images")
)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12})


def save(fig, name):
    fig.savefig(f"{OUT}/{name}.png", dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def arrow(ax, x, y, dx, dy, color, label=None, lx=0, ly=0):
    ax.add_patch(
        FancyArrowPatch(
            (x, y),
            (x + dx, y + dy),
            arrowstyle="-|>",
            mutation_scale=18,
            lw=2.5,
            color=color,
        )
    )
    if label:
        ax.text(
            x + dx + lx,
            y + dy + ly,
            label,
            color=color,
            ha="center",
            fontsize=13,
            fontweight="bold",
        )


# 1) Lever – 3rd class (effort between fulcrum and load)
fig, ax = plt.subplots(figsize=(7, 3))
ax.set_xlim(-0.5, 10.5)
ax.set_ylim(-1.6, 2.6)
ax.axis("off")
ax.add_patch(Rectangle((0, 0), 10, 0.25, color="#8d6e63"))
ax.add_patch(Polygon([[0, 0], [-0.45, -0.9], [0.45, -0.9]], color="#455a64"))
ax.text(0, -1.4, "vrtišče", ha="center")
arrow(ax, 2.5, 0.25, 0, 1.8, "#c62828", "F (mišica)", 0, 0.15)
arrow(ax, 9.5, 2.1, 0, -1.8, "#1565c0", "breme", 0, 0.65)
ax.add_patch(Rectangle((9.0, 0.25), 1.0, 0.0, color="#1565c0"))
save(fig, "vzvod")

# 3) Stress-strain curve (humerus)
fig, ax = plt.subplots(figsize=(6.5, 4.2))
e1 = np.linspace(0, 0.5, 50)
s1 = 170 * e1
e2 = np.linspace(0.5, 1.4, 80)
s2 = 85 + 35 * (1 - np.exp(-(e2 - 0.5) / 0.35)) / (1 - np.exp(-0.9 / 0.35))
ax.plot(e1, s1, color="#1565c0", lw=2.5)
ax.plot(e2, s2, color="#c62828", lw=2.5)
ax.plot(1.4, s2[-1], "kx", ms=12, mew=3)
ax.text(1.32, s2[-1] + 6, "zlom", ha="center")
ax.set_xlabel("relativni raztezek ε (%)")
ax.set_ylabel("napetost σ (MPa)")
ax.set_xlim(0, 1.6)
ax.set_ylim(0, 140)
ax.set_xticks(np.arange(0, 1.61, 0.2))
ax.set_yticks(range(0, 141, 20))
ax.grid(alpha=0.35)
ax.set_title("Nadlahtnica: napetost v odvisnosti od raztezka")
save(fig, "napetost_raztezek")

# 4) Boxer punch force-time
fig, ax = plt.subplots(figsize=(6.5, 3.8))
t = np.array([0, 0.05, 0.1])
F = np.array([0, 1600, 0])
ax.fill_between(t, F, color="#ef9a9a", alpha=0.6)
ax.plot(t, F, color="#c62828", lw=2.5)
ax.set_xlabel("čas t (s)")
ax.set_ylabel("sila F (N)")
ax.set_xlim(-0.01, 0.12)
ax.set_ylim(0, 1800)
ax.set_yticks([0, 400, 800, 1200, 1600])
ax.set_xticks([0, 0.025, 0.05, 0.075, 0.1])
ax.grid(alpha=0.35)
ax.set_title("Sila udarca v boksarsko vrečo")
save(fig, "udarec_sila_cas")

# 5) Centre-of-mass height during walking
fig, ax = plt.subplots(figsize=(7, 3.6))
t = np.linspace(0, 3, 600)
z = 100 - 2.5 * np.cos(2 * np.pi * t / 0.5)
ax.plot(t, z, color="#2e7d32", lw=2.5)
ax.set_xlabel("čas t (s)")
ax.set_ylabel("višina težišča z (cm)")
ax.set_ylim(96, 104)
ax.set_xticks(np.arange(0, 3.01, 0.25))
ax.grid(alpha=0.35)
ax.set_title("Vertikalno gibanje težišča med hojo")
save(fig, "tezisce_hoja")

# 7) Force–velocity and power
fig, ax = plt.subplots(figsize=(6.5, 4))
v = np.linspace(0, 1, 200)
F = (1 - v) / (1 + 3 * v)
P = F * v
ax.plot(v, F, color="#1565c0", lw=2.5, label="sila F")
ax2 = ax.twinx()
ax2.plot(v, P / P.max(), color="#c62828", lw=2.5, ls="--", label="moč P")
ax.set_xlabel("hitrost krčenja (delež $v_{max}$)")
ax.set_ylabel("sila (delež $F_{max}$)", color="#1565c0")
ax2.set_ylabel("moč (delež $P_{max}$)", color="#c62828")
ax.set_ylim(0, 1.05)
ax2.set_ylim(0, 1.05)
ax.grid(alpha=0.35)
for lab, x in [("A", 0.05), ("B", 0.33), ("C", 0.9)]:
    ax.axvline(x, color="gray", ls=":")
    ax.text(
        x, 1.07, lab, ha="center", fontweight="bold", transform=ax.get_xaxis_transform()
    )
fig.legend(loc="upper right", bbox_to_anchor=(0.86, 0.86))
save(fig, "sila_hitrost_moc")

# 8) Amplitude spectrum
fig, ax = plt.subplots(figsize=(6.5, 3.6))
fs = 100
t = np.arange(0, 40, 1 / fs)
x = np.sin(2 * np.pi * t) + np.sin(10 * np.pi * t) + np.sin(0.5 * np.pi * t)
X = np.abs(np.fft.rfft(x)) * 2 / len(x)
f = np.fft.rfftfreq(len(x), 1 / fs)
ax.plot(f, X, color="#4527a0", lw=2)
ax.set_xlim(0, 7)
ax.set_ylim(0, 1.2)
ax.set_xlabel("frekvenca f (Hz)")
ax.set_ylabel("amplituda")
ax.grid(alpha=0.35)
ax.set_xticks(np.arange(0, 7.1, 0.5))
ax.set_title("Frekvenčni (Fourierjev) spekter signala")
save(fig, "spekter")


def arr(ax, a, b, color, lw=2.5, style="-|>"):
    ax.add_patch(
        FancyArrowPatch(
            a,
            b,
            arrowstyle=style,
            mutation_scale=22,
            lw=lw,
            color=color,
            shrinkA=0,
            shrinkB=0,
            zorder=10,
        )
    )


def dim(ax, x1, x2, y, text):
    arr(ax, (x1, y), (x2, y), "gray", 1.2, "<->")
    ax.plot([x1, x1], [y - 0.6, 0], color="gray", ls=":", lw=1)
    ax.plot([x2, x2], [y - 0.6 if y > 0 else y + 0.6, 0], color="gray", ls=":", lw=1)
    ax.text(
        (x1 + x2) / 2, y + (0.5 if y > 0 else -1.4), text, ha="center", color="dimgray"
    )


# Forearm + biceps
fig, ax = plt.subplots(figsize=(8.5, 4.2))
ax.set_xlim(-3, 42)
ax.set_ylim(-13, 16)
ax.axis("off")
ax.set_aspect("equal")
ax.add_patch(Rectangle((0, -1), 34, 2, color="#ffcc80", ec="#e65100", zorder=2))
ax.add_patch(Circle((0, 0), 1.6, color="#455a64", zorder=3))
ax.text(-1.5, 2.3, "komolec", ha="center")
arr(ax, (4, 1), (4, 11), "#c62828")
ax.text(5, 9.5, "$F_m$ (biceps)", color="#c62828", fontsize=13, fontweight="bold")
arr(ax, (15, -1), (15, -6), "#6a1b9a")
ax.text(16, -5.5, "$m_p g$", color="#6a1b9a", fontsize=13)
ax.add_patch(Rectangle((32.5, -3), 5, 6, color="#37474f", zorder=3))
ax.text(35, 3.8, "5 kg", ha="center")
arr(ax, (35, -3), (35, -7.5), "#1565c0")
ax.text(36, -7, "$m_u g$", color="#1565c0", fontsize=13)
dim(ax, 0, 4, 13.5, "4 cm")
dim(ax, 0, 15, -9.0, "15 cm")
dim(ax, 0, 35, -11.5, "35 cm")
save(fig, "podlaket_biceps")

# Pennate muscle
fig, ax = plt.subplots(figsize=(7, 3.4))
ax.set_xlim(-0.5, 11.5)
ax.set_ylim(-1.6, 4.0)
ax.axis("off")
ax.set_aspect("equal")
ax.plot([0, 10], [0, 0], color="#6d4c41", lw=7, solid_capstyle="round")
ax.text(10.3, 0, "kita", va="center")
ang = np.radians(60)
L = 3.0
for x0 in [0.8, 2.2, 3.6, 5.0]:
    ax.plot(
        [x0, x0 + L * np.cos(ang)],
        [0, L * np.sin(ang)],
        color="#ef9a9a",
        lw=5,
        solid_capstyle="round",
    )
x0 = 6.4
ax.plot(
    [x0, x0 + L * np.cos(ang)],
    [0, L * np.sin(ang)],
    color="#ef9a9a",
    lw=5,
    solid_capstyle="round",
)
arr(ax, (x0, 0), (x0 + 1.25 * L * np.cos(ang), 1.25 * L * np.sin(ang)), "#c62828", 3.5)
ax.text(
    x0 + 2.0,
    3.3,
    "$F_f$ (mišična vlakna)",
    color="#c62828",
    fontsize=13,
    fontweight="bold",
)
arr(ax, (x0, 0), (x0 + 1.25 * L * np.cos(ang), 0), "#1565c0", 3.5)
ax.text(
    x0 + 0.7,
    -1.2,
    "$F_t$ (kita)",
    color="#1565c0",
    fontsize=13,
    fontweight="bold",
    ha="center",
)
th = np.linspace(0, ang, 30)
ax.plot(x0 + 0.7 * np.cos(th), 0.7 * np.sin(th), color="k")
ax.text(x0 + 0.85, 0.3, "60°")
save(fig, "pernata_misica")

# Vertical jump – head height
g = 9.81
t = np.linspace(0, 3, 3000)
h = np.full_like(t, 1.75)
for i, ti in enumerate(t):
    if 1.0 <= ti < 1.5:
        h[i] = 1.75 - 0.30 * (1 - np.cos(np.pi * (ti - 1.0) / 0.5)) / 2
    elif 1.5 <= ti < 1.8:
        h[i] = 1.45 + 0.30 * (1 - np.cos(np.pi * (ti - 1.5) / 0.3)) / 2
    elif 1.8 <= ti < 2.3:
        tt = ti - 1.8
        h[i] = 1.75 + 2.4525 * tt - 0.5 * g * tt**2
    elif 2.3 <= ti < 2.7:
        h[i] = 1.75 - 0.15 * np.sin(np.pi * (ti - 2.3) / 0.4)
fig, ax = plt.subplots(figsize=(7, 3.8))
ax.plot(t, h, color="#00695c", lw=2.5)
ax.set_xlabel("čas t (s)")
ax.set_ylabel("višina glave nad tlemi (m)")
ax.set_xticks(np.arange(0, 3.01, 0.25))
ax.set_ylim(1.35, 2.15)
ax.grid(alpha=0.35)
ax.set_title("Navpični skok – meritev višine glave")
save(fig, "navpicni_skok")
print("Images written to", OUT)
