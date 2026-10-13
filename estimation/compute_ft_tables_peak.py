#!/usr/bin/env python3
"""Reproduce Tables 11 (surface code) and 12 (qLDPC) of the paper.

The factory count is the measured peak T-layer demand (478 for SHA-256,
972 for SHA-384/512), under the component-level model stated in Section 4.2
of the paper.

Provisioning model
------------------
* The fully decomposed circuit is scheduled ASAP in T layers.
* A factory supplies one magic state per distillation round.
* One T layer is consumed per round.
* No inter-layer magic-state buffer and no T-layer stalls are allowed.

Under these assumptions, the smallest factory count for which no T-layer of
this schedule stalls is

    Phi = ceil(max_l T_width(l) / factory_yield_per_round).

The measured maxima are 478 for SHA-256 and 972 for SHA-384/512.  Run with
``--remeasure`` to rebuild the ProjectQ circuits through ``compute_phi.py``
and check these values.  Without that option this script has no dependency on
ProjectQ and finishes immediately.

"""

import argparse
import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple


MAXDEPTH_LOG2 = 40.0
FACTORY_YIELD_PER_ROUND = 1


@dataclass(frozen=True)
class HashResources:
    n: int
    logical_qubits: int
    full_depth: int
    t_count: int
    t_depth: int
    peak_t_width: int


HASHES: Dict[str, HashResources] = {
    "SHA-256": HashResources(256, 7245, 7504, 516213, 3207, 478),
    "SHA-384": HashResources(384, 17633, 10783, 1400609, 4647, 972),
    "SHA-512": HashResources(512, 17633, 10783, 1400609, 4647, 972),
}

SURFACE_SCENARIOS = {
    "conservative": {"e_g": 1e-4, "e_in": 1e-3},
    "optimistic": {"e_g": 1e-5, "e_in": 1e-4},
}

QLDPC_SCENARIOS = {
    "conservative": {"per_logical": 101.3, "factory": 8694},
    "optimistic": {"per_logical": 61.4, "factory": 2128},
}


@dataclass(frozen=True)
class Estimate:
    attack: str
    hash_name: str
    phi: int
    log2_s_column: float
    log2_multiplicity: float
    distances: Tuple[int, ...]
    d_c: int
    surface_q_instance: float
    surface_log2_total: float
    qldpc_q_instance: float
    qldpc_log2_total: float
    scenario: str


def factory_count(peak_t_width: int, yield_per_round: int) -> int:
    """Minimum factory count for a no-buffer, no-stall T-layer schedule."""
    if peak_t_width < 0:
        raise ValueError("peak T width must be nonnegative")
    if yield_per_round <= 0:
        raise ValueError("factory yield must be positive")
    return (peak_t_width + yield_per_round - 1) // yield_per_round


def attack_log2_iterations(attack: str, n: int) -> float:
    """Log2 oracle iterations entering T_attack and FD_attack."""
    if attack == "Grover":
        return math.log2(math.pi / 4.0) + n / 2.0 + 1.0
    if attack == "CNS":
        return 1.0 + 3.0 * n / 10.0
    raise ValueError("unknown attack: %s" % attack)


def parallelization_logs(attack: str, h: HashResources) -> Tuple[float, float]:
    """Return (log2 multiplicity, log2 S printed in Tables 11-12)."""
    log2_i = attack_log2_iterations(attack, h.n)
    log2_fd_attack = log2_i + math.log2(h.full_depth)

    if attack == "Grover":
        log2_s = log2_fd_attack - MAXDEPTH_LOG2
        return 2.0 * log2_s, log2_s

    # Table-10-consistent CNS multiplicity:
    # M_p/M = 2^(2 log2(S10) - (n/6)/5), where
    # S10 = (pi/2) * 2^(2n/5) * FD / MAXDEPTH.
    s = h.n / 6.0
    log2_s10 = (math.log2(math.pi / 2.0) + 2.0 * h.n / 5.0
                 + math.log2(h.full_depth) - MAXDEPTH_LOG2)
    log2_multiplicity = 2.0 * log2_s10 - s / 5.0
    log2_s_column = (log2_multiplicity - s) / 2.0
    return log2_multiplicity, log2_s_column


def distillation_distances(log2_p_out: float, e_g: float, e_in: float,
                           eps: float = 1.0) -> Tuple[int, ...]:
    """Amy et al. Algorithm 4 concatenated 15-to-1 distances."""
    distances: List[int] = []
    log2_p = log2_p_out
    while True:
        target = log2_p + math.log2(eps / (1.0 + eps))
        d = 1
        while True:
            lhs = (math.log2(192.0 * d)
                   + ((d + 1.0) / 2.0) * math.log2(100.0 * e_g))
            if lhs < target:
                break
            d += 2
        distances.append(d)
        log2_p = (log2_p - math.log2(35.0 * (1.0 + eps))) / 3.0
        if 2.0 ** log2_p > e_in:
            return tuple(distances)


def estimate_rows() -> Iterable[Estimate]:
    for attack in ("Grover", "CNS"):
        for hash_name, h in HASHES.items():
            phi = factory_count(h.peak_t_width, FACTORY_YIELD_PER_ROUND)
            log2_mult, log2_s = parallelization_logs(attack, h)
            log2_t_attack = attack_log2_iterations(attack, h.n) + math.log2(h.t_count)

            for scenario in ("conservative", "optimistic"):
                sc = SURFACE_SCENARIOS[scenario]
                distances = distillation_distances(
                    -log2_t_attack, sc["e_g"], sc["e_in"])
                d_c = distances[0]
                patch = 2 * (d_c + 1) ** 2
                surface_q = h.logical_qubits * patch + phi * 16 * patch

                ql = QLDPC_SCENARIOS[scenario]
                qldpc_q = (h.logical_qubits * ql["per_logical"]
                           + phi * ql["factory"])

                yield Estimate(
                    attack=attack,
                    hash_name=hash_name,
                    phi=phi,
                    log2_s_column=log2_s,
                    log2_multiplicity=log2_mult,
                    distances=distances,
                    d_c=d_c,
                    surface_q_instance=surface_q,
                    surface_log2_total=log2_mult + math.log2(surface_q),
                    qldpc_q_instance=qldpc_q,
                    qldpc_log2_total=log2_mult + math.log2(qldpc_q),
                    scenario=scenario,
                )


def verify_inputs(remeasure: bool) -> None:
    for name, h in HASHES.items():
        mean = h.t_count / h.t_depth
        phi = factory_count(h.peak_t_width, FACTORY_YIELD_PER_ROUND)
        assert h.peak_t_width >= mean
        assert phi * FACTORY_YIELD_PER_ROUND >= h.peak_t_width
        assert ((phi - 1) * FACTORY_YIELD_PER_ROUND
                < h.peak_t_width or phi == 0)

    # Published worked example of Amy et al.: distances {33, 13, 7}.
    t_ga = math.floor(math.pi / 4.0 * 2 ** 128) * 474168
    assert distillation_distances(-math.log2(t_ga), 1e-5, 1e-4) == (33, 13, 7)

    if remeasure:
        from compute_phi import measure
        for variant, expected in (("256", 478), ("384", 972), ("512", 972)):
            measured = measure(variant)
            if measured != expected:
                raise AssertionError(
                    "SHA-%s peak mismatch: measured %d, expected %d"
                    % (variant, measured, expected))


def scientific(x: float) -> str:
    exponent = math.floor(math.log10(x))
    return "%.2f x 10^%d" % (x / 10 ** exponent, exponent)


def print_demand_summary() -> None:
    print("Magic-state provisioning (one state/factory/round; no buffer or stalls)")
    print("-" * 79)
    print("Hash       T-count  T-depth      mean      peak   Phi")
    for name, h in HASHES.items():
        phi = factory_count(h.peak_t_width, FACTORY_YIELD_PER_ROUND)
        print("%-8s %10d %8d %9.2f %9d %5d" % (
            name, h.t_count, h.t_depth, h.t_count / h.t_depth,
            h.peak_t_width, phi))
    print()


def print_estimates(rows: List[Estimate]) -> None:
    print("Tables 11-12: surface-code and qLDPC estimates, Phi = 478 / 972 (MAXDEPTH = 2^40)")
    print("-" * 118)
    for attack in ("Grover", "CNS"):
        for hash_name in HASHES:
            pair = [r for r in rows
                    if r.attack == attack and r.hash_name == hash_name]
            for r in pair:
                tag = "%s %-7s %-8s" % (r.scenario[:4], attack, hash_name)
                print("%s Phi=%3d log2S=%6.2f dist=%-13s d_c=%2d "
                      "SC(inst=%s,total=2^%.1f=10^%.1f) "
                      "qLDPC(inst=%s,total=2^%.1f=10^%.1f)" % (
                          tag, r.phi, r.log2_s_column,
                          "{" + ",".join(map(str, r.distances)) + "}", r.d_c,
                          scientific(r.surface_q_instance),
                          r.surface_log2_total,
                          r.surface_log2_total * math.log10(2.0),
                          scientific(r.qldpc_q_instance),
                          r.qldpc_log2_total,
                          r.qldpc_log2_total * math.log10(2.0)))
    print()


def print_reduction_summary(rows: List[Estimate]) -> None:
    ratios = [r.surface_q_instance / r.qldpc_q_instance for r in rows]
    sha256 = [r.surface_q_instance / r.qldpc_q_instance for r in rows
              if r.hash_name == "SHA-256"]
    print("Surface-code / qLDPC per-instance ratio (counted components, published factory parameters)")
    print("  all rows:  %.2f to %.2f" % (min(ratios), max(ratios)))
    print("  SHA-256:   %.2f to %.2f" % (min(sha256), max(sha256)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--remeasure", action="store_true",
        help="rebuild all ProjectQ circuits and verify the stored T-layer peaks")
    args = parser.parse_args()

    verify_inputs(args.remeasure)
    rows = list(estimate_rows())
    print_demand_summary()
    print_estimates(rows)
    print_reduction_summary(rows)
    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
