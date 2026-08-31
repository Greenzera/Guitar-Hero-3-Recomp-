#!/usr/bin/env python3
"""Extrai os shaders SPIR-V de frame generation de dentro do Lossless.dll.

Descoberta que torna isto simples: o Lossless Scaling ja embarca versoes Vulkan
(SPIR-V) dos seus shaders de interpolacao na resource section (.rsrc) do DLL --
nao e preciso traduzir DXBC nenhum. Cada shader e um recurso PE identificado por
um id numerico; o pipeline do LSFG referencia-os por esse id.

Nada do Lossless Scaling e redistribuido: o utilizador fornece o SEU Lossless.dll
(comprado), e a extracao acontece na maquina dele, para uma pasta de cache. E o
mesmo modelo do lsfg-vk e do ARMSX2.

O parsing da .rsrc e formato PE padrao (Microsoft PE/COFF). A arvore de recursos
tem tres niveis: Tipo -> Nome/Id -> Idioma -> (offset, tamanho) dos dados.

Uso:
    python extract_lsfg_spirv.py "<caminho para Lossless.dll>" [--out <pasta>]
"""

import argparse
import os
import struct
import sys

SPIRV_MAGIC = 0x07230203


def u16(d, o): return struct.unpack_from("<H", d, o)[0]
def u32(d, o): return struct.unpack_from("<I", d, o)[0]


def parse_pe(path):
    """Devolve (data, secoes, rsrc_rva). secoes = [(va, vsize, raw_ptr, raw_size)]."""
    d = open(path, "rb").read()
    if d[:2] != b"MZ":
        raise SystemExit("nao e um PE (falta 'MZ')")
    pe = u32(d, 0x3C)
    if d[pe:pe+4] != b"PE\0\0":
        raise SystemExit("assinatura PE invalida")
    coff = pe + 4
    nsec = u16(d, coff + 2)
    opt_size = u16(d, coff + 16)
    opt = coff + 20
    magic = u16(d, opt)
    # data directories: offset difere entre PE32 (0x60) e PE32+ (0x70)
    dd = opt + (0x70 if magic == 0x20B else 0x60)
    # directory[2] = resource table
    rsrc_rva = u32(d, dd + 2 * 8)
    sec_tab = opt + opt_size
    secs = []
    for i in range(nsec):
        o = sec_tab + i * 40
        va = u32(d, o + 12)
        vsize = u32(d, o + 8)
        raw_ptr = u32(d, o + 20)
        raw_size = u32(d, o + 16)
        secs.append((va, vsize, raw_ptr, raw_size))
    return d, secs, rsrc_rva


def rva_to_off(secs, rva):
    for va, vsize, raw_ptr, raw_size in secs:
        if va <= rva < va + max(vsize, raw_size):
            return raw_ptr + (rva - va)
    return None


def walk_resources(d, secs, rsrc_rva):
    """Percorre a arvore de recursos, produz (tipo, nome, lang, data_off, size)."""
    base = rva_to_off(secs, rsrc_rva)
    if base is None:
        raise SystemExit("resource section nao encontrada")

    out = []

    def entries(dir_off):
        # IMAGE_RESOURCE_DIRECTORY: 12 bytes de cabecalho, depois entradas de 8 bytes
        n_named = u16(d, dir_off + 12)
        n_id = u16(d, dir_off + 14)
        res = []
        for i in range(n_named + n_id):
            eo = dir_off + 16 + i * 8
            name_or_id = u32(d, eo)
            offset = u32(d, eo + 4)
            res.append((name_or_id, offset))
        return res

    # Nivel 1: tipos
    for type_val, type_off in entries(base):
        if not (type_off & 0x80000000):
            continue  # devia ser subdiretorio
        t_dir = base + (type_off & 0x7FFFFFFF)
        # Nivel 2: nomes/ids
        for name_val, name_off in entries(t_dir):
            if not (name_off & 0x80000000):
                continue
            n_dir = base + (name_off & 0x7FFFFFFF)
            # Nivel 3: idiomas -> data entry
            for lang_val, lang_off in entries(n_dir):
                if lang_off & 0x80000000:
                    continue  # esperavamos uma data entry, nao um dir
                data_entry = base + lang_off
                data_rva = u32(d, data_entry)
                size = u32(d, data_entry + 4)
                data_off = rva_to_off(secs, data_rva)
                out.append((type_val & 0x7FFFFFFF, name_val & 0x7FFFFFFF,
                            lang_val & 0x7FFFFFFF, data_off, size))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dll", help="caminho para o Lossless.dll do utilizador")
    ap.add_argument("--out", default=None, help="pasta de saida (.spv)")
    args = ap.parse_args()

    if not os.path.isfile(args.dll):
        print("[ERRO] nao encontrei: %s" % args.dll, file=sys.stderr)
        return 1
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "..", "..", "..", "lsfg-cache")
    out = os.path.abspath(out)
    os.makedirs(out, exist_ok=True)

    d, secs, rsrc_rva = parse_pe(args.dll)
    print("Lossless.dll: %d bytes, %d secoes" % (len(d), len(secs)))
    res = walk_resources(d, secs, rsrc_rva)
    print("recursos na .rsrc: %d" % len(res))

    saved = 0
    ids = []
    for type_val, name_id, lang, off, size in res:
        if off is None or size < 20 or off + size > len(d):
            continue
        if u32(d, off) != SPIRV_MAGIC:
            continue
        # SPIR-V tem de ser multiplo de 4 palavras; confiar no tamanho do recurso
        fn = os.path.join(out, "lsfg_%d.spv" % name_id)
        with open(fn, "wb") as fh:
            fh.write(d[off:off + size])
        saved += 1
        ids.append(name_id)

    print("shaders SPIR-V extraidos: %d" % saved)
    if ids:
        print("ids: %s" % ", ".join(str(i) for i in sorted(ids)))
    print("pasta: %s" % out)
    if saved == 0:
        print("\n[AVISO] nenhum SPIR-V nos recursos. Ou o DLL nao e uma versao com\n"
              "        shaders Vulkan embarcados, ou o layout mudou.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
