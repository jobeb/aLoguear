"""Genera el icono/logo de la app (candado sobre fondo redondeado) en icon.ico
y un PNG para usar dentro de la propia GUI. Se ejecuta una sola vez; el
resultado se versiona junto al resto de la app."""
from PIL import Image, ImageDraw

ACCENT = (13, 148, 136, 255)       # #0d9488
ACCENT_DARK = (15, 118, 110, 255)  # #0f766e
WHITE = (255, 255, 255, 255)

SIZE = 256


def build_icon() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fondo cuadrado redondeado con un ligero degradado diagonal.
    radius = 56
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=radius, fill=255)
    bg = Image.new("RGBA", (SIZE, SIZE), ACCENT)
    grad = Image.new("L", (SIZE, SIZE), 0)
    grad_draw = ImageDraw.Draw(grad)
    for y in range(SIZE):
        shade = int(255 * (y / SIZE))
        grad_draw.line([(0, y), (SIZE, y)], fill=shade)
    dark_layer = Image.new("RGBA", (SIZE, SIZE), ACCENT_DARK)
    bg = Image.composite(dark_layer, bg, grad)
    img.paste(bg, (0, 0), mask)

    # Candado: grillete (arco grueso) + cuerpo (rectángulo redondeado).
    draw = ImageDraw.Draw(img)
    shackle_box = [76, 56, 180, 160]
    draw.arc(shackle_box, start=180, end=360, fill=WHITE, width=22)

    body_box = [66, 126, 190, 210]
    draw.rounded_rectangle(body_box, radius=20, fill=WHITE)

    # Ojo de la cerradura (recorte en el color de acento sobre el cuerpo blanco).
    cx, cy = 128, 155
    draw.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], fill=ACCENT)
    draw.polygon(
        [(cx - 7, cy + 6), (cx + 7, cy + 6), (cx + 4, cy + 26), (cx - 4, cy + 26)],
        fill=ACCENT,
    )

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
