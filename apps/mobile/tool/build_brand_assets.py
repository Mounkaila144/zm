#!/usr/bin/env python3
"""Fabrique les images de marque livrées dans l'APK, depuis les sources lourdes.

Les fichiers d'origine (`brand-source/`) pèsent ~4 Mo à eux deux : les embarquer
tels quels doublerait la taille de l'application pour un public dont le forfait
data est compté. Ce script en tire les seules variantes réellement affichées,
en WebP, à la taille d'affichage réelle — de ~4 Mo à quelques dizaines de Ko.

Deux traitements méritent une explication :

- **Détourage du fond.** `logo.png` est rendu sur un fond gris avec un halo
  lumineux ; `icone.png` sur du blanc. Le halo est *basse fréquence*, le logo
  est net : c'est le détail local, pas la couleur, qui les sépare. On érode
  ensuite le masque de quelques pixels, sinon le bord garde la teinte du fond
  et dessine un liseré gris sur l'AppBar sombre.
- **Icône de lanceur.** Android compose l'icône adaptative lui-même (masque
  rond, carré, squircle selon le lanceur). On livre donc un fond plein et un
  avant-plan détouré cadré dans la zone sûre, plus des PNG héritées pour les
  anciens lanceurs.

Usage : python3 tool/build_brand_assets.py
"""

from __future__ import annotations

import pathlib
import sys

try:
    import numpy as np
    from PIL import Image, ImageFilter
    from scipy import ndimage
except ImportError as exc:  # pragma: no cover - outil de préparation
    sys.exit(f"dépendance manquante ({exc}) : pip install pillow numpy scipy")

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "brand-source"
ASSETS = ROOT / "assets" / "brand"
RES = ROOT / "android" / "app" / "src" / "main" / "res"

# Fond de l'icône adaptative — le bleu nuit du logo, pas un noir approché.
NAVY = (7, 26, 68)

# Densités Android : mdpi, hdpi, xhdpi, xxhdpi, xxxhdpi.
LAUNCHER_SIZES = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}


def cutout(image: Image.Image, *, detail: float, erode: int, keep: int) -> Image.Image:
    """Détoure le sujet net d'un fond uni ou dégradé, halo compris.

    `detail` : seuil de netteté au-dessus duquel un pixel appartient au sujet.
    `erode`  : pixels de bord retirés, ceux qui portent encore la couleur du fond.
    `keep`   : taille minimale d'une composante conservée (retire le grain).
    """
    rgb = image.convert("RGB")
    pixels = np.asarray(rgb).astype(np.float32)
    blurred = np.asarray(rgb.filter(ImageFilter.GaussianBlur(9))).astype(np.float32)
    sharpness = np.abs(pixels - blurred).max(axis=2)

    mask = ndimage.binary_closing(sharpness > detail, structure=np.ones((25, 25)))
    mask = ndimage.binary_fill_holes(mask)
    labels, count = ndimage.label(mask)
    sizes = ndimage.sum(mask, labels, range(1, count + 1))
    mask = np.isin(labels, [i + 1 for i, s in enumerate(sizes) if s > keep])
    if erode:
        mask = ndimage.binary_erosion(mask, structure=np.ones((erode, erode)))

    soft = Image.fromarray(np.uint8(mask * 255)).filter(ImageFilter.GaussianBlur(1.2))
    alpha = np.clip((np.asarray(soft).astype(np.float32) - 110) * 3.5, 0, 255)
    cut = Image.fromarray(np.dstack([pixels, alpha]).astype(np.uint8), "RGBA")
    return cut.crop(cut.getbbox())


def fit(image: Image.Image, width: int) -> Image.Image:
    height = round(image.height * width / image.width)
    return image.resize((width, height), Image.LANCZOS)


def save_webp(image: Image.Image, path: pathlib.Path, quality: int = 88) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "WEBP", quality=quality, method=6)
    print(f"  {path.relative_to(ROOT)}  {path.stat().st_size / 1024:.1f} Ko  {image.size}")


def main() -> None:
    print("Logo ZarmaIA (détourage du halo)")
    logo = cutout(Image.open(SOURCE / "logo.png"), detail=10, erode=7, keep=3000)
    save_webp(fit(logo, 720), ASSETS / "logo.webp")

    print("Logo PTR-Niger")
    ptr = Image.open(SOURCE / "logo-ptrniger.png").convert("RGBA")
    save_webp(fit(ptr.crop(ptr.getbbox()), 240), ASSETS / "ptr_niger.webp")

    print("Marque carrée (icône dans l'application)")
    icon = Image.open(SOURCE / "icone.png").convert("RGB")
    # Le carré bleu nuit se détache du blanc : seuil sur la luminance, pas de netteté.
    dark = np.asarray(icon).astype(np.float32).mean(axis=2) < 200
    box = Image.fromarray(np.uint8(dark * 255)).getbbox()
    square = Image.open(SOURCE / "icone.png").convert("RGBA").crop(box)
    save_webp(fit(square, 320), ASSETS / "icon.webp")

    print("Icône de lanceur Android (héritée + adaptative)")
    # Fond plein : les coins arrondis de la source seraient re-masqués par le
    # lanceur, un carré plein évite le liseré blanc résiduel.
    legacy = Image.new("RGB", square.size, NAVY)
    legacy.paste(square, (0, 0), square)

    # La bordure arrondie de la source est elle-même un contour net : à moins
    # de l'exclure, `cutout` la confond avec le sujet. On rogne une marge
    # avant détourage — le contenu utile en est loin — puis on retire l'alpha
    # sur ce même rectangle pour rester cohérent avec `square`.
    margin = round(square.width * 0.06)
    inset = square.crop(
        (margin, margin, square.width - margin, square.height - margin)
    ).convert("RGB")
    mark = cutout(inset, detail=10, erode=3, keep=1500)
    for folder, size in LAUNCHER_SIZES.items():
        (RES / folder).mkdir(parents=True, exist_ok=True)
        legacy.resize((size, size), Image.LANCZOS).save(
            RES / folder / "ic_launcher.png", optimize=True
        )
        # Avant-plan adaptatif : canevas 108 dp, sujet dans la zone sûre de 66 dp.
        canvas_px = round(size * 108 / 48)
        safe_px = round(canvas_px * 0.62)
        foreground = Image.new("RGBA", (canvas_px, canvas_px), (0, 0, 0, 0))
        scaled = fit(mark, safe_px) if mark.width >= mark.height else mark.resize(
            (round(mark.width * safe_px / mark.height), safe_px), Image.LANCZOS
        )
        foreground.paste(
            scaled,
            ((canvas_px - scaled.width) // 2, (canvas_px - scaled.height) // 2),
            scaled,
        )
        foreground.save(RES / folder / "ic_launcher_foreground.png", optimize=True)
    print(f"  {len(LAUNCHER_SIZES)} densités écrites dans android/app/src/main/res")


if __name__ == "__main__":
    main()
