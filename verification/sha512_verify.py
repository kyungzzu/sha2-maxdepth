# SHA-512 Quantum Circuit (Depth-Optimized)
#
# Implements a quantum circuit for SHA-512 using ProjectQ.
#
# Usage:
#   python sha512_verify.py              # Resource estimation (default)
#   python sha512_verify.py verify       # NIST test-vector digest check
#   python sha512_verify.py reusecheck   # digest check + |0> check at each register reuse
#   python sha512_verify.py simulate     # Functional simulation
#
# Dependencies: pip install projectq

from projectq import MainEngine
from projectq.ops import H, CNOT, Measure, Toffoli, X, All, Swap, Z, T, Tdag, S, Tdagger, Sdag
from projectq.backends import CircuitDrawer, ResourceCounter, CommandPrinter, ClassicalSimulator
from projectq.meta import Loop, Compute, Uncompute, Control, Dagger
from math import e, floor, ceil, log2

# Toffoli decomposition mode:
#   0 = native ProjectQ Toffoli gate (for simulation)
#   1 = T-gate decomposition, 7 T-gates per Toffoli (for resource estimation)
TD = 1

# Resource counting mode:
#   1 = skip mid-circuit measurements (faster resource estimation)
#   0 = full simulation with actual measurements
resource_check = 1

an = []
share1 = []
share2 = []


def print_hex(eng, b, len):
    All(Measure) | b
    print('0x', end='')
    change_hex(eng, b, len)
    print('\n')


# --- Verification helpers (added for NIST test-vector verification) ---
verify_mode = 0
collected_words = []

# `ancilla_check` makes reusecheck mode read every register that the circuit
# reuses, at the moment it is reused, and record whether it is |0>.
ancilla_check = 0
reuse_checks = {}
reuse_failures = []
reuse_qubits = 0


def check_clean(eng, regs, where):
    """Record whether all qubits in `regs` read 0 just before they are reused."""
    global reuse_qubits
    if not ancilla_check:
        return
    qubits = list(_qubits(regs))
    if not qubits:
        return
    eng.flush()
    if any(eng.backend.read_bit(q) for q in qubits):
        reuse_failures.append(where)
        return
    reuse_checks[where] = reuse_checks.get(where, 0) + 1
    reuse_qubits += len(qubits)


def _qubits(regs):
    """Yield the individual qubits of a (possibly nested) list of registers."""
    for r in regs:
        if hasattr(r, "id"):
            yield r
        else:
            yield from _qubits(r)


def measure_word(eng, reg, nbits):
    """Measure an nbit register (LSB-first qubit order) and return its int value."""
    All(Measure) | reg
    val = 0
    for i in range(nbits):
        if int(reg[i]):
            val |= (1 << i)
    return val


def change_hex(eng, qubits, len):

    num_groups = len // 4
    for i in reversed(range(num_groups)):
        temp = 0
        idx = 4 * i
        if idx + 3 < len:
            temp = temp + int(qubits[idx + 3]) * 8
        if idx + 2 < len:
            temp = temp + int(qubits[idx + 2]) * 4
        if idx + 1 < len:
            temp = temp + int(qubits[idx + 1]) * 2
        if idx < len:
            temp = temp + int(qubits[idx])

        temp = hex(temp)
        y = temp.replace("0x", "")
        print(y, end='')


def w(n):
    return n - sum(int(floor(n / (pow(2, i)))) for i in range(1, int(log2(n)) + 1))


def l(n, t):
    return int(floor(n / (pow(2, t))))


def quantum_and(a, b, c, ancilla):
    H | c
    CNOT | (b, ancilla)
    CNOT | (c, a)
    CNOT | (c, b)
    CNOT | (a, ancilla)
    Tdag | a
    Tdag | b
    T | c
    T | ancilla
    CNOT | (a, ancilla)
    CNOT | (c, b)
    CNOT | (c, a)
    CNOT | (b, ancilla)
    H | c
    S | c


def quantum_and_dag(a, b, c):
    H | b
    H | c
    Measure | c
    if (int(c) or resource_check == 1):
        CNOT | (a, b)
        X | c
    H | b


def toffoli_gate(a, b, c, ancilla=0, mode=True):
    """Apply a Toffoli (CCNOT) gate on target c, controlled by a and b.

    Decomposition is selected by the global TD flag:
      TD=0: native Toffoli gate (simulation only)
      TD=1: T-gate decomposition (7 T-gates, depth-optimal for resource estimation)
      TD=2: quantum AND gate (forward) or quantum AND dagger (inverse, mode=False)

    Args:
        a, b: control qubits
        c:    target qubit
        ancilla: ancilla qubit (required only when TD=2)
        mode: True for forward AND, False for inverse AND (TD=2 only)
    """
    if (TD == 1):
        Tdag | a
        Tdag | b
        H | c
        CNOT | (c, a)
        T | a
        CNOT | (b, c)
        CNOT | (b, a)
        T | c
        Tdag | a
        CNOT | (b, c)
        CNOT | (c, a)
        T | a
        Tdag | c
        CNOT | (b, a)
        H | c
    elif (TD == 2):
        if mode:
            quantum_and(a, b, c, ancilla)
        else:
            quantum_and_dag(a, b, c)
    else:
        Toffoli | (a, b, c)


def outDraper(eng, a, b, ancillas, output=0):
    n = len(a)

    if output != 0:
        z = output[:n]
    else:
        z = eng.allocate_qureg(n)
    length = n - 1 - w(n - 1) - floor(log2(n - 1))
    ancilla = ancillas[:length]
    and_len = n - 1
    and_idx = 0
    tmp_len = (n - 1) - w(n - 1)
    if TD == 2:
        and_ancilla = ancillas[length:length + and_len]
        tmp_ancilla = ancillas[length + and_len:]
    else:
        and_ancilla = 0
        tmp_ancilla = 0
    tmp_idx = 0


    for i in range(n - 1):
        if TD == 2:
            toffoli_gate(a[i], b[i], z[i + 1], and_ancilla[and_idx])
        else:
            toffoli_gate(a[i], b[i], z[i + 1])
        and_idx += 1
    for i in range(1, n - 1):
        CNOT | (a[i], b[i])
    CNOT | (a[n - 1], z[n - 1])
    CNOT | (b[n - 1], z[n - 1])


    idx = 0
    tmp = 0
    and_idx = 0
    for t in range(1, int(log2(n - 1))):
        pre = tmp
        for m in range(1, l(n - 1, t)):
            if t == 1:
                if TD == 2:
                    toffoli_gate(b[2 * m], b[2 * m + 1], ancilla[idx], and_ancilla[and_idx])
                else:
                    toffoli_gate(b[2 * m], b[2 * m + 1], ancilla[idx])
            else:
                if TD == 2:
                    toffoli_gate(ancilla[pre - 1 + 2 * m], ancilla[pre - 1 + 2 * m + 1], ancilla[idx],
                                 and_ancilla[and_idx])
                else:
                    toffoli_gate(ancilla[pre - 1 + 2 * m], ancilla[pre - 1 + 2 * m + 1], ancilla[idx])
            if m == 1:
                tmp = idx
            idx += 1
            and_idx += 1


    pre = 0
    idx = 0
    for t in range(1, int(log2(n - 1)) + 1):
        for m in range(l(n - 1, t)):
            if t == 1:
                if TD == 2:
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], b[2 * m + 1], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx])
                    CNOT | (tmp_ancilla[tmp_idx], z[int(pow(2, t) * (m + 1))])
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], b[2 * m + 1], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx], False)
                else:
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], b[2 * m + 1], z[int(pow(2, t) * (m + 1))])

            else:
                if TD == 2:
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], ancilla[idx + 2 * m], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx])
                    CNOT | (tmp_ancilla[tmp_idx], z[int(pow(2, t) * (m + 1))])
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], ancilla[idx + 2 * m], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx], False)
                else:
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], ancilla[idx + 2 * m],
                                 z[int(pow(2, t) * (m + 1))])
            and_idx = (and_idx + 1) % and_len
            tmp_idx += 1
        if t != 1:
            pre = pre + l(n - 1, t - 1) - 1
            idx = pre


    if int(log2(n - 1)) - 1 == int(log2(2 * (n - 1) / 3)):
        iter = l(n - 1, int(log2(n - 1)) - 1) - 1
    else:
        iter = 0
    pre = 0
    tmp_idx = 0
    for t in range(int(log2(2 * (n - 1) / 3)), 0, -1):
        for m in range(1, l((n - 1 - pow(2, t - 1)), t) + 1):
            if t == 1:
                if TD == 2:
                    toffoli_gate(z[int(pow(2, t) * m)], b[2 * m], tmp_ancilla[tmp_idx], and_ancilla[and_idx])
                    CNOT | (tmp_ancilla[tmp_idx], z[int(pow(2, t) * m + pow(2, t - 1))])
                    toffoli_gate(z[int(pow(2, t) * m)], b[2 * m], tmp_ancilla[tmp_idx], and_ancilla[and_idx], False)
                else:
                    toffoli_gate(z[int(pow(2, t) * m)], b[2 * m], z[int(pow(2, t) * m + pow(2, t - 1))])
            else:
                if m == 1:
                    iter += l(n - 1, t - 1) - 1
                    pre = length - 1 - iter
                if TD == 2:
                    toffoli_gate(z[int(pow(2, t) * m)], ancilla[pre + 2 * m], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx])
                    CNOT | (tmp_ancilla[tmp_idx], z[int(pow(2, t) * m + pow(2, t - 1))])
                    toffoli_gate(z[int(pow(2, t) * m)], ancilla[pre + 2 * m], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx], False)
                else:
                    toffoli_gate(z[int(pow(2, t) * m)], ancilla[pre + 2 * m], z[int(pow(2, t) * m + pow(2, t - 1))])

            and_idx = (and_idx + 1) % and_len
            tmp_idx += 1


    pre = 0
    iter = l(n - 1, int(log2(n - 1)) - 1) - 1
    iter2 = 0
    idx = 0
    and_idx = 0
    for t in reversed(range(1, int(log2(n - 1)))):
        for m in range(1, l(n - 1, t)):
            if t == 1:
                if TD == 2:
                    toffoli_gate(b[2 * m], b[2 * m + 1], ancilla[m - t], and_ancilla[and_idx], False)
                else:
                    toffoli_gate(b[2 * m], b[2 * m + 1], ancilla[m - t])
            else:
                if m == 1:
                    iter += l(n - 1, t - 1) - 1
                    pre = length - iter
                    iter2 += (l(n - 1, t) - 1)
                    idx = length - iter2
                if TD == 2:
                    toffoli_gate(ancilla[pre - 1 + 2 * m], ancilla[pre - 1 + 2 * m + 1], ancilla[idx - 1 + m],
                                 and_ancilla[and_idx], False)
                else:
                    toffoli_gate(ancilla[pre - 1 + 2 * m], ancilla[pre - 1 + 2 * m + 1], ancilla[idx - 1 + m])
            and_idx += 1


    for i in range(n - 1):
        CNOT | (b[i], z[i])
    CNOT | (a[0], z[0])
    for i in range(1, n - 1):
        CNOT | (a[i], b[i])

    return z


def outDraper_dag(eng, a, b, ancillas, output):
    n = len(a)
    z = output[:n]
    length = n - 1 - w(n - 1) - floor(log2(n - 1))

    ancilla = ancillas[:length]
    and_len = n - 1

    and_ancilla = ancillas[length:length + and_len]
    and_idx = 0
    tmp_len = (n - 1) - w(n - 1)

    tmp_ancilla = ancillas[length + and_len:]
    tmp_idx = 0


    for i in range(1, n - 1):
        CNOT | (a[i], b[i])
    CNOT | (a[0], z[0])
    for i in range(n - 1):
        CNOT | (b[i], z[i])


    idx = 0
    tmp = 0
    for t in range(1, int(log2(n - 1))):
        pre = tmp
        for m in range(1, l(n - 1, t)):
            if t == 1:
                if TD == 2:
                    toffoli_gate(b[2 * m], b[2 * m + 1], ancilla[idx], and_ancilla[and_idx])
                else:
                    toffoli_gate(b[2 * m], b[2 * m + 1], ancilla[idx])
            else:

                if TD == 2:
                    toffoli_gate(ancilla[pre - 1 + 2 * m], ancilla[pre - 1 + 2 * m + 1], ancilla[idx],
                                 and_ancilla[and_idx])
                else:
                    toffoli_gate(ancilla[pre - 1 + 2 * m], ancilla[pre - 1 + 2 * m + 1], ancilla[idx])
            if m == 1:
                tmp = idx
            idx += 1
            and_idx += 1


    pre = 0
    tmp_idx = 0
    for t in reversed(range(int(log2(2 * (n - 1) / 3)), 0, -1)):
        idx = pre
        for m in range(1, l((n - 1 - pow(2, t - 1)), t) + 1):
            if t == 1:
                if TD == 2:
                    toffoli_gate(z[int(pow(2, t) * m)], b[2 * m], tmp_ancilla[tmp_idx], and_ancilla[and_idx])
                    CNOT | (tmp_ancilla[tmp_idx], z[int(pow(2, t) * m + pow(2, t - 1))])
                    toffoli_gate(z[int(pow(2, t) * m)], b[2 * m], tmp_ancilla[tmp_idx], and_ancilla[and_idx], False)
                else:
                    toffoli_gate(z[int(pow(2, t) * m)], b[2 * m], z[int(pow(2, t) * m + pow(2, t - 1))])
            else:
                if TD == 2:
                    toffoli_gate(z[int(pow(2, t) * m)], ancilla[idx - 1 + 2 * m], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx])
                    CNOT | (tmp_ancilla[tmp_idx], z[int(pow(2, t) * m + pow(2, t - 1))])
                    toffoli_gate(z[int(pow(2, t) * m)], ancilla[idx - 1 + 2 * m], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx], False)
                else:
                    toffoli_gate(z[int(pow(2, t) * m)], ancilla[idx - 1 + 2 * m], z[int(pow(2, t) * m + pow(2, t - 1))])
                if m == 1:
                    pre += l(n - 1, t - 1) - 1
            and_idx = (and_idx + 1) % and_len
            tmp_idx += 1


    pre = 0
    idx_t = int(log2(n - 1))
    iter = 0
    tmp_idx = 0
    for t in reversed(range(1, int(log2(n - 1)) + 1)):
        for m in range(l(n - 1, t)):
            if t == 1:
                if TD == 2:
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], b[2 * m + 1], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx])
                    CNOT | (tmp_ancilla[tmp_idx], z[int(pow(2, t) * (m + 1))])
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], b[2 * m + 1], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx], False)
                else:
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], b[2 * m + 1], z[int(pow(2, t) * (m + 1))])
            else:
                if m == 0:
                    iter += l(n - 1, idx_t - 1) - 1
                    pre = length - iter
                    idx_t -= 1

                if TD == 2:
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], ancilla[pre - 1 + 2 * m + 1],
                                 tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx])
                    CNOT | (tmp_ancilla[tmp_idx], z[int(pow(2, t) * (m + 1))])
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], ancilla[pre - 1 + 2 * m + 1],
                                 tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx], False)
                else:
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], ancilla[pre - 1 + 2 * m + 1],
                                 z[int(pow(2, t) * (m + 1))])

            and_idx = (and_idx + 1) % and_len
            tmp_idx += 1


    pre = 0
    iter = l(n - 1, int(log2(n - 1)) - 1) - 1
    iter2 = 0
    idx = 0
    and_idx = 0
    for t in reversed(range(1, int(log2(n - 1)))):
        for m in range(1, l(n - 1, t)):
            if t == 1:
                if TD == 2:
                    toffoli_gate(b[2 * m], b[2 * m + 1], ancilla[m - t], and_ancilla[and_idx], False)
                else:
                    toffoli_gate(b[2 * m], b[2 * m + 1], ancilla[m - t])

            else:
                if m == 1:
                    iter += l(n - 1, t - 1) - 1
                    pre = length - iter
                    iter2 += (l(n - 1, t) - 1)
                    idx = length - iter2

                if TD == 2:
                    toffoli_gate(ancilla[pre - 1 + 2 * m], ancilla[pre - 1 + 2 * m + 1], ancilla[idx - 1 + m],
                                 and_ancilla[and_idx], False)
                else:
                    toffoli_gate(ancilla[pre - 1 + 2 * m], ancilla[pre - 1 + 2 * m + 1], ancilla[idx - 1 + m])
            and_idx += 1

    and_idx = 0

    CNOT | (b[n - 1], z[n - 1])
    CNOT | (a[n - 1], z[n - 1])
    for i in range(1, n - 1):
        CNOT | (a[i], b[i])
    for i in range(n - 1):
        if TD == 2:
            toffoli_gate(a[i], b[i], z[i + 1], 0, False)
        else:
            toffoli_gate(a[i], b[i], z[i + 1])
        and_idx += 1

    return z


def outDraper_dirty(eng, a, b, ancillas, output=0):
    n = len(a)

    if output != 0:
        z = output[:n]
    else:
        z = eng.allocate_qureg(n)
    length = n - 1 - w(n - 1) - floor(log2(n - 1))
    ancilla = ancillas[:length]
    and_len = n - 1
    and_idx = 0
    tmp_len = (n - 1) - w(n - 1)
    if TD == 2:
        and_ancilla = ancillas[length:length + and_len]
        tmp_ancilla = ancillas[length + and_len:]
    else:
        and_ancilla = 0
        tmp_ancilla = 0
    tmp_idx = 0


    for i in range(n - 1):
        if TD == 2:
            toffoli_gate(a[i], b[i], z[i + 1], and_ancilla[and_idx])
        else:
            toffoli_gate(a[i], b[i], z[i + 1])
        and_idx += 1
    for i in range(1, n - 1):
        CNOT | (a[i], b[i])
    CNOT | (a[n - 1], z[n - 1])
    CNOT | (b[n - 1], z[n - 1])


    idx = 0
    tmp = 0
    and_idx = 0
    for t in range(1, int(log2(n - 1))):
        pre = tmp
        for m in range(1, l(n - 1, t)):
            if t == 1:
                if TD == 2:
                    toffoli_gate(b[2 * m], b[2 * m + 1], ancilla[idx], and_ancilla[and_idx])
                else:
                    toffoli_gate(b[2 * m], b[2 * m + 1], ancilla[idx])
            else:
                if TD == 2:
                    toffoli_gate(ancilla[pre - 1 + 2 * m], ancilla[pre - 1 + 2 * m + 1], ancilla[idx],
                                 and_ancilla[and_idx])
                else:
                    toffoli_gate(ancilla[pre - 1 + 2 * m], ancilla[pre - 1 + 2 * m + 1], ancilla[idx])
            if m == 1:
                tmp = idx
            idx += 1
            and_idx += 1


    pre = 0
    idx = 0
    for t in range(1, int(log2(n - 1)) + 1):
        for m in range(l(n - 1, t)):
            if t == 1:
                if TD == 2:
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], b[2 * m + 1], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx])
                    CNOT | (tmp_ancilla[tmp_idx], z[int(pow(2, t) * (m + 1))])
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], b[2 * m + 1], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx], False)
                else:
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], b[2 * m + 1], z[int(pow(2, t) * (m + 1))])

            else:
                if TD == 2:
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], ancilla[idx + 2 * m], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx])
                    CNOT | (tmp_ancilla[tmp_idx], z[int(pow(2, t) * (m + 1))])
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], ancilla[idx + 2 * m], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx], False)
                else:
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], ancilla[idx + 2 * m],
                                 z[int(pow(2, t) * (m + 1))])
            and_idx = (and_idx + 1) % and_len
            tmp_idx += 1
        if t != 1:
            pre = pre + l(n - 1, t - 1) - 1
            idx = pre


    if int(log2(n - 1)) - 1 == int(log2(2 * (n - 1) / 3)):
        iter = l(n - 1, int(log2(n - 1)) - 1) - 1
    else:
        iter = 0
    pre = 0
    tmp_idx = 0
    for t in range(int(log2(2 * (n - 1) / 3)), 0, -1):
        for m in range(1, l((n - 1 - pow(2, t - 1)), t) + 1):
            if t == 1:
                if TD == 2:
                    toffoli_gate(z[int(pow(2, t) * m)], b[2 * m], tmp_ancilla[tmp_idx], and_ancilla[and_idx])
                    CNOT | (tmp_ancilla[tmp_idx], z[int(pow(2, t) * m + pow(2, t - 1))])
                    toffoli_gate(z[int(pow(2, t) * m)], b[2 * m], tmp_ancilla[tmp_idx], and_ancilla[and_idx], False)
                else:
                    toffoli_gate(z[int(pow(2, t) * m)], b[2 * m], z[int(pow(2, t) * m + pow(2, t - 1))])
            else:
                if m == 1:
                    iter += l(n - 1, t - 1) - 1
                    pre = length - 1 - iter
                if TD == 2:
                    toffoli_gate(z[int(pow(2, t) * m)], ancilla[pre + 2 * m], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx])
                    CNOT | (tmp_ancilla[tmp_idx], z[int(pow(2, t) * m + pow(2, t - 1))])
                    toffoli_gate(z[int(pow(2, t) * m)], ancilla[pre + 2 * m], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx], False)
                else:
                    toffoli_gate(z[int(pow(2, t) * m)], ancilla[pre + 2 * m], z[int(pow(2, t) * m + pow(2, t - 1))])

            and_idx = (and_idx + 1) % and_len
            tmp_idx += 1


    for i in range(n - 1):
        CNOT | (b[i], z[i])
    CNOT | (a[0], z[0])
    for i in range(1, n - 1):
        CNOT | (a[i], b[i])

    return z


def deferredAdd(eng, a, b, ancillas, output):
    n = len(a)

    if output != 0:
        z = output[:n]
    else:
        z = eng.allocate_qureg(n)
    length = n - 1 - w(n - 1) - floor(log2(n - 1))
    ancilla = ancillas[:length]
    and_len = n - 1
    and_idx = 0
    tmp_len = (n - 1) - w(n - 1)
    if TD == 2:
        and_ancilla = ancillas[length:length + and_len]
        tmp_ancilla = ancillas[length + and_len:]
    else:
        and_ancilla = 0
        tmp_ancilla = 0
    tmp_idx = 0

    for i in range(1, n - 1):
        CNOT | (a[i], b[i])
    CNOT | (a[0], z[0])
    for i in range(n - 1):
        CNOT | (b[i], z[i])


    pre = 0
    iter = l(n - 1, int(log2(n - 1)) - 1) - 1
    iter2 = 0
    idx = 0
    and_idx = 0
    for t in reversed(range(1, int(log2(n - 1)))):
        for m in range(1, l(n - 1, t)):
            if t == 1:
                if TD == 2:
                    toffoli_gate(b[2 * m], b[2 * m + 1], ancilla[m - t], and_ancilla[and_idx], False)
                else:
                    toffoli_gate(b[2 * m], b[2 * m + 1], ancilla[m - t])
            else:
                if m == 1:
                    iter += l(n - 1, t - 1) - 1
                    pre = length - iter
                    iter2 += (l(n - 1, t) - 1)
                    idx = length - iter2
                if TD == 2:
                    toffoli_gate(ancilla[pre - 1 + 2 * m], ancilla[pre - 1 + 2 * m + 1], ancilla[idx - 1 + m],
                                 and_ancilla[and_idx], False)
                else:
                    toffoli_gate(ancilla[pre - 1 + 2 * m], ancilla[pre - 1 + 2 * m + 1], ancilla[idx - 1 + m])
            and_idx += 1


    for i in range(n - 1):
        CNOT | (b[i], z[i])
    CNOT | (a[0], z[0])
    for i in range(1, n - 1):
        CNOT | (a[i], b[i])

    return z


def outDraper_const_dag(eng, a, b, ancillas, output):
    n = len(b)
    z = output[:n]
    length = n - 1 - w(n - 1) - floor(log2(n - 1))
    ancilla = ancillas[:length]
    and_len = n - 1
    if TD == 2:
        and_ancilla = ancillas[length:length + and_len]
        tmp_ancilla = ancillas[length + and_len:]
    else:
        and_ancilla = 0
        tmp_ancilla = 0


    for i in reversed(range(1, n - 1)):
        if a[i] == '1':
            X | b[i]


    if a[0] == '1':
        X | z[0]


    for i in reversed(range(n - 1)):
        CNOT | (b[i], z[i])


    idx = 0
    tmp = 0
    for t in range(1, int(log2(n - 1))):
        pre = tmp
        for m in range(1, l(n - 1, t)):
            if t == 1:
                if TD == 2:
                    toffoli_gate(b[2 * m], b[2 * m + 1], ancilla[m - t], and_ancilla[idx])
                else:
                    toffoli_gate(b[2 * m], b[2 * m + 1], ancilla[m - t])
            else:
                if TD == 2:
                    toffoli_gate(ancilla[pre - 1 + 2 * m], ancilla[pre - 1 + 2 * m + 1], ancilla[idx],
                                 and_ancilla[idx])
                else:
                    toffoli_gate(ancilla[pre - 1 + 2 * m], ancilla[pre - 1 + 2 * m + 1], ancilla[idx])
            if m == 1:
                tmp = idx
            idx += 1


    c_pre_values = {}
    c_iter = 0
    for t in range(int(log2(2 * (n - 1) / 3)), 0, -1):
        if t != 1:
            for m in range(1, l((n - 1 - pow(2, t - 1)), t) + 1):
                if m == 1:
                    c_iter += l(n - 1, t - 1) - 1
                    c_pre_values[t] = length - 1 - c_iter

    for t in range(1, int(log2(2 * (n - 1) / 3)) + 1):
        pre = c_pre_values.get(t, 0)
        for m in reversed(range(1, l((n - 1 - pow(2, t - 1)), t) + 1)):
            if t == 1:
                if TD == 2:
                    toffoli_gate(z[int(pow(2, t) * m)], b[2 * m], tmp_ancilla[0], and_ancilla[0])
                    CNOT | (tmp_ancilla[0], z[int(pow(2, t) * m + pow(2, t - 1))])
                    toffoli_gate(z[int(pow(2, t) * m)], b[2 * m], tmp_ancilla[0], and_ancilla[0], False)
                else:
                    toffoli_gate(z[int(pow(2, t) * m)], b[2 * m], z[int(pow(2, t) * m + pow(2, t - 1))])
            else:
                if TD == 2:
                    toffoli_gate(z[int(pow(2, t) * m)], ancilla[pre + 2 * m], tmp_ancilla[0], and_ancilla[0])
                    CNOT | (tmp_ancilla[0], z[int(pow(2, t) * m + pow(2, t - 1))])
                    toffoli_gate(z[int(pow(2, t) * m)], ancilla[pre + 2 * m], tmp_ancilla[0], and_ancilla[0], False)
                else:
                    toffoli_gate(z[int(pow(2, t) * m)], ancilla[pre + 2 * m], z[int(pow(2, t) * m + pow(2, t - 1))])


    g_idx_values = {}
    g_pre = 0
    g_idx = 0
    for t in range(1, int(log2(n - 1)) + 1):
        g_idx_values[t] = g_idx
        if t != 1:
            g_pre = g_pre + l(n - 1, t - 1) - 1
            g_idx = g_pre

    for t in reversed(range(1, int(log2(n - 1)) + 1)):
        idx = g_idx_values[t]
        for m in reversed(range(l(n - 1, t))):
            if t == 1:
                if TD == 2:
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], b[2 * m + 1], tmp_ancilla[0], and_ancilla[0])
                    CNOT | (tmp_ancilla[0], z[int(pow(2, t) * (m + 1))])
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], b[2 * m + 1], tmp_ancilla[0], and_ancilla[0],
                                 False)
                else:
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], b[2 * m + 1], z[int(pow(2, t) * (m + 1))])
            else:
                if TD == 2:
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], ancilla[idx + 2 * m], tmp_ancilla[0],
                                 and_ancilla[0])
                    CNOT | (tmp_ancilla[0], z[int(pow(2, t) * (m + 1))])
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], ancilla[idx + 2 * m], tmp_ancilla[0],
                                 and_ancilla[0], False)
                else:
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], ancilla[idx + 2 * m],
                                 z[int(pow(2, t) * (m + 1))])


    p_data = []
    idx = 0
    tmp = 0
    for t in range(1, int(log2(n - 1))):
        pre = tmp
        for m in range(1, l(n - 1, t)):
            if t == 1:
                p_data.append((t, m, idx, None))
            else:
                p_data.append((t, m, idx, pre))
            if m == 1:
                tmp = idx
            idx += 1


    for t, m, idx, pre in reversed(p_data):
        if t == 1:
            if TD == 2:
                toffoli_gate(b[2 * m], b[2 * m + 1], ancilla[idx], and_ancilla[idx])
            else:
                toffoli_gate(b[2 * m], b[2 * m + 1], ancilla[idx])
        else:
            if TD == 2:
                toffoli_gate(ancilla[pre - 1 + 2 * m], ancilla[pre - 1 + 2 * m + 1], ancilla[idx], and_ancilla[idx])
            else:
                toffoli_gate(ancilla[pre - 1 + 2 * m], ancilla[pre - 1 + 2 * m + 1], ancilla[idx])


    CNOT | (b[n - 1], z[n - 1])

    if a[n - 1] == '1':
        X | z[n - 1]

    for i in reversed(range(1, n - 1)):
        if a[i] == '1':
            X | b[i]

    for i in reversed(range(n - 1)):
        if a[i] == '1':
            CNOT | (b[i], z[i + 1])

    return z


def outDraper_const(eng, a, b, ancillas, output=0):
    n = len(b)

    if output != 0:
        z = output[:n]
    else:
        z = eng.allocate_qureg(n)
    length = n - 1 - w(n - 1) - floor(log2(n - 1))
    ancilla = ancillas[:length]
    and_len = n - 1
    and_idx = 0
    tmp_len = (n - 1) - w(n - 1)
    if TD == 2:
        and_ancilla = ancillas[length:length + and_len]
        tmp_ancilla = ancillas[length + and_len:]
    else:
        and_ancilla = 0
        tmp_ancilla = 0
    tmp_idx = 0


    for i in range(n - 1):
        if a[i] == '1':
            CNOT | (b[i], z[i + 1])
        and_idx += 1

    for i in range(1, n - 1):
        if a[i] == '1':
            X | b[i]


    if a[n - 1] == '1':
        X | z[n - 1]
    CNOT | (b[n - 1], z[n - 1])


    idx = 0
    tmp = 0
    and_idx = 0
    for t in range(1, int(log2(n - 1))):
        pre = tmp
        for m in range(1, l(n - 1, t)):
            if t == 1:
                if TD == 2:
                    toffoli_gate(b[2 * m], b[2 * m + 1], ancilla[idx], and_ancilla[and_idx])
                else:
                    toffoli_gate(b[2 * m], b[2 * m + 1], ancilla[idx])
            else:
                if TD == 2:
                    toffoli_gate(ancilla[pre - 1 + 2 * m], ancilla[pre - 1 + 2 * m + 1], ancilla[idx],
                                 and_ancilla[and_idx])
                else:
                    toffoli_gate(ancilla[pre - 1 + 2 * m], ancilla[pre - 1 + 2 * m + 1], ancilla[idx])
            if m == 1:
                tmp = idx
            idx += 1
            and_idx += 1


    pre = 0
    idx = 0
    for t in range(1, int(log2(n - 1)) + 1):
        for m in range(l(n - 1, t)):
            if t == 1:
                if TD == 2:
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], b[2 * m + 1], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx])
                    CNOT | (tmp_ancilla[tmp_idx], z[int(pow(2, t) * (m + 1))])
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], b[2 * m + 1], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx], False)
                else:
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], b[2 * m + 1], z[int(pow(2, t) * (m + 1))])

            else:
                if TD == 2:
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], ancilla[idx + 2 * m], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx])
                    CNOT | (tmp_ancilla[tmp_idx], z[int(pow(2, t) * (m + 1))])
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], ancilla[idx + 2 * m], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx], False)
                else:
                    toffoli_gate(z[int(pow(2, t) * m + pow(2, t - 1))], ancilla[idx + 2 * m],
                                 z[int(pow(2, t) * (m + 1))])
            and_idx = (and_idx + 1) % and_len
            tmp_idx += 1
        if t != 1:
            pre = pre + l(n - 1, t - 1) - 1
            idx = pre


    if int(log2(n - 1)) - 1 == int(log2(2 * (n - 1) / 3)):
        iter = l(n - 1, int(log2(n - 1)) - 1) - 1
    else:
        iter = 0
    pre = 0
    tmp_idx = 0
    for t in range(int(log2(2 * (n - 1) / 3)), 0, -1):
        for m in range(1, l((n - 1 - pow(2, t - 1)), t) + 1):
            if t == 1:
                if TD == 2:
                    toffoli_gate(z[int(pow(2, t) * m)], b[2 * m], tmp_ancilla[tmp_idx], and_ancilla[and_idx])
                    CNOT | (tmp_ancilla[tmp_idx], z[int(pow(2, t) * m + pow(2, t - 1))])
                    toffoli_gate(z[int(pow(2, t) * m)], b[2 * m], tmp_ancilla[tmp_idx], and_ancilla[and_idx], False)
                else:
                    toffoli_gate(z[int(pow(2, t) * m)], b[2 * m], z[int(pow(2, t) * m + pow(2, t - 1))])
            else:
                if m == 1:
                    iter += l(n - 1, t - 1) - 1
                    pre = length - 1 - iter
                if TD == 2:
                    toffoli_gate(z[int(pow(2, t) * m)], ancilla[pre + 2 * m], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx])
                    CNOT | (tmp_ancilla[tmp_idx], z[int(pow(2, t) * m + pow(2, t - 1))])
                    toffoli_gate(z[int(pow(2, t) * m)], ancilla[pre + 2 * m], tmp_ancilla[tmp_idx],
                                 and_ancilla[and_idx],
                                 False)
                else:
                    toffoli_gate(z[int(pow(2, t) * m)], ancilla[pre + 2 * m], z[int(pow(2, t) * m + pow(2, t - 1))])

            and_idx = (and_idx + 1) % and_len
            tmp_idx += 1


    pre = 0
    iter = l(n - 1, int(log2(n - 1)) - 1) - 1
    iter2 = 0
    idx = 0
    and_idx = 0
    for t in reversed(range(1, int(log2(n - 1)))):
        for m in range(1, l(n - 1, t)):
            if t == 1:
                if TD == 2:
                    toffoli_gate(b[2 * m], b[2 * m + 1], ancilla[m - t], and_ancilla[and_idx], False)
                else:
                    toffoli_gate(b[2 * m], b[2 * m + 1], ancilla[m - t])
            else:
                if m == 1:
                    iter += l(n - 1, t - 1) - 1
                    pre = length - iter
                    iter2 += (l(n - 1, t) - 1)
                    idx = length - iter2
                if TD == 2:
                    toffoli_gate(ancilla[pre - 1 + 2 * m], ancilla[pre - 1 + 2 * m + 1], ancilla[idx - 1 + m],
                                 and_ancilla[and_idx], False)
                else:
                    toffoli_gate(ancilla[pre - 1 + 2 * m], ancilla[pre - 1 + 2 * m + 1], ancilla[idx - 1 + m])
            and_idx += 1


    for i in range(n - 1):
        CNOT | (b[i], z[i])

    if a[0] == '1':
        X | z[0]

    for i in range(1, n - 1):
        if a[i] == '1':
            X | b[i]

    return z


def initialize_circuit_and_qubits(input):
    n = 64
    w = []
    for i in range(n):
        tmp = []
        for qb in input:
            if len(qb) == n - 1:
                if i != 0:
                    tmp.append(qb[i - 1])
            else:
                tmp.append(qb[i])
        w.append(tmp)

    return w


def apply_adders_and_handle_carry0(eng, w, input2, ancilla, and_ancilla=0):
    num = 0
    and_idx = 0
    t = 1
    stack = []
    share1 = []
    share2 = []
    flag1 = 1
    flag2 = 1
    while (t):
        n = len(w)
        t = 0
        w_tmp = []

        if (len(w[n - 1]) > 2):

            while (len(w[n - 1]) > 2):
                a = w[n - 1].pop(0)
                b = w[n - 1].pop(0)
                c = w[n - 1].pop(0)
                stack.append([a, b, c, 0, 0, 0])
                modQFA(a, b, c)
                w_tmp.append(c)

            if flag1 == 1:
                flag1 = 0
                share1.append(w_tmp[0])
                w[n - 1].insert(0, w_tmp[0])
                w[n - 1].insert(-1, w_tmp[1])

            else:
                w[n - 1].extend(w_tmp)


        for i in reversed(range(0, n - 1)):
            w_tmp = []
            w_tmp2 = []
            while (len(w[i]) > 2):
                a = w[i].pop(0)
                b = w[i].pop(0)
                c = w[i].pop(0)
                carry = ancilla[num]
                num += 1
                an.append(carry)
                stack.append([a, b, c, carry])
                if TD == 2:
                    QFA(a, b, c, carry, and_ancilla[and_idx])
                else:
                    QFA(a, b, c, carry)
                and_idx += 1
                w_tmp.append(c)
                w_tmp2.append(carry)

            if flag2 == 1:
                share1.append(w_tmp[0])
                share2.append(w_tmp2[0])
                w[i].insert(0, w_tmp[0])
                w[i].insert(-1, w_tmp[1])
                w[i + 1].insert(1, w_tmp2[0])
                w[i + 1].insert(-1, w_tmp2[1])

            else:
                w[i].extend(w_tmp)
                w[i + 1].extend(w_tmp2)

        and_idx = 0

        if flag2 == 1:
            flag2 = 0
            share1.reverse()
            share2.reverse()
            input2.append(share1)
            input2.append(share2)

    return w, stack, input2, num


def apply_adders_and_handle_carry(eng, w, ancilla, and_ancilla):
    and_idx = 0
    num = 0
    t = 1
    stack = []
    flag = 0
    while (t):
        n = len(w)
        t = 0
        w_tmp = []
        if (len(w[n - 1]) > 2):
            while (len(w[n - 1]) > 2):
                a = w[n - 1].pop(0)
                b = w[n - 1].pop(0)
                c = w[n - 1].pop(0)
                stack.append([a, b, c, 0, 0, 0])
                modQFA(a, b, c)
                w_tmp.append(c)

            w[n - 1].extend(w_tmp)

        for i in reversed(range(0, n - 1)):
            w_tmp = []
            w_tmp2 = []
            while (len(w[i]) > 2):
                a = w[i].pop(0)
                b = w[i].pop(0)
                c = w[i].pop(0)
                carry = ancilla[num]
                num += 1
                an.append(carry)
                stack.append([a, b, c, carry])
                if TD == 2:
                    QFA(a, b, c, carry, and_ancilla[and_idx])
                else:
                    QFA(a, b, c, carry)
                and_idx += 1
                w_tmp.append(c)
                w_tmp2.append(carry)

            if flag == 1 and len(w[i]) == 2:
                a = w[i].pop(0)
                b = w[i].pop(0)
                carry = ancilla[num]
                num += 1
                an.append(carry)
                stack.append([a, b, carry])
                if TD == 2:
                    QHA(a, b, carry, and_ancilla[and_idx])
                else:
                    QHA(a, b, carry)
                and_idx += 1
                w_tmp.append(b)
                w_tmp2.append(carry)

            w[i].extend(w_tmp)
            w[i + 1].extend(w_tmp2)

        and_idx = 0
        for i in range(len(w)):
            if (len(w[i]) > 3):
                t += 1
                flag = 1

    and_idx = 0
    t = 1
    while (t):
        n = len(w)
        t = 0
        w_tmp = []
        if (len(w[n - 1]) > 2):
            while (len(w[n - 1]) > 2):
                a = w[n - 1].pop(0)
                b = w[n - 1].pop(0)
                c = w[n - 1].pop(0)
                stack.append([a, b, c, 0, 0, 0])
                modQFA(a, b, c)
                w_tmp.append(c)

            w[n - 1].extend(w_tmp)

        if (len(w[n - 1]) == 2):
            return w, stack

        for i in reversed(range(0, n - 1)):
            w_tmp = []
            w_tmp2 = []
            while (len(w[i]) > 2):
                a = w[i].pop(0)
                b = w[i].pop(0)
                c = w[i].pop(0)
                carry = ancilla[num]
                num += 1
                an.append(carry)
                stack.append([a, b, c, carry])
                if TD == 2:
                    QFA(a, b, c, carry, and_ancilla[and_idx])
                else:
                    QFA(a, b, c, carry)
                and_idx += 1
                w_tmp.append(c)
                w_tmp2.append(carry)

            if len(w[i]) == 2:
                a = w[i].pop(0)
                b = w[i].pop(0)
                carry = ancilla[num]
                num += 1
                an.append(carry)
                stack.append([a, b, carry])
                if TD == 2:
                    QHA(a, b, carry, and_ancilla[and_idx])
                else:
                    QHA(a, b, carry)
                and_idx += 1
                w_tmp.append(b)
                w_tmp2.append(carry)

            w[i].extend(w_tmp)
            w[i + 1].extend(w_tmp2)

        and_idx = 0
        for i in range(len(w)):
            if (len(w[i]) > 2):
                t += 1
    return w, stack


def apply_adders_and_handle_carry1(eng, w, stack, ancilla, num, and_ancilla=0):
    and_idx = 0
    t = 1
    flag = 0

    while (t):
        n = len(w)
        t = 0
        w_tmp = []
        if (len(w[n - 1]) > 2):
            while (len(w[n - 1]) > 2):
                a = w[n - 1].pop(0)
                b = w[n - 1].pop(0)
                c = w[n - 1].pop(0)
                stack.append([a, b, c, 0, 0, 0])
                modQFA(a, b, c)
                w_tmp.append(c)

            w[n - 1].extend(w_tmp)

        for i in reversed(range(0, n - 1)):
            w_tmp = []
            w_tmp2 = []
            while (len(w[i]) > 2):
                a = w[i].pop(0)
                b = w[i].pop(0)
                c = w[i].pop(0)
                carry = ancilla[num]
                num += 1
                an.append(carry)
                stack.append([a, b, c, carry])
                if TD == 2:
                    QFA(a, b, c, carry, and_ancilla[and_idx])
                else:
                    QFA(a, b, c, carry)
                and_idx += 1
                w_tmp.append(c)
                w_tmp2.append(carry)

            if flag == 1 and len(w[i]) == 2:
                a = w[i].pop(0)
                b = w[i].pop(0)
                carry = ancilla[num]
                num += 1
                an.append(carry)
                stack.append([a, b, carry])
                if TD == 2:
                    QHA(a, b, carry, and_ancilla[and_idx])
                else:
                    QHA(a, b, carry)
                and_idx += 1
                w_tmp.append(b)
                w_tmp2.append(carry)

            w[i].extend(w_tmp)
            w[i + 1].extend(w_tmp2)

        and_idx = 0
        for i in range(len(w)):
            if (len(w[i]) > 3):
                t += 1
                flag = 1

    and_idx = 0
    t = 1
    while (t):
        n = len(w)
        t = 0
        w_tmp = []
        if (len(w[n - 1]) > 2):
            while (len(w[n - 1]) > 2):
                a = w[n - 1].pop(0)
                b = w[n - 1].pop(0)
                c = w[n - 1].pop(0)
                stack.append([a, b, c, 0, 0, 0])
                modQFA(a, b, c)
                w_tmp.append(c)

            w[n - 1].extend(w_tmp)

        for i in reversed(range(0, n - 1)):
            w_tmp = []
            w_tmp2 = []
            while (len(w[i]) > 2):
                a = w[i].pop(0)
                b = w[i].pop(0)
                c = w[i].pop(0)
                carry = ancilla[num]
                num += 1
                an.append(carry)
                stack.append([a, b, c, carry])
                if TD == 2:
                    QFA(a, b, c, carry, and_ancilla[and_idx])
                else:
                    QFA(a, b, c, carry)
                and_idx += 1
                w_tmp.append(c)
                w_tmp2.append(carry)

            if len(w[i]) == 2:
                a = w[i].pop(0)
                b = w[i].pop(0)
                carry = ancilla[num]
                num += 1
                an.append(carry)
                stack.append([a, b, carry])
                if TD == 2:
                    QHA(a, b, carry, and_ancilla[and_idx])
                else:
                    QHA(a, b, carry)
                and_idx += 1
                w_tmp.append(b)
                w_tmp2.append(carry)

            w[i].extend(w_tmp)
            w[i + 1].extend(w_tmp2)

        and_idx = 0
        for i in range(len(w)):
            if (len(w[i]) > 2):
                t += 1
    return w, stack


def apply_adders_and_handle_carry00(eng, w, input2, ancilla, and_ancilla):
    num = 0
    and_idx = 0
    t = 1
    copy_ancilla = ancilla[-64:]
    idx = 0
    stack = []
    share1 = []
    share2 = []
    flag1 = 1
    flag2 = 1
    while (t):
        n = len(w)
        t = 0
        w_tmp = []

        if (len(w[n - 1]) > 2):
            while (len(w[n - 1]) > 2):
                a = w[n - 1].pop(0)
                b = w[n - 1].pop(0)
                c = w[n - 1].pop(0)
                stack.append([a, b, c, 0, 0, 0])
                modQFA(a, b, c)
                w_tmp.append(c)

            if flag1 == 1:
                flag1 = 0
                stack.append([w_tmp[0], copy_ancilla[idx]])
                CNOT | (w_tmp[0], copy_ancilla[idx])
                share1.append(copy_ancilla[idx])
                idx += 1
                w[n - 1].insert(0, w_tmp[0])
                w[n - 1].insert(-1, w_tmp[1])

            else:
                w[n - 1].extend(w_tmp)

        for i in reversed(range(0, n - 1)):
            w_tmp = []
            w_tmp2 = []
            while (len(w[i]) > 2):
                a = w[i].pop(0)
                b = w[i].pop(0)
                c = w[i].pop(0)
                carry = ancilla[num]
                num += 1
                an.append(carry)
                stack.append([a, b, c, carry])
                if TD == 2:
                    QFA(a, b, c, carry, and_ancilla[and_idx])
                else:
                    QFA(a, b, c, carry)
                and_idx += 1
                w_tmp.append(c)
                w_tmp2.append(carry)

            if flag2 == 1:
                stack.append([w_tmp[0], copy_ancilla[idx]])
                CNOT | (w_tmp[0], copy_ancilla[idx])
                share1.append(copy_ancilla[idx])
                idx += 1
                share2.append(w_tmp2[0])
                w[i].insert(0, w_tmp[0])
                w[i].insert(-1, w_tmp[1])
                w[i + 1].insert(1, w_tmp2[0])
                w[i + 1].insert(-1, w_tmp2[1])

            else:
                w[i].extend(w_tmp)
                w[i + 1].extend(w_tmp2)

        and_idx = 0
        if flag2 == 1:
            flag2 = 0
            share1.reverse()
            share2.reverse()
            input2.append(share1)
            input2.append(share2)

    return w, stack, input2, num


def apply_adders_and_handle_carry01(eng, w, stack, ancilla, num, and_ancilla):
    and_idx = 0
    t = 1
    flag = 0
    while (t):
        n = len(w)
        t = 0
        w_tmp = []
        if (len(w[n - 1]) > 2):
            while (len(w[n - 1]) > 2):
                a = w[n - 1].pop(0)
                b = w[n - 1].pop(0)
                c = w[n - 1].pop(0)
                stack.append([a, b, c, 0, 0, 0])
                modQFA(a, b, c)
                w_tmp.append(c)

            w[n - 1].extend(w_tmp)

        for i in reversed(range(0, n - 1)):
            w_tmp = []
            w_tmp2 = []
            while (len(w[i]) > 2):
                a = w[i].pop(0)
                b = w[i].pop(0)
                c = w[i].pop(0)
                carry = ancilla[num]
                num += 1
                an.append(carry)
                stack.append([a, b, c, carry])
                if TD == 2:
                    QFA(a, b, c, carry, and_ancilla[and_idx])
                else:
                    QFA(a, b, c, carry)
                and_idx += 1
                w_tmp.append(c)
                w_tmp2.append(carry)

            if i == 0:
                flag = 1

            if flag == 1 and len(w[i]) == 2:
                a = w[i].pop(0)
                b = w[i].pop(0)
                carry = ancilla[num]
                num += 1
                an.append(carry)
                stack.append([a, b, carry])
                if TD == 2:
                    QHA(a, b, carry, and_ancilla[and_idx])
                else:
                    QHA(a, b, carry)
                and_idx += 1
                w_tmp.append(b)
                w_tmp2.append(carry)

            w[i].extend(w_tmp)
            w[i + 1].extend(w_tmp2)

        and_idx = 0
        for i in range(len(w)):
            if (len(w[i]) > 3):
                t += 1
                flag = 1

    and_idx = 0
    t = 1
    while (t):
        n = len(w)
        t = 0
        w_tmp = []
        if (len(w[n - 1]) > 2):
            while (len(w[n - 1]) > 2):
                a = w[n - 1].pop(0)
                b = w[n - 1].pop(0)
                c = w[n - 1].pop(0)
                stack.append([a, b, c, 0, 0, 0])
                modQFA(a, b, c)
                w_tmp.append(c)

            w[n - 1].extend(w_tmp)

        for i in reversed(range(0, n - 1)):
            w_tmp = []
            w_tmp2 = []
            while (len(w[i]) > 2):
                a = w[i].pop(0)
                b = w[i].pop(0)
                c = w[i].pop(0)
                carry = ancilla[num]
                num += 1
                an.append(carry)
                stack.append([a, b, c, carry])
                if TD == 2:
                    QFA(a, b, c, carry, and_ancilla[and_idx])
                else:
                    QFA(a, b, c, carry)
                and_idx += 1
                w_tmp.append(c)
                w_tmp2.append(carry)

            if len(w[i]) == 2:
                a = w[i].pop(0)
                b = w[i].pop(0)
                carry = ancilla[num]
                num += 1
                an.append(carry)
                stack.append([a, b, carry])
                if TD == 2:
                    QHA(a, b, carry, and_ancilla[and_idx])
                else:
                    QHA(a, b, carry)
                and_idx += 1
                w_tmp.append(b)
                w_tmp2.append(carry)

            w[i].extend(w_tmp)
            w[i + 1].extend(w_tmp2)

        for i in range(len(w)):
            if (len(w[i]) > 2):
                t += 1
    return w, stack


def apply_final_cnot(eng, w, output=0):
    idx = -1
    for i in range(len(w)):
        if len(w[i]) == 1:
            if output != 0:
                ancilla = output[idx]
                idx -= 1
            else:
                ancilla = eng.allocate_qubit()
            CNOT | (w[i].pop(), ancilla)
            w[i].append(ancilla)

    return w


def transfer_to_rca_components(w):
    rca_A = []
    rca_B = []
    R = []
    while (len(w)):
        if len(w[0]) == 1:
            if (len(w) == 1):
                rca_A.append(w.pop(0).pop())
                rca_B.append(eng.allocate_qubit())
            else:
                R.append(w.pop(0).pop())

        elif len(w[0]) == 2:
            tmp = w.pop(0)
            rca_A.append(tmp.pop(0))
            rca_B.append(tmp.pop())

    return rca_A, rca_B, R


def reverse_adders(stack):
    while (len(stack)):
        tmp = stack.pop()
        if (len(tmp) == 2):
            CNOT | (tmp[0], tmp[1])
        if (len(tmp) == 3):
            QHA_R(tmp[0], tmp[1], tmp[2])
        if (len(tmp) == 4):
            QFA_R(tmp[0], tmp[1], tmp[2], tmp[3])
        if (len(tmp) == 5):
            CNOT | (tmp[0], tmp[1])
        if (len(tmp) == 6):
            modQFA_R(tmp[0], tmp[1], tmp[2])


def modQFA(a, b, c):
    CNOT | (a, b)
    CNOT | (b, c)
    CNOT | (a, b)


def modQFA_R(a, b, c):
    CNOT | (a, b)
    CNOT | (b, c)
    CNOT | (a, b)


def QFA(a, b, c, d, ancilla=0):
    CNOT | (a, b)
    CNOT | (a, c)
    if TD == 2:
        toffoli_gate(b, c, d, ancilla)
    else:
        toffoli_gate(b, c, d)
    CNOT | (a, b)
    CNOT | (a, d)
    CNOT | (b, c)


def QFA_R(a, b, c, d):
    CNOT | (b, c)
    CNOT | (a, d)
    CNOT | (a, b)
    if TD == 2:
        toffoli_gate(b, c, d, 0, False)
    else:
        toffoli_gate(b, c, d)
    CNOT | (a, c)
    CNOT | (a, b)


def QHA(a, b, c, ancilla=0):
    if TD == 2:
        toffoli_gate(a, b, c, ancilla)
    else:
        toffoli_gate(a, b, c)
    CNOT | (a, b)


def QHA_R(a, b, c):
    CNOT | (a, b)
    if TD == 2:
        toffoli_gate(a, b, c, 0, False)
    else:
        toffoli_gate(a, b, c)


def csa0(eng, input1, input2, ancillas0, ancillas1, outputs):
    w1 = initialize_circuit_and_qubits(input1)
    w1, stack0, input2, num = apply_adders_and_handle_carry0(eng, w1, input2, ancillas0[0], ancillas0[1])
    w2 = initialize_circuit_and_qubits(input2)

    w1, stack1 = apply_adders_and_handle_carry1(eng, w1, stack0, ancillas0[0], num, ancillas0[1])

    w2, stack2 = apply_adders_and_handle_carry(eng, w2, ancillas1[0], ancillas1[1])

    w1 = apply_final_cnot(eng, w1, outputs[0])
    w2 = apply_final_cnot(eng, w2, outputs[1])

    rca_A1, rca_B1, R1 = transfer_to_rca_components(w1)
    rca_A2, rca_B2, R2 = transfer_to_rca_components(w2)

    result1 = outDraper_dirty(eng, rca_A1, rca_B1, ancillas0[1], outputs[0])
    result2 = outDraper_dirty(eng, rca_A2, rca_B2, ancillas1[1], outputs[1])

    DrapOut_stack1 = [rca_A1, rca_B1, ancillas0[1], result1]
    DrapOut_stack2 = [rca_A2, rca_B2, ancillas1[1], result2]

    result1 = R1 + result1
    result2 = R2 + result2


    return result1, result2, stack1, stack2, DrapOut_stack1, DrapOut_stack2


def csa1_0_no_w(eng, input, input2, ancillas0, ancillas1, outputs):
    w1 = initialize_circuit_and_qubits(input)
    w1, stack0, input2, num = apply_adders_and_handle_carry00(eng, w1, input2, ancillas0[0] + ancillas1[0][:2],
                                                              ancillas0[1])
    w2 = initialize_circuit_and_qubits(input2)

    w1, stack1 = apply_adders_and_handle_carry01(eng, w1, stack0, ancillas0[0], num, ancillas0[1])
    w2, stack2 = apply_adders_and_handle_carry(eng, w2, ancillas1[0][2:], ancillas1[1])

    w1 = apply_final_cnot(eng, w1, outputs[0])
    w2 = apply_final_cnot(eng, w2, outputs[1])

    rca_A1, rca_B1, R1 = transfer_to_rca_components(w1)
    rca_A2, rca_B2, R2 = transfer_to_rca_components(w2)

    result1 = outDraper_dirty(eng, rca_A1, rca_B1, ancillas0[1], outputs[0])
    result2 = outDraper_dirty(eng, rca_A2, rca_B2, ancillas1[1], outputs[1])

    DrapOut_stack1 = [rca_A1, rca_B1, ancillas0[1], result1]
    DrapOut_stack2 = [rca_A2, rca_B2, ancillas1[1], result2]

    result1 = R1 + result1
    result2 = R2 + result2

    return result1, result2, stack1, stack2, DrapOut_stack1, DrapOut_stack2


def csa1_0(eng, input, input2, input3, ancillas0, ancillas1, ancillas2, outputs):
    w1 = initialize_circuit_and_qubits(input)
    if len(input3) != 2:
        w3 = initialize_circuit_and_qubits(input3)
    w1, stack0, input2, num = apply_adders_and_handle_carry00(eng, w1, input2, ancillas0[0] + ancillas1[0][:2],
                                                              ancillas0[1])
    w2 = initialize_circuit_and_qubits(input2)

    w1, stack1 = apply_adders_and_handle_carry01(eng, w1, stack0, ancillas0[0], num, ancillas0[1])
    w2, stack2 = apply_adders_and_handle_carry(eng, w2, ancillas1[0][2:], ancillas1[1])
    if len(input3) != 2:
        w3, stack3 = apply_adders_and_handle_carry(eng, w3, ancillas2[0], ancillas2[1])

    w1 = apply_final_cnot(eng, w1, outputs[0])
    w2 = apply_final_cnot(eng, w2, outputs[1])
    if len(input3) != 2:
        w3 = apply_final_cnot(eng, w3, outputs[2])

    rca_A1, rca_B1, R1 = transfer_to_rca_components(w1)
    rca_A2, rca_B2, R2 = transfer_to_rca_components(w2)
    if len(input3) != 2:
        rca_A3, rca_B3, R3 = transfer_to_rca_components(w3)

    result1 = outDraper_dirty(eng, rca_A1, rca_B1, ancillas0[1], outputs[0])
    result2 = outDraper_dirty(eng, rca_A2, rca_B2, ancillas1[1], outputs[1])
    if len(input3) != 2:
        result3 = outDraper_dirty(eng, rca_A3, rca_B3, ancillas2[1], outputs[2])
    else:
        result3 = outDraper_dirty(eng, input3[0], input3[1], ancillas2[0] + ancillas2[1], outputs[2])

    DrapOut_stack1 = [rca_A1, rca_B1, ancillas0[1], result1]
    DrapOut_stack2 = [rca_A2, rca_B2, ancillas1[1], result2]

    if len(input3) != 2:
        DrapOut_stack3 = [rca_A3, rca_B3, ancillas2[1], result3]
    else:
        DrapOut_stack3 = [input3[0], input3[1], ancillas2[0] + ancillas2[1], result3]

    result1 = R1 + result1
    result2 = R2 + result2
    if len(input3) != 2:
        result3 = R3 + result3

    return result1, result2, result3, stack1, stack2, stack3, DrapOut_stack1, DrapOut_stack2, DrapOut_stack3


def csa_ww(eng, input, ancillas, output):
    w = initialize_circuit_and_qubits(input)
    w, stack = apply_adders_and_handle_carry(eng, w, ancillas[0], ancillas[1])
    w = apply_final_cnot(eng, w, output)
    rca_A, rca_B, R = transfer_to_rca_components(w)
    result = outDraper(eng, rca_A, rca_B, ancillas[1], output)
    reverse_adders(stack)

    return R + result


def make_list(num, length):
    arr1 = list(format(num, 'b'))
    if length > len(arr1):
        arr2 = ['0' for i in range(length - len(arr1))]
        arr2.extend(arr1)
        arr1 = arr2
    return arr1


def SHA512_init_H(eng, H, idx):
    H0_hex = [
        0x6a09e667f3bcc908, 0xbb67ae8584caa73b, 0x3c6ef372fe94f82b, 0xa54ff53a5f1d36f1,
        0x510e527fade682d1, 0x9b05688c2b3e6c1f, 0x1f83d9abfb41bd6b, 0x5be0cd19137e2179
    ]

    chain = make_list(H0_hex[idx], 64)
    for j in range(64):
        if chain[j] == '1':
            X | H[idx][63 - j]

    return H[idx]


SHA512_K_VALUES = [
    0x428a2f98d728ae22, 0x7137449123ef65cd, 0xb5c0fbcfec4d3b2f, 0xe9b5dba58189dbbc,
    0x3956c25bf348b538, 0x59f111f1b605d019, 0x923f82a4af194f9b, 0xab1c5ed5da6d8118,
    0xd807aa98a3030242, 0x12835b0145706fbe, 0x243185be4ee4b28c, 0x550c7dc3d5ffb4e2,
    0x72be5d74f27b896f, 0x80deb1fe3b1696b1, 0x9bdc06a725c71235, 0xc19bf174cf692694,
    0xe49b69c19ef14ad2, 0xefbe4786384f25e3, 0x0fc19dc68b8cd5b5, 0x240ca1cc77ac9c65,
    0x2de92c6f592b0275, 0x4a7484aa6ea6e483, 0x5cb0a9dcbd41fbd4, 0x76f988da831153b5,
    0x983e5152ee66dfab, 0xa831c66d2db43210, 0xb00327c898fb213f, 0xbf597fc7beef0ee4,
    0xc6e00bf33da88fc2, 0xd5a79147930aa725, 0x06ca6351e003826f, 0x142929670a0e6e70,
    0x27b70a8546d22ffc, 0x2e1b21385c26c926, 0x4d2c6dfc5ac42aed, 0x53380d139d95b3df,
    0x650a73548baf63de, 0x766a0abb3c77b2a8, 0x81c2c92e47edaee6, 0x92722c851482353b,
    0xa2bfe8a14cf10364, 0xa81a664bbc423001, 0xc24b8b70d0f89791, 0xc76c51a30654be30,
    0xd192e819d6ef5218, 0xd69906245565a910, 0xf40e35855771202a, 0x106aa07032bbd1b8,
    0x19a4c116b8d2d0c8, 0x1e376c085141ab53, 0x2748774cdf8eeb99, 0x34b0bcb5e19b48a8,
    0x391c0cb3c5c95a63, 0x4ed8aa4ae3418acb, 0x5b9cca4f7763e373, 0x682e6ff3d6b2b8a3,
    0x748f82ee5defb2fc, 0x78a5636f43172f60, 0x84c87814a1f0ab72, 0x8cc702081a6439ec,
    0x90befffa23631e28, 0xa4506cebde82bde9, 0xbef9a3f7b2c67915, 0xc67178f2e372532b,
    0xca273eceea26619c, 0xd186b8c721c0c207, 0xeada7dd6cde0eb1e, 0xf57d4f7fee6ed178,
    0x06f067aa72176fba, 0x0a637dc5a2c898a6, 0x113f9804bef90dae, 0x1b710b35131c471b,
    0x28db77f523047d84, 0x32caab7b40c72493, 0x3c9ebe0a15c9bebc, 0x431d67c49c100d4c,
    0x4cc5d4becb3e42b6, 0x597f299cfc657e2a, 0x5fcb6fab3ad6faec, 0x6c44198c4a475817
]


def SHA512_K(eng, idx):
    return make_list(SHA512_K_VALUES[idx], 64)


def SHA512_K_const(eng, idx):
    K = make_list(SHA512_K_VALUES[idx], 64)
    K.reverse()
    return K


def K_set(eng, K, q):
    for i in range(len(q)):
        if K[i] == '1':
            X | q[len(q) - 1 - i]


def w_sigma(rr0, rr1, ss, input, output):
    ss_len = 64 - ss
    for i in range(64):
        CNOT | (input[(rr0 + i) % 64], output[i])
    for i in range(64):
        CNOT | (input[(rr1 + i) % 64], output[i])
    for i in range(64):
        if i < ss_len:
            CNOT | (input[i + ss], output[i])


def r_sigma(rr0, rr1, rr2, input, output):
    for i in range(64):
        CNOT | (input[(rr0 + i) % 64], output[i])
    for i in range(64):
        CNOT | (input[(rr1 + i) % 64], output[i])
    for i in range(64):
        CNOT | (input[(rr2 + i) % 64], output[i])


def maj_out(x, y, z, result, tmp=0, ancilla=0):
    for i in range(64):
        CNOT | (z[i], result[i])

    for i in range(64):
        CNOT | (z[i], y[i])

    for i in range(64):
        CNOT | (result[i], x[i])

    if TD == 2:
        for i in range(64):
            toffoli_gate(x[i], y[i], tmp[i], ancilla[i])
            CNOT | (tmp[i], result[i])
    else:
        for i in range(64):
            toffoli_gate(x[i], y[i], result[i])

    for i in range(64):
        CNOT | (z[i], x[i])

    for i in range(64):
        CNOT | (z[i], y[i])


def maj_out_dag(x, y, z, result, tmp=0, ancilla=0):
    for i in range(64):
        CNOT | (z[i], y[i])

    for i in range(64):
        CNOT | (z[i], x[i])

    if TD == 2:
        for i in range(64):
            CNOT | (tmp[i], result[i])
            toffoli_gate(x[i], y[i], tmp[i], ancilla[i])
    else:
        for i in range(64):
            toffoli_gate(x[i], y[i], result[i])

    for i in range(64):
        CNOT | (result[i], x[i])

    for i in range(64):
        CNOT | (z[i], y[i])

    for i in range(64):
        CNOT | (z[i], result[i])


def ch_out(x, y, z, result, tmp=0, ancilla=0):
    for i in range(64):
        CNOT | (z[i], result[i])

    for i in range(64):
        CNOT | (y[i], z[i])

    if TD == 2:
        for i in range(64):
            toffoli_gate(x[i], z[i], tmp[i], ancilla[i])
            CNOT | (tmp[i], result[i])
    else:
        for i in range(64):
            toffoli_gate(x[i], z[i], result[i])

    for i in range(64):
        CNOT | (y[i], z[i])


def ch_out_dag(x, y, z, result, tmp=0):
    for i in range(64):
        CNOT | (y[i], z[i])
    if TD == 2:
        for i in range(64):
            CNOT | (tmp[i], result[i])
            toffoli_gate(x[i], z[i], tmp[i], 0, False)
    else:
        for i in range(64):
            toffoli_gate(x[i], z[i], result[i])
    for i in range(64):
        CNOT | (y[i], z[i])

    for i in range(64):
        CNOT | (z[i], result[i])


def copy(x, y):
    for i in range(64):
        CNOT | (x[i], y[i])


def csa2_d(eng, input, ancillas, output):
    if len(input) != 2:
        w = initialize_circuit_and_qubits(input)
        w, stack = apply_adders_and_handle_carry(eng, w, ancillas[0], ancillas[1])


        k = sum(1 for wi in w if len(wi) == 1)
        if k > 0:
            original_output = list(output[k:]) + list(reversed(output[:k]))
        else:
            original_output = list(output)

        w = apply_final_cnot(eng, w, original_output)
        rca_A, rca_B, R = transfer_to_rca_components(w)
        result = outDraper_dag(eng, rca_A, rca_B, ancillas[1], original_output)
        reverse_adders(stack)
        result = R + result
    else:
        result = outDraper_dag(eng, input[0], input[1], ancillas[0] + ancillas[1], output)

    return result


def SHA512_Compression(eng, H, W):
    """SHA-512 compression function over 80 rounds.
    H:   list of 8 x 64-qubit registers (working variables, modified in-place)
    W:   list of 16 x 64-qubit registers (message schedule, first 16 words)
    """
    even_add_ancilla = []
    tmp = []
    tmp.append(eng.allocate_qureg(313))
    tmp.append(eng.allocate_qureg(168))
    even_add_ancilla.append(tmp)

    tmp = []
    tmp.append(eng.allocate_qureg(188))
    tmp.append(eng.allocate_qureg(168))
    even_add_ancilla.append(tmp)

    tmp = []
    tmp.append(eng.allocate_qureg(126))
    tmp.append(eng.allocate_qureg(171))
    even_add_ancilla.append(tmp)

    odd_add_ancilla = []
    tmp = []
    tmp.append(eng.allocate_qureg(313))
    tmp.append(eng.allocate_qureg(168))
    odd_add_ancilla.append(tmp)

    tmp = []
    tmp.append(eng.allocate_qureg(188))
    tmp.append(eng.allocate_qureg(168))
    odd_add_ancilla.append(tmp)

    tmp = []
    tmp.append(eng.allocate_qureg(126))
    tmp.append(eng.allocate_qureg(171))
    odd_add_ancilla.append(tmp)

    maj_ch_tmp = []
    maj_ch_tmp.append(eng.allocate_qureg(64))
    maj_ch_tmp.append(eng.allocate_qureg(64))

    sigma_ancilla = []
    for i in range(8):
        sigma_ancilla.append(eng.allocate_qureg(64))

    pre_result = []
    for i in range(3):
        pre_result.append(eng.allocate_qureg(64))

    a0 = H[0]
    b0 = H[1]
    c0 = H[2]
    d0 = H[3]
    e0 = H[4]
    f0 = H[5]
    g0 = H[6]
    h0 = H[7]

    a1 = eng.allocate_qureg(64)
    b1 = eng.allocate_qureg(64)
    c1 = eng.allocate_qureg(64)
    d1 = eng.allocate_qureg(64)
    e1 = eng.allocate_qureg(64)
    f1 = eng.allocate_qureg(64)
    g1 = eng.allocate_qureg(64)
    h1 = eng.allocate_qureg(64)

    maj_result = []
    ch_result = []
    maj_result.append(eng.allocate_qureg(64))
    maj_result.append(eng.allocate_qureg(64))
    ch_result.append(eng.allocate_qureg(64))
    ch_result.append(eng.allocate_qureg(64))

    W_idx = 16


    dag_sigma_anc = [eng.allocate_qureg(64), eng.allocate_qureg(64)]
    dag_ancilla1 = [eng.allocate_qureg(126), eng.allocate_qureg(171)]
    free_pool = []
    dag_w_idx = 50
    pre_anc = [maj_ch_tmp[0], maj_ch_tmp[1]]
    late_output_reuse_pool = dag_sigma_anc[0] + dag_sigma_anc[1] + dag_ancilla1[0] + dag_ancilla1[1]
    late_output_reuse_idx = 0
    anc2_output_reuse_pool = list(even_add_ancilla[2][0]) + list(even_add_ancilla[2][1]) + \
                             list(odd_add_ancilla[2][0]) + list(odd_add_ancilla[2][1])
    anc2_output_reuse_idx = 0

    def pop_anc2_output_reuse(size):
        nonlocal anc2_output_reuse_idx, late_output_reuse_idx
        chunk = []
        remain = size

        if anc2_output_reuse_idx < len(anc2_output_reuse_pool):
            take = min(remain, len(anc2_output_reuse_pool) - anc2_output_reuse_idx)
            chunk.extend(anc2_output_reuse_pool[anc2_output_reuse_idx:anc2_output_reuse_idx + take])
            anc2_output_reuse_idx += take
            remain -= take

        if remain > 0 and late_output_reuse_idx < len(late_output_reuse_pool):
            take = min(remain, len(late_output_reuse_pool) - late_output_reuse_idx)
            chunk.extend(late_output_reuse_pool[late_output_reuse_idx:late_output_reuse_idx + take])
            late_output_reuse_idx += take
            remain -= take

        return chunk if remain == 0 else 0


    a0_sigma_fanout = eng.allocate_qureg(64)
    e0_sigma_fanout = eng.allocate_qureg(64)
    a1_sigma_fanout = eng.allocate_qureg(64)
    e1_sigma_fanout = eng.allocate_qureg(64)

    for i in range(80):
        if i % 2 == 0:
            add_ancilla1 = even_add_ancilla
            add_ancilla2 = odd_add_ancilla
        else:
            add_ancilla1 = odd_add_ancilla
            add_ancilla2 = even_add_ancilla

        if i == 0:
            K_q = dag_sigma_anc[0]
            K = SHA512_K(eng, i)
            K_set(eng, K, K_q)

            copy(a0, a0_sigma_fanout)
            copy(e0, e0_sigma_fanout)
            r_sigma(28, 34, 39, a0_sigma_fanout, sigma_ancilla[0])  # sigma_ancilla[0] = Σ0(a)
            r_sigma(14, 18, 41, e0_sigma_fanout, sigma_ancilla[1])  # sigma_ancilla[1] = Σ1(e)
            check_clean(eng, [maj_result[0]], "Maj output slot")
            maj_out(a0, b0, c0, maj_result[0], maj_ch_tmp[0], add_ancilla2[0][0])  # maj_result = Maj(a,b,c)
            ch_out(e0, f0, g0, ch_result[0], maj_ch_tmp[1], add_ancilla2[0][1])  # ch_result = Ch(e,f,g)
            copy(a0, a0_sigma_fanout)
            copy(e0, e0_sigma_fanout)

            input1 = [h0, sigma_ancilla[1], ch_result[0], W[i], K_q, maj_result[0], sigma_ancilla[0]]
            input2 = [W[i], K_q, d0]

            output = [0, 0, 0]


            updated_h0, updated_d0, even_stack1, even_stack2, even_DrapOut_stack1, even_DrapOut_stack2 = csa0(eng,
                                                                                                              input1,
                                                                                                              input2,
                                                                                                              add_ancilla1
                                                                                                              [0],
                                                                                                              add_ancilla1
                                                                                                              [1],
                                                                                                              output)


            pre_idx = i % 3
            check_clean(eng, [pre_result[pre_idx], pre_anc[0]], "K+W slot")
            outDraper_const(eng, SHA512_K_const(eng, i + 1), W[i + 1], pre_anc[0], pre_result[pre_idx])


            copy(a0, a1)
            copy(b0, b1)
            copy(c0, c1)
            copy(updated_d0, d1)
            copy(e0, e1)
            copy(f0, f1)
            copy(g0, g1)
            copy(updated_h0, h1)

        if i % 2 == 1:
            # inverse operation for previous round  (R_dag)
            if i != 79:
                if i == 1:
                    deferredAdd(eng, even_DrapOut_stack1[0], even_DrapOut_stack1[1], even_DrapOut_stack1[2],
                                        even_DrapOut_stack1[3])
                    deferredAdd(eng, even_DrapOut_stack2[0], even_DrapOut_stack2[1], even_DrapOut_stack2[2],
                                        even_DrapOut_stack2[3])

                    reverse_adders(even_stack2)
                    reverse_adders(even_stack1)

                    K_set(eng, K, K_q)

                    ch_out_dag(e0, f0, g0, ch_result[0], maj_ch_tmp[1])
                    maj_out_dag(a0, b0, c0, maj_result[0], maj_ch_tmp[0])
                    r_sigma(14, 18, 41, e0_sigma_fanout, sigma_ancilla[1])  # dag
                    r_sigma(28, 34, 39, a0_sigma_fanout, sigma_ancilla[0])  # dag
                    copy(e0, e0_sigma_fanout)  # dag
                    copy(a0, a0_sigma_fanout)  # dag


                else:
                    deferredAdd(eng, even_DrapOut_stack1[0], even_DrapOut_stack1[1], even_DrapOut_stack1[2],
                                        even_DrapOut_stack1[3])
                    deferredAdd(eng, even_DrapOut_stack2[0], even_DrapOut_stack2[1], even_DrapOut_stack2[2],
                                        even_DrapOut_stack2[3])
                    if 4 <= i <= 65:
                        deferredAdd(eng, even_DrapOut_stack3[0], even_DrapOut_stack3[1], even_DrapOut_stack3[2],
                                            even_DrapOut_stack3[3])

                    if 4 <= i <= 65:
                        reverse_adders(even_stack3)
                    reverse_adders(even_stack2)
                    reverse_adders(even_stack1)

                    copy(e0, e0_sigma_fanout)
                    copy(a0, a0_sigma_fanout)
                    ch_out_dag(e0, f0, g0, ch_result[0], maj_ch_tmp[1])
                    maj_out_dag(a0, b0, c0, maj_result[0], maj_ch_tmp[0])
                    r_sigma(14, 18, 41, e0_sigma_fanout, sigma_ancilla[1])  # dag
                    r_sigma(28, 34, 39, a0_sigma_fanout, sigma_ancilla[0])  # dag
                    copy(e0, e0_sigma_fanout)
                    copy(a0, a0_sigma_fanout)


            copy(a1, a1_sigma_fanout)
            copy(e1, e1_sigma_fanout)
            r_sigma(28, 34, 39, a1_sigma_fanout, sigma_ancilla[4])  # sigma_ancilla[4] = Σ0(a)
            r_sigma(14, 18, 41, e1_sigma_fanout, sigma_ancilla[5])  # sigma_ancilla[5] = Σ1(e)
            check_clean(eng, [maj_result[1]], "Maj output slot")
            maj_out(a1, b1, c1, maj_result[1], maj_ch_tmp[0], add_ancilla2[1][0])  # maj_result = Maj(a,b,c)
            ch_out(e1, f1, g1, ch_result[1], maj_ch_tmp[1], add_ancilla2[1][1])  # ch_result = Ch(e,f,g)
            copy(a1, a1_sigma_fanout)
            copy(e1, e1_sigma_fanout)


            pre_idx = (i - 1) % 3
            input1 = [h1, sigma_ancilla[5], ch_result[1], maj_result[1], pre_result[pre_idx], sigma_ancilla[4]]
            input2 = [pre_result[pre_idx], d1]

            if 3 <= i <= 64:
                w_sigma(1, 8, 7, W[W_idx - 15], sigma_ancilla[6])  # sigma_ancilla[6] = σ0(W[i-15])
                w_sigma(19, 61, 6, W[W_idx - 2], sigma_ancilla[7])  # sigma_ancilla[7] = σ1(W[i-2])

                if 53 <= i <= 64 and len(free_pool) > 0:
                    output = [0, 0, free_pool.pop(0)]
                else:
                    output = [0, 0, 0]

                if i > 0 and i < 7:
                    input3 = [W[W_idx - 16], sigma_ancilla[6],
                              sigma_ancilla[7]]
                elif i >= 10 and i < 16:
                    input3 = [W[W_idx - 7], sigma_ancilla[6],
                              sigma_ancilla[7]]
                else:
                    input3 = [W[W_idx - 16], W[W_idx - 7], sigma_ancilla[6], sigma_ancilla[7]]

                check_clean(eng, [o for o in output if not isinstance(o, int)], "reused output registers")
                updated_h1, updated_d1, ww, odd_stack1, odd_stack2, odd_stack3, odd_DrapOut_stack1, odd_DrapOut_stack2, odd_DrapOut_stack3 = csa1_0(
                    eng, input1, input2, input3,
                    add_ancilla1[0], add_ancilla1[1],
                    add_ancilla1[2], output)
                W.append(ww)
            else:
                if 66 <= i <= 72:
                    if i <= 67:
                        output = [pop_anc2_output_reuse(64), pop_anc2_output_reuse(64)]
                    else:
                        output = [free_pool.pop(0) if len(free_pool) > 0 else 0, pop_anc2_output_reuse(64)]
                elif i == 73 and len(free_pool) > 0:
                    output = [free_pool.pop(0), 0]
                elif i == 74 and len(free_pool) > 0:
                    output = [free_pool.pop(0), 0]
                elif 75 <= i <= 77 and late_output_reuse_idx + 128 <= len(late_output_reuse_pool):
                    output = [
                        late_output_reuse_pool[late_output_reuse_idx:late_output_reuse_idx + 64],
                        late_output_reuse_pool[late_output_reuse_idx + 64:late_output_reuse_idx + 128]
                    ]
                    late_output_reuse_idx += 128
                else:
                    output = [0, 0]

                check_clean(eng, [o for o in output if not isinstance(o, int)], "reused output registers")
                updated_h1, updated_d1, odd_stack1, odd_stack2, odd_DrapOut_stack1, odd_DrapOut_stack2 = csa1_0_no_w(
                    eng, input1, input2,
                    add_ancilla1[0], add_ancilla1[1], output)

                if i <= 2:
                    w_sigma(1, 8, 7, W[W_idx - 15], sigma_ancilla[6])
                    w_sigma(19, 61, 6, W[W_idx - 2], sigma_ancilla[7])
                    if i > 0 and i < 7:
                        w_input = [W[W_idx - 16], sigma_ancilla[6], sigma_ancilla[7]]
                    else:
                        w_input = [W[W_idx - 16], W[W_idx - 7], sigma_ancilla[6], sigma_ancilla[7]]
                    ww = eng.allocate_qureg(64)
                    ww = csa_ww(eng, w_input, add_ancilla1[2], ww)
                    W.append(ww)


            if 3 <= i <= 65:
                w_sigma(1, 8, 7, W[W_idx - 15 - 1], sigma_ancilla[2])
                w_sigma(19, 61, 6, W[W_idx - 2 - 1], sigma_ancilla[3])


            if 52 <= i <= 70 and dag_w_idx >= 16:
                t = dag_w_idx
                i_orig = t - 15

                w_sigma(1, 8, 7, W[t - 15], dag_sigma_anc[0])
                w_sigma(19, 61, 6, W[t - 2], dag_sigma_anc[1])

                if 0 < i_orig < 7:
                    input_dag = [W[t - 16], dag_sigma_anc[0], dag_sigma_anc[1]]
                elif 10 <= i_orig < 16:
                    input_dag = [W[t - 7], dag_sigma_anc[0], dag_sigma_anc[1]]
                elif i_orig % 2 == 0:
                    input_dag = [W[t - 16], dag_sigma_anc[0], W[t - 7], dag_sigma_anc[1]]
                else:
                    input_dag = [W[t - 16], W[t - 7], dag_sigma_anc[0], dag_sigma_anc[1]]

                W[t] = csa2_d(eng, input_dag, dag_ancilla1, W[t])

                w_sigma(1, 8, 7, W[t - 15], dag_sigma_anc[0])
                w_sigma(19, 61, 6, W[t - 2], dag_sigma_anc[1])
                free_pool.append(W[t])
                dag_w_idx -= 1

            # reset pre_round_qubits
            copy(b1, a0) # a0 reset
            copy(c1, b0) # b0 reset
            copy(d1, c0) # c0 reset
            copy(e1, updated_d0) # updated_d0 reset
            copy(f1, e0) # e0 reset
            copy(g1, f0) # f0 reset
            copy(h1, g0) # g0 reset
            copy(a1, updated_h0) # updated_h0 reset
            check_clean(eng, [a0, b0, c0, updated_d0, e0, f0, g0, updated_h0], "register set before reload")

            copy(a1, a0)
            copy(b1, b0)
            copy(c1, c0)
            copy(updated_d1, updated_d0)
            copy(e1, e0)
            copy(f1, f0)
            copy(g1, g0)
            copy(updated_h1, updated_h0)

            if i != 79:
                 # operand reduction
                pre_idx = i % 3
                check_clean(eng, [pre_result[pre_idx], pre_anc[0]], "K+W slot")
                outDraper_const(eng, SHA512_K_const(eng, i + 1), W[i + 1], pre_anc[0], pre_result[pre_idx])


                if i >= 2:
                    prev2_pre_idx = (i - 2) % 3
                    outDraper_const_dag(eng, SHA512_K_const(eng, i - 1), W[i - 1], pre_anc[1],
                                        pre_result[prev2_pre_idx])

        if i > 0 and i % 2 == 0:
            # inverse operation for previous round  (R_dag)
            deferredAdd(eng, odd_DrapOut_stack1[0], odd_DrapOut_stack1[1], odd_DrapOut_stack1[2],
                                odd_DrapOut_stack1[3])
            deferredAdd(eng, odd_DrapOut_stack2[0], odd_DrapOut_stack2[1], odd_DrapOut_stack2[2],
                                odd_DrapOut_stack2[3])
            if 4 <= i <= 65:
                deferredAdd(eng, odd_DrapOut_stack3[0], odd_DrapOut_stack3[1], odd_DrapOut_stack3[2],
                                    odd_DrapOut_stack3[3])

            if 4 <= i <= 65:
                reverse_adders(odd_stack3)
            reverse_adders(odd_stack2)
            reverse_adders(odd_stack1)

            ch_out_dag(e1, f1, g1, ch_result[1], maj_ch_tmp[1])
            maj_out_dag(a1, b1, c1, maj_result[1], maj_ch_tmp[0])
            r_sigma(14, 18, 41, e1_sigma_fanout, sigma_ancilla[5])  # dag
            r_sigma(28, 34, 39, a1_sigma_fanout, sigma_ancilla[4])  # dag
            copy(e1, e1_sigma_fanout)  # dag
            copy(a1, a1_sigma_fanout)  # dag

            # Forward round R

            copy(a0, a0_sigma_fanout)
            copy(e0, e0_sigma_fanout)
            r_sigma(28, 34, 39, a0_sigma_fanout, sigma_ancilla[0])  # sigma_ancilla[0] = Σ0(a)
            check_clean(eng, [maj_result[0]], "Maj output slot")
            maj_out(a0, b0, c0, maj_result[0], maj_ch_tmp[0], add_ancilla2[0][0])  # maj_result = Maj(a,b,c)
            r_sigma(14, 18, 41, e0_sigma_fanout, sigma_ancilla[1])  # sigma_ancilla[1] = Σ1(e)
            ch_out(e0, f0, g0, ch_result[0], maj_ch_tmp[1], add_ancilla2[0][1])  # ch_result = Ch(e,f,g)
            copy(a0, a0_sigma_fanout)
            copy(e0, e0_sigma_fanout)

            # pre_result = W[i]+K[i]
            pre_idx = (i - 1) % 3
            input1 = [h0, sigma_ancilla[1], ch_result[0], maj_result[0], pre_result[pre_idx], sigma_ancilla[0]]
            input2 = [pre_result[pre_idx], d0]

            if 3 <= i <= 64:
                w_sigma(1, 8, 7, W[W_idx - 15], sigma_ancilla[2])  # sigma_ancilla[2] = σ0(W[i-15])
                w_sigma(19, 61, 6, W[W_idx - 2], sigma_ancilla[3])  # sigma_ancilla[3] = σ1(W[i-2])

                if 53 <= i <= 64 and len(free_pool) > 0:
                    output = [0, 0, free_pool.pop(0)]
                else:
                    output = [0, 0, 0]
                if i > 0 and i < 7:
                    input3 = [W[W_idx - 16], sigma_ancilla[2],
                              sigma_ancilla[3]]
                elif i >= 10 and i < 16:
                    input3 = [W[W_idx - 7], sigma_ancilla[2],
                              sigma_ancilla[3]]
                else:
                    input3 = [W[W_idx - 16], sigma_ancilla[2], W[W_idx - 7], sigma_ancilla[3]]

                check_clean(eng, [o for o in output if not isinstance(o, int)], "reused output registers")
                updated_h0, updated_d0, ww, even_stack1, even_stack2, even_stack3, even_DrapOut_stack1, even_DrapOut_stack2, even_DrapOut_stack3 = csa1_0(
                    eng, input1, input2, input3,
                    add_ancilla1[0], add_ancilla1[1],
                    add_ancilla1[2], output)
                W.append(ww)

            else:
                if 66 <= i <= 72:
                    if i <= 67:
                        output = [pop_anc2_output_reuse(64), pop_anc2_output_reuse(64)]
                    else:
                        output = [free_pool.pop(0) if len(free_pool) > 0 else 0, pop_anc2_output_reuse(64)]
                elif i == 73 and len(free_pool) > 0:
                    output = [free_pool.pop(0), 0]
                elif i == 74 and len(free_pool) > 0:
                    output = [free_pool.pop(0), 0]
                elif 75 <= i <= 77 and late_output_reuse_idx + 128 <= len(late_output_reuse_pool):
                    output = [
                        late_output_reuse_pool[late_output_reuse_idx:late_output_reuse_idx + 64],
                        late_output_reuse_pool[late_output_reuse_idx + 64:late_output_reuse_idx + 128]
                    ]
                    late_output_reuse_idx += 128
                else:
                    output = [0, 0]

                check_clean(eng, [o for o in output if not isinstance(o, int)], "reused output registers")
                updated_h0, updated_d0, even_stack1, even_stack2, even_DrapOut_stack1, even_DrapOut_stack2 = csa1_0_no_w(
                    eng, input1, input2,
                    add_ancilla1[0], add_ancilla1[1], output)

                if i <= 2:
                    w_sigma(1, 8, 7, W[W_idx - 15], sigma_ancilla[2])
                    w_sigma(19, 61, 6, W[W_idx - 2], sigma_ancilla[3])
                    if i > 0 and i < 7:
                        w_input = [W[W_idx - 16], sigma_ancilla[2], sigma_ancilla[3]]
                    else:
                        w_input = [W[W_idx - 16], W[W_idx - 7], sigma_ancilla[2], sigma_ancilla[3]]
                    ww = eng.allocate_qureg(64)
                    ww = csa_ww(eng, w_input, add_ancilla1[2], ww)
                    W.append(ww)


            if 2 <= i <= 64:
                w_sigma(1, 8, 7, W[W_idx - 15 - 1], sigma_ancilla[6])  # dag
                w_sigma(19, 61, 6, W[W_idx - 2 - 1], sigma_ancilla[7])  # dag


            if 52 <= i <= 70 and dag_w_idx >= 16:
                t = dag_w_idx
                i_orig = t - 15

                w_sigma(1, 8, 7, W[t - 15], dag_sigma_anc[0])
                w_sigma(19, 61, 6, W[t - 2], dag_sigma_anc[1])

                if 0 < i_orig < 7:
                    input_dag = [W[t - 16], dag_sigma_anc[0], dag_sigma_anc[1]]
                elif 10 <= i_orig < 16:
                    input_dag = [W[t - 7], dag_sigma_anc[0], dag_sigma_anc[1]]
                elif i_orig % 2 == 0:
                    input_dag = [W[t - 16], dag_sigma_anc[0], W[t - 7], dag_sigma_anc[1]]
                else:
                    input_dag = [W[t - 16], W[t - 7], dag_sigma_anc[0], dag_sigma_anc[1]]

                W[t] = csa2_d(eng, input_dag, dag_ancilla1, W[t])

                w_sigma(1, 8, 7, W[t - 15], dag_sigma_anc[0])  # dag
                w_sigma(19, 61, 6, W[t - 2], dag_sigma_anc[1])  # dag
                free_pool.append(W[t])
                dag_w_idx -= 1


            pre_idx = i % 3

            check_clean(eng, [pre_result[pre_idx], pre_anc[0]], "K+W slot")
            outDraper_const(eng, SHA512_K_const(eng, i + 1), W[i + 1], pre_anc[0], pre_result[pre_idx])


            if i >= 2:
                prev2_pre_idx = (i - 2) % 3
                outDraper_const_dag(eng, SHA512_K_const(eng, i - 1), W[i - 1], pre_anc[1],
                                    pre_result[prev2_pre_idx])

            # reset pre_round_qubits
            copy(b0, a1)  # a1 reset
            copy(c0, b1)  # b1 reset
            copy(d0, c1)  # c1 reset
            copy(e0, updated_d1)  # updated_d1 reset
            copy(f0, e1)  # e1 reset
            copy(g0, f1)  # f1 reset
            copy(h0, g1)  # g1 reset
            copy(a0, updated_h1)  # updated_h1 reset
            check_clean(eng, [a1, b1, c1, updated_d1, e1, f1, g1, updated_h1], "register set before reload")

            copy(a0, a1)
            copy(b0, b1)
            copy(c0, c1)
            copy(updated_d0, updated_d1)
            copy(e0, e1)
            copy(f0, f1)
            copy(g0, g1)
            copy(updated_h0, updated_h1)

        if i != 0:
            W_idx += 1

        if i == 0:
            a1, b1, c1, d1, e1, f1, g1, h1 = h1, a1, b1, c1, d1, e1, f1, g1

        if i != 0 and i % 2 == 0:
            a1, b1, c1, d1, e1, f1, g1, h1 = updated_h1, a1, b1, c1, updated_d1, e1, f1, g1

        if i % 2 == 1:
            a0, b0, c0, d0, e0, f0, g0, h0 = updated_h0, a0, b0, c0, updated_d0, e0, f0, g0

        if resource_check != 1 and verify_mode != 1:
            print('\n')
            print("round", i)
            if i % 2 == 0:
                print_hex(eng, a1, 64)
                print_hex(eng, b1, 64)
                print_hex(eng, c1, 64)
                print_hex(eng, d1, 64)
                print_hex(eng, e1, 64)
                print_hex(eng, f1, 64)
                print_hex(eng, g1, 64)
                print_hex(eng, h1, 64)
            else:
                print_hex(eng, a0, 64)
                print_hex(eng, b0, 64)
                print_hex(eng, c0, 64)
                print_hex(eng, d0, 64)
                print_hex(eng, e0, 64)
                print_hex(eng, f0, 64)
                print_hex(eng, g0, 64)
                print_hex(eng, h0, 64)

    if verify_mode == 1:
        global collected_words
        collected_words = [
            measure_word(eng, a0, 64), measure_word(eng, b0, 64),
            measure_word(eng, c0, 64), measure_word(eng, d0, 64),
            measure_word(eng, e0, 64), measure_word(eng, f0, 64),
            measure_word(eng, g0, 64), measure_word(eng, h0, 64),
        ]
    elif resource_check != 1:
        print('\n')
        print("Final Hash (SHA-512):")
        print_hex(eng, a0, 64)
        print_hex(eng, b0, 64)
        print_hex(eng, c0, 64)
        print_hex(eng, d0, 64)
        print_hex(eng, e0, 64)
        print_hex(eng, f0, 64)
        print_hex(eng, g0, 64)
        print_hex(eng, h0, 64)
    
    else:
        print("round ", i)


def SHA512_preprocessing(msg, q_msg):
    global msg_bin_arr


    length = len(msg)
    msg_bin = []

    for i in range(length):
        msg_bin += make_list(ord(msg[i]), 8)
    length = len(msg_bin)
    msg_bin += ['1']

    for i in range(length + 1, 896):
        msg_bin += ['0']

    len_arr = make_list(length, 128)
    msg_bin += len_arr

    msg_bin_arr = msg_bin

    if resource_check != 1:
        for i in range(16):
            init_Ws(q_msg, i)


def init_Ws(W, idx):

    for i in range(64):
        if msg_bin_arr[idx * 64 + i] == '1':
            X | W[idx][63 - i]


def sha512(eng, msg="abc"):
    """Top-level SHA-512 quantum circuit.

    Flow:
      1. Allocate 8 x 64-qubit working variable registers (H[0]..H[7])
      2. Allocate 16 x 64-qubit message schedule registers (W[0]..W[15])
      3. Initialize H with SHA-512 initial hash values (FIPS 180-4 constants)
      4. Preprocess message (padding) and load into W registers
      5. Run SHA512_Compression for 80 rounds

    Simulation output note:
      This circuit computes the SHA-512 compression function only.
      The simulation prints the compression output (a, b, ..., h after 80 rounds),
      NOT the full SHA-512 hash. The full hash is: IV[i] + compression_output[i] (mod 2^64).

      SHA-512 IV = [6a09e667f3bcc908, bb67ae8584caa73b, 3c6ef372fe94f82b, a54ff53a5f1d36f1,
                    510e527fade682d1, 9b05688c2b3e6c1f, 1f83d9abfb41bd6b, 5be0cd19137e2179]

      Verification (compression output for "" empty string):
        Circuit output: 6579facd8b32efb5 35ec79cb51a2d8cc 99b1f0920cc21db1 dea4b3e7744fb2dd
                        f6c27ebcaf9f6fdf 647db0465c408010 443558114bffbd16 49576561e5a9b8c5
        IV + output   : cf83e1357eefb8bd f1542850d66d8007 d620e4050b5715dc 83f4a921d36ce9ce
                        47d0d13c5d85f2b0 ff8318d2877eec2f 63b931bd47417a81 a538327af927da3e
        SHA-512("")   : cf83e1357eefb8bd f1542850d66d8007 d620e4050b5715dc 83f4a921d36ce9ce
                        47d0d13c5d85f2b0 ff8318d2877eec2f 63b931bd47417a81 a538327af927da3e ✓
    """
    H = []
    W = []

    for i in range(8):
        H.append(eng.allocate_qureg(64))

    for i in range(16):
        W.append(eng.allocate_qureg(64))

    for i in range(8):
        SHA512_init_H(eng, H, i)
    SHA512_preprocessing(msg, W)

    SHA512_Compression(eng, H, W)
    ### Final feed-forward (IV + compression output) is applied in software
    ### during verification, not inside the quantum circuit. See verify_sha512().


SHA512_IV = [0x6a09e667f3bcc908, 0xbb67ae8584caa73b, 0x3c6ef372fe94f82b, 0xa54ff53a5f1d36f1,
             0x510e527fade682d1, 0x9b05688c2b3e6c1f, 0x1f83d9abfb41bd6b, 0x5be0cd19137e2179]
MASK64 = (1 << 64) - 1


def run_circuit_compression(msg, reuse_check=False):
    global TD, resource_check, verify_mode, collected_words
    global ancilla_check, reuse_checks, reuse_failures, reuse_qubits
    TD = 0
    resource_check = 0
    verify_mode = 1
    collected_words = []
    ancilla_check = 1 if reuse_check else 0
    reuse_checks = {}
    reuse_failures = []
    reuse_qubits = 0
    eng = MainEngine(ClassicalSimulator())
    sha512(eng, msg)
    eng.flush()
    return list(collected_words)


def verify_sha512(msg_bytes, expected_hex, reuse_check=False):
    """Full SHA-512 = (IV[i] + compression_output[i]) mod 2^64, compared to the
    published NIST digest (FIPS 180-4 / CAVP). hashlib independently
    cross-checks the expected value before the circuit runs."""
    import hashlib
    assert hashlib.sha512(msg_bytes).hexdigest() == expected_hex, \
        "expected digest disagrees with the hashlib reference"
    comp = run_circuit_compression(msg_bytes.decode("latin-1"), reuse_check)
    digest_words = [(SHA512_IV[i] + comp[i]) & MASK64 for i in range(8)]
    circuit_hex = "".join("%016x" % w for w in digest_words)
    ok = (circuit_hex == expected_hex)
    return circuit_hex, ok, comp, dict(reuse_checks), list(reuse_failures), reuse_qubits


if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "resource"

    if mode in ("verify", "reusecheck"):
        do_reuse = (mode == "reusecheck")
        # Single-block NIST test vectors: the FIPS 180-4 example and
        # CAVP SHA512ShortMsg.rsp entries (Len = 0, 8, 440 bits).
        # Expected digests are the published values.
        vectors = [
            ('"abc" (FIPS 180-4 example)', b"abc",
             "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea2"
             "0a9eeee64b55d39a2192992a274fc1a836ba3c23a3feebbd"
             "454d4423643ce80e2a9ac94fa54ca49f"),
            ('"" (empty; CAVP ShortMsg Len=0)', b"",
             "cf83e1357eefb8bdf1542850d66d8007d620e4050b5715dc"
             "83f4a921d36ce9ce47d0d13c5d85f2b0ff8318d2877eec2f"
             "63b931bd47417a81a538327af927da3e"),
            ("CAVP ShortMsg Len=8", bytes.fromhex("21"),
             "3831a6a6155e509dee59a7f451eb35324d8f8f2df6e37088"
             "94740f98fdee23889f4de5adb0c5010dfb555cda77c8ab5d"
             "c902094c52de3278f35a75ebc25f093a"),
            ("CAVP ShortMsg Len=440",
             bytes.fromhex("ec2a92e47f692b53c1355475c71ceff0b0952a8b3541b293"
                           "8270247d44e7c5cc04e17236b353da028674eab4047d89ec"
                           "5dad868cfd91ce"),
             "c83aca6147bfcbbc72c377efa8d53654ba0830c5a6a89e1d"
             "2a19b713e68fb534640deb833ca512247166dd273b5897e5"
             "7d526f88eef58f6ff97baee0b4ee5644"),
        ]
        print("=== SHA-512 quantum-circuit verification vs NIST test vectors ===\n")
        all_ok = True
        lines = []
        for label, m, expected in vectors:
            circuit_hex, ok, comp, checks, fails, nq = verify_sha512(m, expected, do_reuse)
            anc_ok = not fails
            all_ok = all_ok and ok and (not do_reuse or anc_ok)
            comp_hex = "".join("%016x" % w for w in comp)
            block = (
                "Input            : %s\n" % label +
                "Msg (hex)        : %s\n" % (m.hex() if m else "(empty)") +
                "Compression out  : %s\n" % comp_hex +
                "Circuit + IV     : %s\n" % circuit_hex +
                "NIST SHA-512     : %s\n" % expected +
                "Match            : %s\n" % ("PASS" if ok else "FAIL")
            )
            if do_reuse:
                block += (
                    "Ancilla reuse    : %s (%d reuse events, %d qubits read |0>: %s)\n" % (
                    "PASS" if anc_ok else "FAIL at " + ", ".join(sorted(set(fails))),
                    sum(checks.values()), nq,
                    ", ".join("%s %d" % kv for kv in sorted(checks.items())))
                )
            print(block)
            lines.append(block)
        verdict = "ALL TEST VECTORS PASSED" if all_ok else "VERIFICATION FAILED"
        print("=== %s ===" % verdict)
        if do_reuse:
            with open("Result-sha512-verify.txt", "w") as f:
                f.write("SHA-512 Quantum Circuit -- NIST Test-Vector Verification (FIPS 180-4 / CAVP)\n")
                f.write("==================================================================\n\n")
                f.write("\n".join(lines))
                f.write("\n=== %s ===\n" % verdict)
        sys.exit(0 if all_ok else 1)

    elif mode == "simulate":
        TD = 0
        resource_check = 0
        print("SHA-512 Simulation")
        eng = MainEngine(ClassicalSimulator())
        sha512(eng)
        eng.flush()
    else:
        TD = 1
        resource_check = 1
        print("SHA-512 Resource Estimation")
        Resource = ResourceCounter()
        eng = MainEngine(Resource)
        sha512(eng)
        eng.flush()
        print(Resource)
