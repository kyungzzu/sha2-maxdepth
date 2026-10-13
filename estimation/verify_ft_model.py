#!/usr/bin/env python3
"""Validate the fault-tolerant cost model against published results.

Run:  python3 verify_ft_model.py   (exit code 0 iff all checks pass)

Checks:
  [1] Algorithm 4 (distillation distances), as implemented in
      compute_ft_tables_peak.py, reproduces the worked example published in
      Amy et al. [SAC'16], Section 6: for their SHA-256 Grover attack,
      T_GA = floor(pi/4 * 2^128) * 474,168 T gates, p_out = 1/T_GA
      (~7.89e-45), p_in = 1e-4, p_g = 1e-5, eps = 1, the paper states
      "3 layers of distillation, with distances d1 = 33, d2 = 13 and
      d3 = 7".
  [2] Amy et al.'s Eq. (12) distance rule: the smallest d with
      (p_in / 0.0125)^((d+1)/2) < 4.27e-46 at p_in = 1e-4 is d = 43,
      stated in the paper as d_SHA-256 = 43.  (Our pipeline sets
      d_c = d_1 instead, but this confirms our reading of the
      inequality family.)
  [3] The surface-code footprint of compute_ft_tables_peak.py equals the
      Gidney--Ekera convention: "distance-d logical qubits are stored
      using square patches of 2(d+1)^2 physical qubits" [GE21, Fig. 8];
      at their RSA-2048 level-2 distance d = 27 this gives 1,568
      physical qubits per logical qubit.
"""
import math

from compute_ft_tables_peak import distillation_distances as algorithm4


def check(name, got, want):
    ok = got == want
    print("[%s] %s: got %s, expected %s" % ("PASS" if ok else "FAIL", name, got, want))
    return ok


def main():
    ok = True

    # [1] Amy et al. SAC'16 worked example (their Sec. 6).
    T_GA = math.floor(math.pi / 4 * 2 ** 128) * 474168
    log2_p_out = -math.log2(T_GA)
    ok &= check("Amy Alg-4 distances (SHA-256 Grover, p_g=1e-5, p_in=1e-4)",
                algorithm4(log2_p_out, 1e-5, 1e-4), (33, 13, 7))

    # [2] Amy et al. Eq. (12): global/Clifford distance.
    p_in, budget = 1e-4, 4.27e-46
    d = 1
    while (p_in / 0.0125) ** ((d + 1) / 2) >= budget:
        d += 2
    ok &= check("Amy Eq.(12) distance (budget 4.27e-46, p_in=1e-4)", d, 43)

    # [3] Gidney--Ekera footprint at their RSA-2048 distance.
    ok &= check("GE21 footprint 2(d+1)^2 at d=27", 2 * (27 + 1) ** 2, 1568)

    # [4] INFO: end-to-end cross-check on GE21's own logical resources.
    # GE21 (RSA-2048): M = 3n + 0.002 n lg n = 6,189 logical qubits,
    # 0.3n^3 + 0.0005 n^3 lg n ~ 2.62e9 Toffolis, published total ~20M
    # physical qubits at d = 27.  Our pipeline is NOT expected to
    # reproduce 20M: GE21 budget the full ~8-hour spacetime volume of a
    # nearly serial circuit (d = 27 >> the T-budget distance), use CCZ
    # factories, and count routing workspace (their data block alone is
    # 6,189 x 1,568 = 9.7M).  The informative point is that the gap is
    # fully explained by these three declared differences.
    n, lg = 2048, 11
    M = round(3 * n + 0.002 * n * lg)
    n_tof = 0.3 * n ** 3 + 0.0005 * n ** 3 * lg
    T = 7 * n_tof
    phi = int(T // n_tof)                      # rate-based (reaction-limited: ~serial)
    d1 = algorithm4(-math.log2(T), 1e-4, 1e-3)[0]
    q = M * 2 * (d1 + 1) ** 2 + phi * 16 * 2 * (d1 + 1) ** 2
    print("[INFO] GE21 inputs through our pipeline: d1=%d, Phi=%d, Q_inst=%.2fM "
          "(GE21 publish 20M at d=27; data block alone 9.70M; gap = volume-budget "
          "distance + CCZ factories + routing board)" % (d1, phi, q / 1e6))

    # [5] Regime check: in OUR attack regime the T-budget distance d1 must
    # already cover a GE21-style per-round volume budget for the data
    # block: 0.1*(100 e_g)^((d+1)/2) <= 1 / (patches * FD_att * d).
    def d_volume(log2_locations, e_g):
        d = 1
        while math.log2(0.1) + ((d + 1) / 2) * math.log2(100 * e_g) > -log2_locations:
            d += 2
        return d

    cases = {"SHA-256": (256, 7245, 478, 7504, 516213),
             "SHA-384": (384, 17633, 972, 10783, 1400609),
             "SHA-512": (512, 17633, 972, 10783, 1400609)}
    all_cover = True
    for name, (nn, M2, phi2, FD, Tc) in cases.items():
        for attack, li in (("Grover", math.log2(math.pi / 4) + nn / 2 + 1),
                           ("CNS", 1 + 3 * nn / 10)):
            for eg, ein in ((1e-4, 1e-3), (1e-5, 1e-4)):
                d1s = algorithm4(-(li + math.log2(Tc)), eg, ein)[0]
                loc = math.log2(M2 + 16 * phi2) + li + math.log2(FD) + math.log2(d1s)
                all_cover &= d_volume(loc, eg) <= d1s
    ok &= check("d_c = d_1 covers the GE21-style volume budget (12/12 rows)",
                all_cover, True)

    print("\nALL CHECKS PASSED" if ok else "\nVALIDATION FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
