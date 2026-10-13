# Measure the magic-state demand per T-layer of the decomposed SHA-256/384/512
# circuits in ../implementation (ASAP T-layer schedule, Section 4.2).
# The peak (max over T-layers of the number of T/Tdag gates) is the factory
# count Phi used in Tables 11-12: 478 for SHA-256 and 972 for SHA-384/512.
# With one T-layer per distillation round and one magic state per factory per
# round, Phi = peak supplies the busiest T-layer.
#
# T-layer model (standard T-depth convention):
#   - a T/Tdag gate on qubit q enters layer depth[q]+1 and advances depth[q]
#   - a multi-qubit gate synchronizes the T-layer index of all its qubits
#     (dependencies propagate through Cliffords)
#   - single-qubit Cliffords are free
#
# Usage:  python3 compute_phi.py 256   (or 384 / 512)
#         python3 compute_phi.py all
#
# Output: T-count, number of T-layers, peak / mean / median T gates per layer.

import os
import sys
import statistics
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "implementation"))

from projectq import MainEngine
from projectq.cengines import BasicEngine
from projectq.ops import T, Tdag
import projectq.setups.default


class TLayerTracker(BasicEngine):
    """Track the T-layer schedule and per-layer T-gate counts."""

    def __init__(self):
        super().__init__()
        self.depth = {}      # qubit id -> current T-layer index
        self.width = {}      # T-layer index -> number of T gates
        self.max_layer = 0
        self.t_count = 0

    def is_available(self, cmd):
        return True

    def receive(self, cmds):
        for cmd in cmds:
            ids = [q.id for q in cmd.control_qubits] + \
                  [q.id for qr in cmd.qubits for q in qr]
            g = cmd.gate
            if g == T or g == Tdag:
                q = ids[0]
                lv = self.depth.get(q, 0) + 1
                self.depth[q] = lv
                self.width[lv] = self.width.get(lv, 0) + 1
                self.t_count += 1
                if lv > self.max_layer:
                    self.max_layer = lv
            elif len(ids) >= 2:
                mx = max(self.depth.get(i, 0) for i in ids)
                for i in ids:
                    self.depth[i] = mx


def measure(variant):
    if variant == "256":
        import sha256 as m
        build = m.sha256
    elif variant == "384":
        import sha384 as m
        build = m.sha384
    elif variant == "512":
        import sha512 as m
        build = m.sha512
    else:
        raise ValueError(variant)
    m.TD = 1                     # AMMR13 decomposition (7 T per Toffoli)
    m.resource_check = 1
    if hasattr(m, "depth_profile"):
        m.depth_profile = 0

    tracker = TLayerTracker()
    # Stream the circuit through ProjectQ's default engine list -- the same
    # pipeline behind the ResourceCounter runs of Table 8 -- so the counted
    # gate stream is identical to the reported resource estimates.
    eng = MainEngine(backend=tracker,
                     engine_list=projectq.setups.default.get_engine_list())
    build(eng)
    eng.flush()

    widths = list(tracker.width.values())
    peak = max(widths) if widths else 0
    print("=" * 62)
    print("SHA-%s  T-layer schedule (AMMR13-decomposed, ASAP)" % variant)
    print("=" * 62)
    print("  T-count                 = %d" % tracker.t_count)
    print("  # T-layers (T-depth)    = %d" % tracker.max_layer)
    print("  peak T per layer        = %d" % peak)
    print("  mean T per layer        = %.1f" % (tracker.t_count / max(tracker.max_layer, 1)))
    print("  median T per layer      = %.1f" % statistics.median(widths))
    print("  layers >= 0.9 * peak    = %d" % sum(1 for x in widths if x >= 0.9 * peak))
    return peak


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    variants = ["256", "384", "512"] if arg == "all" else [arg]
    phis = {}
    for v in variants:
        phis[v] = measure(v)
    print()
    for v, p in phis.items():
        print("peak T per layer (SHA-%s) = %d" % (v, p))
