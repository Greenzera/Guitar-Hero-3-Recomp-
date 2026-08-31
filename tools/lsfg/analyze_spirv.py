#!/usr/bin/env python3
"""Analisa os shaders SPIR-V do LSFG para reconstruir o grafo do pipeline.

Isto e engenharia PROPRIA a partir dos binarios SPIR-V (que vem do DLL do
utilizador), nao uma copia do lsfg-vk. Para cada shader extrai, so pela leitura
do bytecode:
  - workgroup size (OpExecutionMode LocalSize)
  - imagens de ENTRADA  (OpTypeImage amostrada/lida)  por binding
  - imagens de SAIDA    (storage image, escrita)      por binding
  - buffers/push constants
Com estes inputs/outputs por shader consegue-se inferir quem alimenta quem, sem
olhar para a receita de nenhum projeto de licenca incompativel.

Uso:
    python analyze_spirv.py <pasta com lsfg_*.spv>
"""

import argparse
import glob
import os
import struct
import sys

# Opcodes que interessam
OP_ENTRY_POINT = 15
OP_EXECUTION_MODE = 16
OP_NAME = 5
OP_DECORATE = 71
OP_TYPE_IMAGE = 25
OP_TYPE_POINTER = 32
OP_VARIABLE = 59
OP_TYPE_SAMPLED_IMAGE = 27

EXEC_LOCAL_SIZE = 17
DEC_BINDING = 33
DEC_DESCRIPTOR_SET = 34
DEC_BUILTIN = 11

# storage classes
SC_UNIFORM_CONSTANT = 0
SC_UNIFORM = 2
SC_PUSH_CONSTANT = 9
SC_STORAGE_BUFFER = 12


def parse(path):
    d = open(path, "rb").read()
    if len(d) < 20 or struct.unpack_from("<I", d, 0)[0] != 0x07230203:
        return None
    words = struct.unpack("<%dI" % (len(d) // 4), d[:len(d) // 4 * 4])
    i = 5
    info = {
        "local_size": None,
        "type_image": {},      # result_id -> (sampled_flag, format)
        "sampled_image": set(),
        "pointer": {},         # result_id -> (storage_class, pointee_id)
        "variables": [],       # (result_id, storage_class, type_id)
        "binding": {},         # result_id -> binding
        "descset": {},         # result_id -> set
    }
    while i < len(words):
        w = words[i]
        op = w & 0xFFFF
        wc = w >> 16
        if wc == 0:
            break
        if op == OP_EXECUTION_MODE and words[i + 2] == EXEC_LOCAL_SIZE:
            info["local_size"] = (words[i + 3], words[i + 4], words[i + 5])
        elif op == OP_TYPE_IMAGE:
            rid = words[i + 1]
            sampled = words[i + 7]  # 1 = usada com sampler (leitura), 2 = storage
            fmt = words[i + 8]
            info["type_image"][rid] = (sampled, fmt)
        elif op == OP_TYPE_SAMPLED_IMAGE:
            info["sampled_image"].add(words[i + 1])
        elif op == OP_TYPE_POINTER:
            info["pointer"][words[i + 1]] = (words[i + 2], words[i + 3])
        elif op == OP_VARIABLE:
            info["variables"].append((words[i + 2], words[i + 3], words[i + 1]))
        elif op == OP_DECORATE:
            target = words[i + 2]
            dec = words[i + 3]
            if dec == DEC_BINDING:
                info["binding"][target] = words[i + 4]
            elif dec == DEC_DESCRIPTOR_SET:
                info["descset"][target] = words[i + 4]
        i += wc
    return info


def classify(info):
    """Devolve (inputs, outputs, buffers, push). in/out sao listas de binding."""
    inputs, outputs, buffers, push = [], [], [], 0
    for rid, sc, ptype in info["variables"]:
        binding = info["binding"].get(rid)
        if sc == SC_PUSH_CONSTANT:
            push += 1
            continue
        # o tipo da variavel e um ponteiro; segue para o pointee
        pointee = None
        if ptype in info["pointer"]:
            _, pointee = info["pointer"][ptype]
        if sc == SC_UNIFORM_CONSTANT:
            # imagem: storage (saida) vs amostrada (entrada)
            if pointee in info["type_image"]:
                sampled, fmt = info["type_image"][pointee]
                if sampled == 2:
                    outputs.append(binding)
                else:
                    inputs.append(binding)
            elif pointee in info["sampled_image"]:
                inputs.append(binding)
            else:
                inputs.append(binding)  # sampler ou outro recurso lido
        elif sc in (SC_UNIFORM, SC_STORAGE_BUFFER):
            buffers.append(binding)
    return (sorted(x for x in inputs if x is not None),
            sorted(x for x in outputs if x is not None),
            sorted(x for x in buffers if x is not None), push)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", help="pasta com lsfg_*.spv")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, "lsfg_*.spv")),
                   key=lambda p: int(os.path.basename(p)[5:-4]))
    if not files:
        print("sem shaders em %s" % args.dir, file=sys.stderr)
        return 1

    print("%-6s %-12s %-14s %-14s %-8s %s" %
          ("id", "workgroup", "entradas(bind)", "saidas(bind)", "buffers", "push"))
    print("-" * 76)
    rows = []
    for f in files:
        sid = int(os.path.basename(f)[5:-4])
        info = parse(f)
        if not info:
            continue
        ins, outs, bufs, push = classify(info)
        ls = info["local_size"]
        lss = "%dx%dx%d" % ls if ls else "?"
        rows.append((sid, lss, ins, outs, bufs, push))
        print("%-6d %-12s %-14s %-14s %-8s %d" %
              (sid, lss, ",".join(map(str, ins)) or "-",
               ",".join(map(str, outs)) or "-", ",".join(map(str, bufs)) or "-", push))

    # sumario: agrupar por assinatura (n entradas -> n saidas) revela os "tipos"
    print("\n--- tipos de shader por assinatura (entradas->saidas) ---")
    sig = {}
    for sid, lss, ins, outs, bufs, push in rows:
        key = (len(ins), len(outs))
        sig.setdefault(key, []).append(sid)
    for (ni, no), ids in sorted(sig.items()):
        print("  %d entrada(s) -> %d saida(s): %d shaders  (ids %s%s)" %
              (ni, no, len(ids), ", ".join(map(str, ids[:8])),
               " ..." if len(ids) > 8 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
