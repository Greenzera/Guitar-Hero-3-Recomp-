"""Gera o icone do executavel a partir da logo do projeto.

Um .ico do Windows guarda varias resolucoes; o Explorer escolhe conforme o
contexto (16px na barra de titulo, 256px na vista de icones grandes). Gerar so'
uma e deixar o Windows reduzir da um resultado bem pior nas pequenas.

A logo tem margem transparente a mais e nao e quadrada: recorta-se ao conteudo
e assenta-se num quadrado, senao o icone aparece pequeno e descentrado.
"""
import os

from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)

ORIGEM = r"C:\Users\Luis\Desktop\gh3_recomp.png"
DESTINO = os.path.join(RAIZ, "assets", "gh3recomp.ico")

# 256 e o maximo que o formato guarda comprimido; abaixo disso sao as medidas
# que o Windows usa em barras, listas e na de tarefas.
TAMANHOS = [256, 128, 64, 48, 32, 24, 16]


def main():
    if not os.path.exists(ORIGEM):
        raise SystemExit("nao encontrei a logo em %s" % ORIGEM)

    img = Image.open(ORIGEM).convert("RGBA")

    caixa = img.getbbox()
    if caixa:
        img = img.crop(caixa)

    # Quadrado, com uma folga pequena para o icone nao encostar as bordas.
    lado = int(max(img.width, img.height) * 1.04)
    tela = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    tela.alpha_composite(img, ((lado - img.width) // 2, (lado - img.height) // 2))

    os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
    # LANCZOS em cada medida: deixar o Pillow gerar sozinho a partir da maior
    # borra as letras pequenas.
    quadros = [tela.resize((n, n), Image.LANCZOS) for n in TAMANHOS]
    quadros[0].save(DESTINO, format="ICO",
                    sizes=[(n, n) for n in TAMANHOS],
                    append_images=quadros[1:])
    print("icone: %s  (%s)" % (DESTINO, ", ".join("%dx%d" % (n, n) for n in TAMANHOS)))
    print("origem recortada: %dx%d -> tela %dx%d" % (img.width, img.height, lado, lado))


if __name__ == "__main__":
    main()
