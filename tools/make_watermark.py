"""Gera a assinatura do ecra de arranque.

Produz duas coisas a partir do mesmo desenho:
  - assets/watermark.png    -- para se ver e editar
  - src/gh3_watermark_png.h -- os mesmos pixeis em RGBA cru

O jogo usa o header, nao o PNG: assim a assinatura vive dentro do binario, sem
depender de o ficheiro existir em disco nem de haver descodificador de PNG no
modulo. Para mudar o visual, edita-se aqui e volta-se a correr isto.
"""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)

TEXTO_1 = "RECOMP"
TEXTO_2 = "by LUIS SANTOS"

# Grande e depois reduzido: o supersampling e o que tira as escadas das
# diagonais do Impact, que a esta dimensao ficariam serrilhadas.
ESCALA = 4
LARG, ALT = 1100 * ESCALA // 2, 190 * ESCALA // 2

OURO_TOPO = (255, 232, 150)
OURO_BASE = (218, 146, 24)
CONTORNO = (26, 18, 6)


def fonte(tam):
    return ImageFont.truetype("C:/Windows/Fonts/impact.ttf", tam)


def desenhar_texto(base, texto, fnt, cx, cy, cor, contorno_px):
    d = ImageDraw.Draw(base)
    d.text((cx, cy), texto, font=fnt, fill=cor, anchor="mm",
           stroke_width=contorno_px, stroke_fill=CONTORNO)


def gradiente(tamanho, topo, base):
    grad = Image.new("RGB", (1, tamanho[1]))
    for y in range(tamanho[1]):
        t = y / max(1, tamanho[1] - 1)
        # Curva ligeiramente puxada ao topo: o brilho concentra-se em cima,
        # como no lettering do proprio jogo.
        t = t ** 0.75
        grad.putpixel((0, y), tuple(int(topo[i] + (base[i] - topo[i]) * t) for i in range(3)))
    return grad.resize(tamanho, Image.BILINEAR)


img = Image.new("RGBA", (LARG, ALT), (0, 0, 0, 0))

f1 = fonte(int(76 * ESCALA / 2))
f2 = fonte(int(52 * ESCALA / 2))
cx = LARG // 2
y1 = int(ALT * 0.34)
y2 = int(ALT * 0.74)

# 1) mascara do texto, com contorno grosso
mascara = Image.new("L", (LARG, ALT), 0)
md = ImageDraw.Draw(mascara)
md.text((cx, y1), TEXTO_1, font=f1, fill=255, anchor="mm", stroke_width=int(5 * ESCALA / 2),
        stroke_fill=255)
md.text((cx, y2), TEXTO_2, font=f2, fill=255, anchor="mm", stroke_width=int(4 * ESCALA / 2),
        stroke_fill=255)

# 2) brilho por tras, para descolar do fundo preto do ecra de titulo
brilho = mascara.filter(ImageFilter.GaussianBlur(int(9 * ESCALA / 2)))
camada_brilho = Image.new("RGBA", (LARG, ALT), (255, 176, 40, 0))
camada_brilho.putalpha(brilho.point(lambda v: int(v * 0.55)))
img = Image.alpha_composite(img, camada_brilho)

# 3) contorno escuro
contorno = Image.new("RGBA", (LARG, ALT), (0, 0, 0, 0))
desenhar_texto(contorno, TEXTO_1, f1, cx, y1, CONTORNO, int(5 * ESCALA / 2))
desenhar_texto(contorno, TEXTO_2, f2, cx, y2, CONTORNO, int(4 * ESCALA / 2))
img = Image.alpha_composite(img, contorno)

# 4) o texto em si, preenchido com o gradiente dourado
preenchimento = Image.new("L", (LARG, ALT), 0)
pd = ImageDraw.Draw(preenchimento)
pd.text((cx, y1), TEXTO_1, font=f1, fill=255, anchor="mm")
pd.text((cx, y2), TEXTO_2, font=f2, fill=255, anchor="mm")
ouro = gradiente((LARG, ALT), OURO_TOPO, OURO_BASE).convert("RGBA")
ouro.putalpha(preenchimento)
img = Image.alpha_composite(img, ouro)

# 5) recortar a moldura vazia: com a tela folgada o texto ficava perdido no
# meio de transparencia, o que complica posiciona-lo e desperdica memoria.
caixa = img.getbbox()
if caixa:
    margem = int(6 * ESCALA / 2)
    caixa = (max(0, caixa[0] - margem), max(0, caixa[1] - margem),
             min(LARG, caixa[2] + margem), min(ALT, caixa[3] + margem))
    img = img.crop(caixa)

# 6) reduzir ao tamanho final
final = img.resize((img.width // (ESCALA // 2), img.height // (ESCALA // 2)), Image.LANCZOS)

assets = os.path.join(RAIZ, "assets")
os.makedirs(assets, exist_ok=True)
png = os.path.join(assets, "watermark.png")
final.save(png)
print("PNG   : %s  (%dx%d)" % (png, final.width, final.height))

# ---- header com os pixeis crus
dados = final.tobytes()
header = os.path.join(RAIZ, "src", "gh3_watermark_png.h")
with open(header, "w", newline="\n") as f:
    f.write("// GERADO por tools/make_watermark.py -- nao editar a mao.\n")
    f.write("// Assinatura do ecra de arranque, em RGBA cru (sem descodificador).\n")
    f.write("#pragma once\n\n#include <cstdint>\n\nnamespace gh3 {\n\n")
    f.write("constexpr uint32_t kWatermarkWidth = %d;\n" % final.width)
    f.write("constexpr uint32_t kWatermarkHeight = %d;\n\n" % final.height)
    f.write("inline constexpr uint8_t kWatermarkRgba[] = {\n")
    for i in range(0, len(dados), 24):
        f.write("    " + "".join("0x%02x," % b for b in dados[i:i + 24]) + "\n")
    f.write("};\n\nstatic_assert(sizeof(kWatermarkRgba) == "
            "kWatermarkWidth * kWatermarkHeight * 4, \"tamanho errado\");\n\n")
    f.write("}  // namespace gh3\n")
print("header: %s  (%.1f KB de pixeis)" % (header, len(dados) / 1024))
