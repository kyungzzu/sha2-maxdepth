#!/usr/bin/env python3
"""Recompute Tables 9-10 (attack costs and parallelized qubits under NIST
MAXDEPTH) exactly, from the integer gate counts / depths of Table 8.

Conventions (Section 4.1 of the paper):
  Oracle = forward SHA-2 + comparison + inverse  ->  ~2x single-circuit cost
  Preimage (Grover):  N_iter = (pi/4) * 2^(n/2)   ->  X_att = (pi/2) * 2^(n/2)  * X
  Collision (CNS)  :  N_iter = (pi/4) * 2^(2n/5)  ->  X_att = (pi/2) * 2^(2n/5) * X
      (X in {G, FD};  G = CNOT + 1qCliff + T)
  S = FD_att / MAXDEPTH
  Preimage : M_p = max(S,1)^2 * M
  Collision: M_p = 2^s * max(S_inst,1)^2 * M,  S_inst = FD_att / (2^(3s/5) * MAXDEPTH),
             s = n/6 exactly (no rounding)
  (Once the per-instance depth fits within MAXDEPTH, S is floored at 1: no
   further parallelization is possible below one machine per instance. This
   floor is reached only by the SHA-256 collision search at MAXDEPTH = 2^96.)

All arithmetic is done in log2, so no intermediate rounding is possible.
"Paper" columns are the values currently printed in Tables 9-10; DIFF means
the exact mantissa differs from the printed one (rounding propagated from
Table 9's two-digit mantissas into Table 10).
"""
from math import log2, pi, floor

# variant, impl, n, M, CNOT, 1qCliff, T, FD   (Table 8, exact integers)
ROWS = [
    ("SHA-256", "Jang", 256,  5715,   693832,  84086,  495089, 12791),
    ("SHA-256", "Ours", 256,  7245,   751546,  92147,  516213,  7504),
    ("SHA-384", "Jang", 384, 13773,  1847124, 225008, 1335511, 17257),
    ("SHA-384", "Ours", 384, 17633,  1995746, 249214, 1400609, 10783),
    ("SHA-512", "Jang", 512, 13901,  1864872, 226533, 1346011, 17303),
    ("SHA-512", "Ours", 512, 17633,  1995746, 249235, 1400609, 10783),
]

# Current Table 9 values: (G_att, FD_att) as (mantissa, exponent)
PAPER_T9 = {
    ("SHA-256","Jang","pre") : ((1.91,148),(1.23,142)),
    ("SHA-256","Ours","pre") : ((1.02,149),(1.44,141)),
    ("SHA-384","Jang","pre") : ((1.28,214),(1.65,206)),
    ("SHA-384","Ours","pre") : ((1.37,214),(1.03,206)),
    ("SHA-512","Jang","pre") : ((1.29,278),(1.66,270)),
    ("SHA-512","Ours","pre") : ((1.37,278),(1.03,270)),
    ("SHA-256","Jang","coll"): ((1.26,123),(1.62,116)),
    ("SHA-256","Ours","coll"): ((1.34,123),(1.90,115)),
    ("SHA-384","Jang","coll"): ((1.93,175),(1.25,168)),
    ("SHA-384","Ours","coll"): ((1.03,176),(1.57,167)),
    ("SHA-512","Jang","coll"): ((1.12,227),(1.44,219)),
    ("SHA-512","Ours","coll"): ((1.19,227),(1.80,218)),
}

# Current Table 10 values at MAXDEPTH = 2^40 (mantissa, exponent)
PAPER_T10 = {
    ("SHA-256","Jang","pre") : (1.05,217), ("SHA-256","Ours","pre") : (1.83,215),
    ("SHA-384","Jang","pre") : (1.15,347), ("SHA-384","Ours","pre") : (1.15,346),
    ("SHA-512","Jang","pre") : (1.17,475), ("SHA-512","Ours","pre") : (1.15,474),
    ("SHA-256","Jang","coll"): (1.26,157), ("SHA-256","Ours","coll"): (1.10,156),
    ("SHA-384","Jang","coll"): (1.52,257), ("SHA-384","Ours","coll"): (1.52,256),
    ("SHA-512","Jang","coll"): (1.69,355), ("SHA-512","Ours","coll"): (1.66,354),
}

MDS = (40, 64, 96)
LOG_PI_2 = log2(pi / 2)

def iters_log2(n, attack):
    return n / 2 if attack == "pre" else 2 * n / 5

def att_log2(x, n, attack):
    """log2 of attack-level quantity X_att = (pi/2) * 2^iters * X."""
    return LOG_PI_2 + iters_log2(n, attack) + log2(x)

def mp_log2(n, M, FD, attack, md):
    if attack == "coll":
        s = n / 6                                        # exact, no rounding
        S_inst = att_log2(FD, n, attack) - 3 * s / 5 - md  # log2 per-instance S
        return s + 2 * max(S_inst, 0.0) + log2(M)
    S = att_log2(FD, n, attack) - md
    return 2 * max(S, 0.0) + log2(M)

def m2(l2):
    e = floor(l2)
    return 2 ** (l2 - e), e

def fmt(l2):
    m, e = m2(l2)
    return f"{m:.2f}*2^{e}"

def check(l2, paper):
    m, e = m2(l2)
    pm, pe = paper
    return "OK  " if (e == pe and abs(m - pm) < 0.005) else "DIFF"

print("=" * 100)
print("Table 9 check: G_att and FD_att from exact integers")
print("=" * 100)
print(f"{'Row':16s}{'Atk':6s}{'G_att exact':>14s}{'paper':>12s}{'':>6s}{'FD_att exact':>14s}{'paper':>12s}")
for (v, impl, n, M, cn, cl, t, fd) in ROWS:
    G = cn + cl + t
    for atk in ("pre", "coll"):
        g_l2, fd_l2 = att_log2(G, n, atk), att_log2(fd, n, atk)
        pg, pfd = PAPER_T9[(v, impl, atk)]
        print(f"{v+' '+impl:16s}{atk:6s}{fmt(g_l2):>14s}"
              f"{f'{pg[0]:.2f}*2^{pg[1]}':>12s}  {check(g_l2,pg):4s}"
              f"{fmt(fd_l2):>14s}{f'{pfd[0]:.2f}*2^{pfd[1]}':>12s}  {check(fd_l2,pfd):4s}")

print()
print("=" * 100)
print("Table 10 check: M_p under MAXDEPTH in {2^40, 2^64, 2^96}  (exact, no intermediate rounding)")
print("=" * 100)
print(f"{'Row':16s}{'Atk':6s}" + "".join(f"{'Mp@2^%d'%md:>15s}" for md in MDS)
      + f"{'paper@2^40':>14s}{'':>6s}")
for (v, impl, n, M, cn, cl, t, fd) in ROWS:
    for atk in ("pre", "coll"):
        vals = [mp_log2(n, M, fd, atk, md) for md in MDS]
        p = PAPER_T10[(v, impl, atk)]
        print(f"{v+' '+impl:16s}{atk:6s}" + "".join(f"{fmt(x):>15s}" for x in vals)
              + f"{f'{p[0]:.2f}*2^{p[1]}':>14s}  {check(vals[0],p):4s}")

print()
print("Shift structure: log2 Mp(2^64) - log2 Mp(2^40) and log2 Mp(2^96) - log2 Mp(2^40)")
print("(-48 / -112 while S >= 1; SHA-256 collision hits the S = 1 floor at 2^96)")
v, impl, n, M, cn, cl, t, fd = ROWS[1]
for atk in ("pre", "coll"):
    a, b, c = (mp_log2(n, M, fd, atk, md) for md in MDS)
    print(f"  {atk:5s}: {b-a:+.4f}, {c-a:+.4f}")

print()
print("Ours vs Jang reduction in M_p (MAXDEPTH-independent):")
for i in (0, 2, 4):
    (v, _, n, Mj, cnj, clj, tj, fdj), (_, _, _, Mo, cno, clo, to, fdo) = ROWS[i], ROWS[i+1]
    for atk in ("pre", "coll"):
        r = 1 - 2 ** (mp_log2(n, Mo, fdo, atk, 40) - mp_log2(n, Mj, fdj, atk, 40))
        print(f"  {v} {atk:5s}: {100*r:5.1f}%")
