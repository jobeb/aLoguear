"""Genera el icono/logo de la app (candado sobre fondo redondeado) en icon.ico
y un PNG para usar dentro de la propia GUI. Se ejecuta una sola vez; el
resultado se versiona junto al resto de la app."""
from PIL import Image, ImageDraw

ACCENT = (13, 148, 136, 255)       # #0d9488
ACCENT_DARK = (15, 118, 110, 255)  # #0f766e
ACCENT_DEEP = (11, 92, 86, 255)    # #0b5c56 (borde/sombra)
WHITE = (255, 255, 255, 255)
HIGHLIGHT = (255, 255, 255, 70)

# Se dibuja en grande (512) y se reduce con LANCZOS: bordes más nítidos en
# todos los tamaños (barra de tareas, título, bandeja).
SIZE = 512


def build_icon() -> Image.Image:
    s = SIZE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # Fondo cuadrado redondeado con degradado diagonal (claro arriba-izq).
    radius = int(s * 0.22)
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=255)
    bg = Image.new("RGBA", (s, s), ACCENT)
    grad = Image.new("L", (s, s), 0)
    grad_draw = ImageDraw.Draw(grad)
    for y in range(s):
        shade = int(255 * (y / s))
        grad_draw.line([(0, y), (s, y)], fill=shade)
    dark_layer = Image.new("RGBA", (s, s), ACCENT_DARK)
    bg = Image.composite(dark_layer, bg, grad)
    # Brillo superior sutil.
    shine = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(shine).rounded_rectangle(
        [int(s * 0.08), int(s * 0.05), int(s * 0.92), int(s * 0.38)],
        radius=radius // 2, fill=HIGHLIGHT,
    )
    bg = Image.alpha_composite(bg, shine)
    # Borde fino para recortar nítido sobre fondos claros/oscuros.
    border = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle(
        [0, 0, s - 1, s - 1], radius=radius, outline=ACCENT_DEEP, width=max(2, s // 128)
    )
    img.paste(bg, (0, 0), mask)

    draw = ImageDraw.Draw(img)

    # Candado: grillete (arco grueso) + cuerpo (rectángulo redondeado).
    shackle_box = [s * 0.297, s * 0.219, s * 0.703, s * 0.625]
    draw.arc(shackle_box, start=180, end=360, fill=WHITE, width=int(s * 0.086))

    body_box = [s * 0.258, s * 0.492, s * 0.742, s * 0.82]
    draw.rounded_rectangle(body_box, radius=int(s * 0.078), fill=WHITE)
    # Sombra inferior del cuerpo para darle relieve.
    draw.rounded_rectangle(
        [s * 0.258, s * 0.492, s * 0.742, s * 0.82],
        radius=int(s * 0.078), outline=ACCENT_DEEP, width=max(2, s // 170),
    )

    # Ojo de la cerradura (en color de acento sobre el cuerpo blanco).
    cx, cy = s / 2, s * 0.605
    r = s * 0.047
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT)
    draw.polygon(
        [
            (cx - s * 0.027, cy + s * 0.023),
            (cx + s * 0.027, cy + s * 0.023),
            (cx + s * 0.016, cy + s * 0.102),
            (cx - s * 0.016, cy + s * 0.102),
        ],
        fill=ACCENT,
    )

    # OJO: no usar paste() con máscara aquí: sobrescribiría (incluido el alfa)
    # todo lo ya dibujado con los píxeles transparentes de `border`.
    img = Image.alpha_composite(img, border)
    return img


def main() -> None:
    icon = build_icon()
    icon.save(
        "assets/icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    icon.save("assets/icon.png")
    icon.resize((48, 48), Image.LANCZOS).save("assets/icon_48.png")
    print("Iconos generados en assets/")


if __name__ == "__main__":
    main()
