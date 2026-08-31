"""Escreve a assinatura DENTRO da imagem de arranque do jogo.

O ecra legal do arranque e' DATA/COMPRESSED/IMAGES/LOADINGSCREENS/boot_legal.img.xen.
Formato, decifrado por tentativa: deflate cru (zlib com wbits=-15), cabecalho de
0x1000 bytes, e a seguir 1024x512 em DXT1, no arranjo "tiled" do Xbox 360 e com
os bytes trocados aos pares (big-endian).

O resultado NAO substitui o ficheiro original: sai para game/MODS/, onde o
sistema de mods o sobrepoe. Assim o jogo base fica intacto e basta desligar o
mod para voltar atras.

Uso:
    python tools/brand_boot_screen.py            # gera o mod
    python tools/brand_boot_screen.py --preview  # so' mostra como fica
"""
import argparse
import io
import os
import struct
import zlib

from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
BASE_JOGO = os.path.abspath(os.path.join(RAIZ, "..", "game"))

REL = os.path.join("DATA", "COMPRESSED", "IMAGES", "LOADINGSCREENS", "boot_legal.img.xen")
NOME_MOD = "assinatura-recomp"

HEADER = 0x1000
LARG, ALT = 1024, 512
BLOCO = 8  # DXT1


# --------------------------------------------------------------- tiling do 360
def xg_offset(x, y, width_blocos, texel_pitch):
    """XGAddress2DTiledOffset: (x,y) em blocos -> indice do bloco no ficheiro."""
    aw = (width_blocos + 31) & ~31
    lb = (texel_pitch >> 2) + ((texel_pitch >> 1) >> (texel_pitch >> 2))
    macro = ((x >> 5) + (y >> 5) * (aw >> 5)) << (lb + 7)
    micro = ((x & 7) + ((y & 6) << 2)) << lb
    off = (macro + ((micro & ~15) << 1) + (micro & 15) +
           ((y & 8) << (3 + lb)) + ((y & 1) << 4))
    return ((((off & ~511) << 3) + ((off & 448) << 2) + (off & 63) +
             ((y & 16) << 7) + (((((y & 8) >> 2) + (x >> 3)) & 3) << 6)) >> lb)


def mapa_blocos():
    """Par (destino_linear, origem_tiled) para cada bloco. Serve nos dois sentidos."""
    bw, bh = LARG // 4, ALT // 4
    return [((by * bw + bx) * BLOCO, xg_offset(bx, by, bw, BLOCO) * BLOCO)
            for by in range(bh) for bx in range(bw)]


def bswap16(b):
    a = bytearray(b)
    a[0::2], a[1::2] = b[1::2], b[0::2]
    return bytes(a)


def dds_header(w, h, tamanho):
    hdr = bytearray(128)
    hdr[0:4] = b"DDS "
    struct.pack_into("<I", hdr, 4, 124)
    struct.pack_into("<I", hdr, 8, 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000)
    struct.pack_into("<I", hdr, 12, h)
    struct.pack_into("<I", hdr, 16, w)
    struct.pack_into("<I", hdr, 20, tamanho)
    struct.pack_into("<I", hdr, 76, 32)
    struct.pack_into("<I", hdr, 80, 0x4)
    hdr[84:88] = b"DXT1"
    struct.pack_into("<I", hdr, 108, 0x1000)
    return bytes(hdr)


def descodificar(caminho):
    bruto = zlib.decompress(open(caminho, "rb").read(), -15)
    cabecalho, corpo = bruto[:HEADER], bswap16(bruto[HEADER:])
    linear = bytearray(len(corpo))
    for dst, src in mapa_blocos():
        linear[dst:dst + BLOCO] = corpo[src:src + BLOCO]
    img = Image.open(io.BytesIO(dds_header(LARG, ALT, len(linear)) + bytes(linear)))
    img.load()
    return cabecalho, img.convert("RGB")


def codificar(cabecalho, img):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="DDS", pixel_format="DXT1")
    linear = buf.getvalue()[128:]
    esperado = (LARG // 4) * (ALT // 4) * BLOCO
    if len(linear) != esperado:
        raise SystemExit("DXT1 deu %d bytes, esperava %d" % (len(linear), esperado))
    tiled = bytearray(esperado)
    for dst, src in mapa_blocos():
        tiled[src:src + BLOCO] = linear[dst:dst + BLOCO]
    corpo = bswap16(bytes(tiled))
    # Nivel 9: o ficheiro original tem ~31 KB e o jogo le por streaming; nao ha
    # motivo para o mod ficar maior do que precisa.
    comp = zlib.compressobj(9, zlib.DEFLATED, -15)
    return comp.compress(cabecalho + corpo) + comp.flush()


def compor(img):
    """Assenta a assinatura por baixo do 'LEGENDS of ROCK'."""
    marca_png = os.path.join(RAIZ, "assets", "watermark.png")
    if not os.path.exists(marca_png):
        raise SystemExit("falta %s -- corre tools/make_watermark.py primeiro" % marca_png)
    marca = Image.open(marca_png).convert("RGBA")

    # O logotipo ocupa a metade esquerda; o "LEGENDS of ROCK" acaba por volta de
    # y=325 e vai de x~215 a x~490. A assinatura fica centrada nesse eixo.
    largura_alvo = 300
    escala = largura_alvo / marca.width
    marca = marca.resize((largura_alvo, max(1, int(marca.height * escala))), Image.LANCZOS)

    centro_x, topo_y = 352, 336
    fora = img.convert("RGBA")
    fora.alpha_composite(marca, (centro_x - marca.width // 2, topo_y))
    return fora.convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true", help="so gera o PNG de pre-visualizacao")
    ap.add_argument("--game", default=BASE_JOGO, help="pasta game/ do jogo")
    args = ap.parse_args()

    origem = os.path.join(args.game, REL)
    if not os.path.exists(origem):
        raise SystemExit("nao encontrei %s" % origem)

    cabecalho, img = descodificar(origem)
    print("descodificado: %dx%d" % img.size)

    marcada = compor(img)
    previa = os.path.join(RAIZ, "assets", "boot_legal_preview.png")
    marcada.save(previa)
    print("pre-visualizacao: %s" % previa)
    if args.preview:
        return

    destino = os.path.join(args.game, "MODS", NOME_MOD, REL)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    dados = codificar(cabecalho, marcada)
    with open(destino, "wb") as f:
        f.write(dados)
    print("mod escrito: %s (%.1f KB, original %.1f KB)" %
          (destino, len(dados) / 1024, os.path.getsize(origem) / 1024))
    print()
    print("Fica ativo assim que o jogo arrancar. Para desligar, cria um ficheiro")
    print(".disabled dentro de MODS/%s (ou usa a aba Mods do menu)." % NOME_MOD)


if __name__ == "__main__":
    main()
