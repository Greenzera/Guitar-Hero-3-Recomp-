#!/usr/bin/env python3
"""
Live progress viewer for a rexglue codegen run.

Why this exists: at --log-level info the GapFill phase writes nothing for tens
of minutes, so a healthy run looks identical to a hung one. This shows the
current phase, how long it has been running against a known baseline, and --
the part that actually settles the question -- whether the process is still
burning CPU. A deadlocked process sits at ~0%; a working one sits near 100% of
one core.

Usage:
    python tools/codegen_watch.py [log-file] [--interval N]

Defaults to codegen_tu.err.log / codegen.log in the current directory
(rexglue writes its progress to stderr).
"""
import argparse
import os
import re
import subprocess
import sys
import time
from datetime import timedelta

# Phase -> (typical duration in seconds, note).
#
# MEDIDO: o codegen completo do GH3 leva ~62 s (nao os ~28 min que a estimativa
# inicial, escalada do PES 2017, previa -- o GH3 e uma ordem de grandeza mais
# pequeno). O rexglue nao poe timestamps no log, por isso a reparticao por fase
# abaixo e proporcional e nao medida; o total e que esta ancorado na realidade.
#
# A consequencia pratica: neste jogo o watcher e quase dispensavel, o codegen
# acaba antes de valer a pena abrir outra janela. Fica para quando os hints
# crescerem e o Discover/GapFill se alongarem.
PHASES = [
    ("Register", 3, ""),
    ("Scan", 5, ""),
    ("Discover", 12, "descoberta iterativa + PDATA"),
    ("GapFill", 20, "SILENCIOSO em --log-level info (normal)"),
    ("Merge", 4, ""),
    ("Validate", 3, "aqui aparecem os UnresolvedCall"),
    ("Write", 15, "escreve os .cpp gerados"),
]
PHASE_NAMES = [p[0] for p in PHASES]
TOTAL_BASELINE = sum(p[1] for p in PHASES)

PHASE_RE = re.compile(r"phase\s+\S+:\s+(\w+)")
DONE_RE = re.compile(r"Done in ([\d.]+)s|done\s+\S+\s+\(([\d.]+)s\)")
FAIL_RE = re.compile(r"Failed:(.*)")


def fmt(seconds):
    return str(timedelta(seconds=int(seconds)))


def cpu_seconds(proc_name="rexglue.exe"):
    """Total CPU seconds and RSS for the process, or None if it is not running."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"$p=Get-Process -Name '{proc_name.replace('.exe','')}' -ErrorAction SilentlyContinue;"
             f"if($p){{'{{0}} {{1}}' -f $p.CPU,$p.WorkingSet64}}"],
            capture_output=True, text=True, timeout=20)
        s = out.stdout.strip()
        if not s:
            return None
        cpu, rss = s.split()
        return float(cpu), int(rss)
    except Exception:
        return None


def read_log(path):
    """Return (phases_seen, finished_text, failed_text, mtime)."""
    if not os.path.exists(path):
        return [], None, None, 0
    with open(path, "r", errors="replace") as f:
        text = f.read()
    phases = PHASE_RE.findall(text)
    done = DONE_RE.search(text)
    fail = FAIL_RE.search(text)
    return (phases,
            done.group(0) if done else None,
            fail.group(1).strip() if fail else None,
            os.path.getmtime(path))


def bar(done, total, width=34):
    filled = 0 if total <= 0 else min(width, int(width * done / total))
    return "#" * filled + "." * (width - filled)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log", nargs="?", default=None)
    ap.add_argument("--interval", type=int, default=15)
    ap.add_argument("--process", default="rexglue.exe")
    args = ap.parse_args()

    log = args.log
    if log is None:
        for cand in ("codegen_090.err.log", "codegen.err.log", "codegen_090.log", "codegen.log"):
            if os.path.exists(cand):
                log = cand
                break
    if log is None:
        sys.exit("nenhum log de codegen encontrado (passe o caminho como argumento)")

    # No wall-clock start time is trustworthy here: rexglue's info log carries no
    # timestamps, and the file's creation time lies on Windows (file system
    # tunneling reuses it when a log of the same name is recreated). Progress is
    # therefore derived from completed-phase baselines plus time in the current
    # phase, which is measured exactly (see phase_started below).
    phase_started = {}
    last_phase = None
    prev_cpu = None
    first_poll = True

    print(f"a observar: {log}   (baseline total ~{fmt(TOTAL_BASELINE)})")
    print("Ctrl+C para sair -- nao afeta o codegen\n")

    while True:
        phases, done, failed, mtime = read_log(log)
        now = time.time()
        cur = phases[-1] if phases else None

        if cur != last_phase:
            # rexglue logs each phase as it enters it, so on the first poll of a
            # run already in progress the log's last write is that phase line --
            # a better start time than "now". After that we see the transitions.
            phase_started[cur] = mtime if first_poll and mtime else now
            last_phase = cur
        first_poll = False

        proc = cpu_seconds(args.process)
        alive = proc is not None
        cpu_pct = None
        if proc and prev_cpu is not None:
            dt = now - prev_cpu[1]
            if dt > 0:
                cpu_pct = (proc[0] - prev_cpu[0]) / dt * 100
        if proc:
            prev_cpu = (proc[0], now)

        idx = PHASE_NAMES.index(cur) if cur in PHASE_NAMES else -1
        spent_before = sum(p[1] for p in PHASES[:max(idx, 0)])
        in_phase = now - phase_started.get(cur, now)
        est = spent_before + in_phase

        os.system("cls" if os.name == "nt" else "clear")
        print(f"  rexglue codegen  --  {log}")
        print(f"  {'=' * 60}")
        for i, (name, baseline, note) in enumerate(PHASES):
            if idx > i or (done and idx == i):
                mark, extra = "[x]", ""
            elif idx == i:
                over = " (ACIMA do baseline)" if in_phase > baseline * 1.25 else ""
                mark, extra = "[>]", f"  {fmt(in_phase)} / ~{fmt(baseline)}{over}"
            else:
                mark, extra = "[ ]", ""
            print(f"  {mark} {name:<10}{extra}")
            if idx == i and note:
                print(f"      nota: {note}")
        print(f"  {'=' * 60}")
        print(f"  decorrido (est.) : {fmt(est)}  de ~{fmt(TOTAL_BASELINE)}")
        print(f"  progresso : [{bar(est, TOTAL_BASELINE)}] {min(99, int(est / TOTAL_BASELINE * 100))}%")
        print(f"  log escrito ha : {fmt(now - mtime) if mtime else '--'}"
              + ("   <- normal no GapFill" if cur == "GapFill" else ""))
        if alive:
            rss_mb = proc[1] / (1024 * 1024)
            health = "a trabalhar" if (cpu_pct is None or cpu_pct > 20) else "SUSPEITO: CPU quase parado"
            pct = f"{cpu_pct:.0f}%" if cpu_pct is not None else "..."
            print(f"  processo  : vivo   CPU {pct} de 1 nucleo   RAM {rss_mb:.0f} MB   -> {health}")
        else:
            print("  processo  : NAO esta a correr")

        if failed:
            print(f"\n  FALHOU: {failed}")
            return 1
        if done:
            print(f"\n  CONCLUIDO: {done}")
            return 0
        if not alive:
            print("\n  processo desapareceu sem marcador de conclusao (interrompido?)")
            return 2

        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrompido (o codegen continua a correr)")
