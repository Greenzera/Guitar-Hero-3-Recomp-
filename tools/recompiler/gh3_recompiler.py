#!/usr/bin/env python3
"""GH3 Mod Recompiler -- recompila o jogo a partir do default.xex de um mod.

Porque e preciso: um recomp executa C++ compilado a partir de UM xex especifico.
Um mod que altera o executavel (o GH3 Deluxe) tem o seu proprio xex e nao pode
so substituir o ficheiro -- o runtime leria de la um entry point que nao
corresponde a nenhuma funcao registada, e o jogo morre com "No function
registered at ...". Este e o unico xex que a maioria dos mods altera, mas quando
altera, precisa do seu proprio build.

MODO AUTOMATICO (sem argumentos): varre a pasta de mods, deteta os que trazem um
default.xex e ainda NAO tem um build recompilado (emparelhando por hash com os
builds existentes), e recompila cada um. Depois disso o launcher reconhece-os
sozinho. E este o "automatiza tudo": instalas o mod, corres isto, e joga.

MODO MANUAL: passa um caminho para um default.xex e recompila so esse.

O ciclo de cada recompilacao (copiar xex -> codegen -> resolver UnresolvedCall
-> validar rotulos -> build) e automatico. O que NAO se automatiza: orfas que so
aparecem em runtime (rotinas chamadas por ponteiro num caminho especifico). Essas
so se descobrem jogando; o log da o endereco e volta-se a correr com --extra-hint.

Uso:
    gh3_recompiler.exe                       (auto: varre a pasta de mods)
    gh3_recompiler.exe <xex>                 (manual: so esse xex)
    gh3_recompiler.exe <xex> --nome deluxe --extra-hint 0x825E9B20
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# A ferramenta vive em tools/recompiler/, o projeto e dois niveis acima.
PROJ = os.path.abspath(os.path.join(HERE, "..", ".."))
ROOT = os.path.abspath(os.path.join(PROJ, ".."))
MODS = os.path.join(ROOT, "mods")
BUILDS = os.path.join(PROJ, "out", "build")

REXGLUE = os.path.join(
    r"C:\Users\Luis\Desktop\projeto_CLAUDE\skate3recomp\third_party",
    "rexglue-sdk", "out", "win-amd64", "rexglue.exe")

QUOTES = '"' + "'"


def log(msg, step=None):
    print(("[%s] " % step if step else "      ") + msg, flush=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def run(cmd, cwd=PROJ, out=None):
    if not out:
        return subprocess.call(cmd, cwd=cwd)
    with open(out + ".log", "w") as so, open(out + ".err.log", "w") as se:
        return subprocess.call(cmd, cwd=cwd, stdout=so, stderr=se)


def unresolved_targets(err_path):
    if not os.path.exists(err_path):
        return []
    found = []
    with open(err_path, errors="replace") as fh:
        for line in fh:
            if "target not in any function" in line:
                m = re.match(r"\s*(0x[0-9A-Fa-f]{8})", line)
                if m:
                    found.append("0x" + m.group(1)[2:].upper())
    return sorted(set(found))


def sweep(xex, addrs):
    if not addrs:
        return []
    cmd = [sys.executable, os.path.join(PROJ, "tools", "xex_image.py"),
           xex, "--sweep"] + list(addrs)
    res = subprocess.run(cmd, cwd=PROJ, capture_output=True, text=True)
    return [l for l in res.stdout.splitlines() if l.startswith('"0x')]


def builds_by_hash():
    """{hash do xex de origem -> pasta do build} para os builds ja existentes."""
    out = {}
    if not os.path.isdir(BUILDS):
        return out
    for d in os.listdir(BUILDS):
        stamp = os.path.join(BUILDS, d, "source-xex.sha256")
        exe = os.path.join(BUILDS, d, "gh3.exe")
        if os.path.isfile(stamp) and os.path.isfile(exe):
            with open(stamp) as fh:
                out[fh.read().strip().upper()] = d
    return out


def active_code_mods():
    """Mods ativos (sem .disabled) que trazem um default.xex."""
    mods = []
    if not os.path.isdir(MODS):
        return mods
    for name in sorted(os.listdir(MODS)):
        folder = os.path.join(MODS, name)
        if not os.path.isdir(folder):
            continue
        if os.path.exists(os.path.join(folder, ".disabled")):
            continue
        xex = os.path.join(folder, "default.xex")
        if os.path.isfile(xex):
            mods.append((name, xex))
    return mods


def variant_name(raw):
    return re.sub(r"[^A-Za-z0-9_-]", "-", raw).strip("-") or "mod"


def recompile_one(xex, name, extra_hints, jobs, max_rondas):
    """O ciclo completo para um xex. Devolve o caminho do exe, ou None."""
    extracted = os.path.join(ROOT, "extracted-" + name)
    manifest = os.path.join(PROJ, "gh3_manifest.%s.toml" % name)
    hints = os.path.join(PROJ, "config", "gh3%s_functions.toml" % name)
    gen_rel = "generated/" + name
    gen_abs = os.path.join(PROJ, "generated", name)
    started = time.time()

    print()
    print("-" * 66)
    print("  A recompilar variante '%s'" % name)
    print("-" * 66)

    # 1. copiar o xex
    os.makedirs(extracted, exist_ok=True)
    dest = os.path.join(extracted, "default.xex")
    shutil.copy2(xex, dest)
    log("%s  (%d bytes)" % (dest, os.path.getsize(dest)), "1/5")

    # 2. manifest e hints
    os.makedirs(gen_abs, exist_ok=True)
    if not os.path.exists(hints):
        with open(hints, "w") as fh:
            fh.write("# Fronteiras de funcao da variante '%s'.\n" % name)
            fh.write("# GERADO pelo GH3 Mod Recompiler; podes acrescentar a mao.\n\n")
            fh.write("[functions]\n")
    for h in extra_hints:
        for line in sweep(dest, [h]):
            with open(hints, "a") as fh:
                fh.write("\n# orfa de runtime, dada na linha de comandos\n%s\n" % line)
            log("hint de runtime: " + line, "2/5")
    with open(manifest, "w") as fh:
        fh.write('# Variante "%s" -- GERADO pelo GH3 Mod Recompiler.\n\n' % name)
        fh.write('[project]\nname = "gh3"\nsdk_version = "0.8.0"\n\n')
        fh.write('[entrypoint]\n')
        fh.write('file_path = "../extracted-%s/default.xex"\n' % name)
        fh.write('out_directory_path = "%s"\n\n' % gen_rel)
        fh.write('includes = [\n  "config/gh3%s_functions.toml",\n]\n' % name)
    log("manifest e hints prontos", "2/5")

    # 3. codegen, resolvendo o que faltar
    base = os.path.join(PROJ, "codegen_" + name)
    ok = False
    for ronda in range(1, max_rondas + 1):
        shutil.rmtree(gen_abs, ignore_errors=True)
        os.makedirs(gen_abs, exist_ok=True)
        log("ronda %d: a gerar codigo (2-3 min)..." % ronda, "3/5")
        if run([REXGLUE, "--log-level", "info", "codegen",
                os.path.basename(manifest)], out=base) == 0:
            n = len([f for f in os.listdir(gen_abs) if f.endswith(".cpp")])
            log("codegen OK -- %d ficheiros .cpp" % n, "3/5")
            ok = True
            break
        targets = unresolved_targets(base + ".err.log")
        if not targets:
            log("codegen falhou por outra razao; ve " + base + ".err.log", "3/5")
            return None
        log("%d chamadas por resolver; a varrer fronteiras..." % len(targets), "3/5")
        lines = sweep(dest, targets)
        if not lines:
            log("nao consegui varrer as fronteiras", "3/5")
            return None
        with open(hints, "a") as fh:
            fh.write("\n# ronda %d: alvos UnresolvedCall\n" % ronda)
            for l in lines:
                fh.write(l + "\n")
                log("  " + l, "3/5")
    if not ok:
        log("demasiadas rondas sem convergir", "3/5")
        return None

    # 4. validar rotulos (apanha 'undeclared label' em segundos)
    log("a validar rotulos...", "4/5")
    chk = subprocess.run([sys.executable,
                          os.path.join(PROJ, "tools", "check_generated_labels.py")],
                         cwd=PROJ, capture_output=True, text=True)
    if "labels em falta      : 0" not in chk.stdout:
        print(chk.stdout)
        log("ha hints que partem funcoes -- ve a lista acima", "4/5")
        return None
    log("rotulos consistentes", "4/5")

    # 5. build (o CMake escreve source-xex.sha256 e o gh3.default.toml certo)
    bat = os.path.join(PROJ, "build-%s.bat" % name)
    with open(os.path.join(PROJ, "build-081-dx.bat"), encoding="ascii", errors="replace") as fh:
        src = fh.read()
    src = src.replace("win-amd64-081-dx", "win-amd64-" + name)
    src = src.replace("-DGH3_VARIANT=dx", "-DGH3_VARIANT=" + name)
    src = src.replace("build081dx.log", "build%s.log" % name)
    with open(bat, "w", newline="\r\n", encoding="ascii", errors="replace") as fh:
        fh.write(src)
    log("a compilar (a primeira vez ~10 min)...", "5/5")
    if run(["cmd", "/c", bat, str(jobs)]) != 0:
        log("o build falhou -- ve build%s.log" % name, "5/5")
        return None

    exe = os.path.join(BUILDS, "win-amd64-" + name, "gh3.exe")
    log("PRONTO em %.1f min -- %s" % ((time.time() - started) / 60.0, exe), "5/5")
    return exe


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xex", nargs="?", help="default.xex do mod (modo manual)")
    ap.add_argument("--nome", default=None, help="nome da variante (modo manual)")
    ap.add_argument("--extra-hint", action="append", default=[],
                    help="endereco de orfa vinda de runtime (repetivel)")
    ap.add_argument("--jobs", default="4")
    ap.add_argument("--max-rondas", type=int, default=6)
    args = ap.parse_args()

    print("=" * 66)
    print("  GH3 Mod Recompiler")
    print("=" * 66)

    if not os.path.isfile(REXGLUE):
        print("\n[ERRO] rexglue.exe nao encontrado em:\n       %s" % REXGLUE)
        return 1

    # ---- MODO MANUAL: um xex especifico ----------------------------------
    if args.xex:
        xex = args.xex.strip().strip(QUOTES)
        if not os.path.isfile(xex):
            print("\n[ERRO] ficheiro nao encontrado: %s" % xex)
            return 1
        # nome: --nome, senao o da pasta que contem o xex, senao 'mod'
        name = variant_name(args.nome or os.path.basename(os.path.dirname(xex)))
        exe = recompile_one(xex, name, args.extra_hint, args.jobs, args.max_rondas)
        if not exe:
            return 1
        print("\n  Abre o jogo pelo atalho normal -- o launcher escolhe este")
        print("  build sozinho quando o mod '%s' estiver ativo." % name)
        return 0

    # ---- MODO AUTOMATICO: varrer a pasta de mods -------------------------
    print("\n  A procurar mods que alterem o executavel e faltem recompilar...")
    existing = builds_by_hash()
    mods = active_code_mods()

    if not mods:
        print("\n  Nenhum mod ATIVO com um default.xex proprio.")
        print("  (Mods so de dados nao precisam disto -- aplicam-se diretos.)")
        print("\n  Instala o mod na pasta:")
        print("    %s" % MODS)
        print("  ativa-o, e corre isto outra vez.")
        input("\n  Enter para sair.")
        return 0

    todo = []
    for name, xex in mods:
        h = sha256(xex)
        if h in existing:
            print("  [ja feito] %-24s -> %s" % (name, existing[h]))
        else:
            todo.append((name, xex))
            print("  [a fazer ] %s" % name)

    if not todo:
        print("\n  Tudo em dia -- todos os mods de codigo ativos ja tem build.")
        print("  Abre o jogo pelo atalho normal.")
        input("\n  Enter para sair.")
        return 0

    print("\n  %d para recompilar. Cada um leva ~10-15 min." % len(todo))
    failures = []
    for name, xex in todo:
        exe = recompile_one(xex, variant_name(name), [], args.jobs, args.max_rondas)
        if not exe:
            failures.append(name)

    print()
    print("=" * 66)
    if failures:
        print("  Terminou com falhas em: %s" % ", ".join(failures))
        print("  Ve os logs build<nome>.log em %s" % PROJ)
        code = 1
    else:
        print("  Tudo recompilado. Abre o jogo pelo atalho normal --")
        print("  o launcher escolhe o build certo conforme o mod ativo.")
        code = 0
    print("=" * 66)
    print("\n  Se crashar ao entrar numa musica, o log da um endereco em")
    print("  'Call to invalid or unregistered function at guest address 0x...'.")
    print("  Corre a ferramenta com esse mod:")
    print("    gh3_recompiler.exe <xex-do-mod> --extra-hint 0xESSEENDERECO")
    input("\n  Enter para sair.")
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrompido")
        sys.exit(130)
