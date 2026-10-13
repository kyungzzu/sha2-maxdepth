# SHA-256 Quantum Circuit (Depth-Optimized)
#
# Implements a quantum circuit for SHA-256 using ProjectQ.
#
# Usage:
#   python sha256.py            # Resource estimation (default)
#   python sha256.py simulate   # Functional simulation
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
    n = 32
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
    copy_ancilla = ancilla[-32:]
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


def SHA256_init_H(eng, H, idx):
    H_list = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]

    bit_list = make_list(H_list[idx], 32)
    for j in range(32):
        if bit_list[j] == '1':

            X | H[idx][31 - j]

    return H[idx]


def K_set(eng, K, q):
    for i in range(len(q)):
        if K[i] == '1':
            X | q[len(q) - 1 - i]


SHA256_K_VALUES = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
    0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
    0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
    0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
]


def SHA256_K(eng, idx):
    return make_list(SHA256_K_VALUES[idx], 32)


def SHA256_K_const(eng, idx):
    K = make_list(SHA256_K_VALUES[idx], 32)
    K.reverse()
    return K


def w_sigma(rr0, rr1, ss, input, output):
    ss_len = 32 - ss
    for i in range(32):
        CNOT | (input[(rr0 + i) % 32], output[i])
    for i in range(32):
        CNOT | (input[(rr1 + i) % 32], output[i])
    for i in range(32):
        if i < ss_len:
            CNOT | (input[i + ss], output[i])


def r_sigma(rr0, rr1, rr2, input, output):
    for i in range(32):
        CNOT | (input[(rr0 + i) % 32], output[i])
    for i in range(32):
        CNOT | (input[(rr1 + i) % 32], output[i])
    for i in range(32):
        CNOT | (input[(rr2 + i) % 32], output[i])


def maj_out(x, y, z, result, tmp=0, ancilla=0):
    for i in range(32):
        CNOT | (z[i], result[i])

    for i in range(32):
        CNOT | (z[i], y[i])

    for i in range(32):
        CNOT | (result[i], x[i])

    if TD == 2:
        for i in range(32):
            toffoli_gate(x[i], y[i], tmp[i], ancilla[i])
            CNOT | (tmp[i], result[i])
    else:
        for i in range(32):
            toffoli_gate(x[i], y[i], result[i])

    for i in range(32):
        CNOT | (z[i], x[i])

    for i in range(32):
        CNOT | (z[i], y[i])


def maj_out_dag(x, y, z, result, tmp=0, ancilla=0):
    for i in range(32):
        CNOT | (z[i], y[i])

    for i in range(32):
        CNOT | (z[i], x[i])

    if TD == 2:
        for i in range(32):
            CNOT | (tmp[i], result[i])
            toffoli_gate(x[i], y[i], tmp[i], ancilla[i])
    else:
        for i in range(32):
            toffoli_gate(x[i], y[i], result[i])

    for i in range(32):
        CNOT | (result[i], x[i])

    for i in range(32):
        CNOT | (z[i], y[i])

    for i in range(32):
        CNOT | (z[i], result[i])


def ch_out(x, y, z, result, tmp=0, ancilla=0):
    for i in range(32):
        CNOT | (z[i], result[i])

    for i in range(32):
        CNOT | (y[i], z[i])

    if TD == 2:
        for i in range(32):
            toffoli_gate(x[i], z[i], tmp[i], ancilla[i])
            CNOT | (tmp[i], result[i])
    else:
        for i in range(32):
            toffoli_gate(x[i], z[i], result[i])

    for i in range(32):
        CNOT | (y[i], z[i])


def ch_out_dag(x, y, z, result, tmp=0):
    for i in range(32):
        CNOT | (y[i], z[i])
    if TD == 2:
        for i in range(32):
            CNOT | (tmp[i], result[i])
            toffoli_gate(x[i], z[i], tmp[i], 0, False)
    else:
        for i in range(32):
            toffoli_gate(x[i], z[i], result[i])
    for i in range(32):
        CNOT | (y[i], z[i])

    for i in range(32):
        CNOT | (z[i], result[i])


def copy(x, y):
    for i in range(32):
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


def SHA256_Compression(eng, H, W):
    """SHA-256 compression function over 64 rounds.
    H:   list of 8 x 32-qubit registers (working variables, modified in-place)
    W:   list of 16 x 32-qubit registers (message schedule, first 16 words)
    """
    even_add_ancilla = []
    tmp = []
    tmp.append(eng.allocate_qureg(153)) # 6 CSA
    tmp.append(eng.allocate_qureg(75)) # outDraper_30bit
    even_add_ancilla.append(tmp)

    tmp = []
    tmp.append(eng.allocate_qureg(92)) # 4 CSA
    tmp.append(eng.allocate_qureg(75)) # outDraper_30bit
    even_add_ancilla.append(tmp)

    tmp = []
    tmp.append(eng.allocate_qureg(62)) # 4 CSA
    tmp.append(eng.allocate_qureg(78)) # outDraper_31bit
    even_add_ancilla.append(tmp)

    odd_add_ancilla = []
    tmp = []
    tmp.append(eng.allocate_qureg(153)) # 6 CSA
    tmp.append(eng.allocate_qureg(75)) # outDraper_30bit
    odd_add_ancilla.append(tmp)

    tmp = []
    tmp.append(eng.allocate_qureg(92)) # 4 CSA
    tmp.append(eng.allocate_qureg(75)) # outDraper_30bit
    odd_add_ancilla.append(tmp)

    tmp = []
    tmp.append(eng.allocate_qureg(62)) # 4 CSA
    tmp.append(eng.allocate_qureg(78)) # outDraper_31bit
    odd_add_ancilla.append(tmp)

    maj_ch_tmp = []
    maj_ch_tmp.append(eng.allocate_qureg(32))
    maj_ch_tmp.append(eng.allocate_qureg(32))

    sigma_ancilla = []
    for i in range(8):
        sigma_ancilla.append(eng.allocate_qureg(32))

    pre_result = []
    for i in range(3):
        pre_result.append(eng.allocate_qureg(32))

    a0 = H[0]
    b0 = H[1]
    c0 = H[2]
    d0 = H[3]
    e0 = H[4]
    f0 = H[5]
    g0 = H[6]
    h0 = H[7]

    a1 = eng.allocate_qureg(32)
    b1 = eng.allocate_qureg(32)
    c1 = eng.allocate_qureg(32)
    d1 = eng.allocate_qureg(32)
    e1 = eng.allocate_qureg(32)
    f1 = eng.allocate_qureg(32)
    g1 = eng.allocate_qureg(32)
    h1 = eng.allocate_qureg(32)

    maj_result = []
    ch_result = []
    maj_result.append(eng.allocate_qureg(32))
    maj_result.append(eng.allocate_qureg(32))
    ch_result.append(eng.allocate_qureg(32))
    ch_result.append(eng.allocate_qureg(32))

    W_idx = 16


    dag_sigma_anc = [eng.allocate_qureg(32), eng.allocate_qureg(32)]
    dag_ancilla1 = [eng.allocate_qureg(62), eng.allocate_qureg(78)]
    free_pool = []
    dag_w_idx = 34
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


    a0_sigma_fanout = eng.allocate_qureg(32)
    e0_sigma_fanout = eng.allocate_qureg(32)
    a1_sigma_fanout = eng.allocate_qureg(32)
    e1_sigma_fanout = eng.allocate_qureg(32)

    for i in range(64):
        if i % 2 == 0:
            add_ancilla1 = even_add_ancilla
            add_ancilla2 = odd_add_ancilla
        else:
            add_ancilla1 = odd_add_ancilla
            add_ancilla2 = even_add_ancilla

        if i == 0:
            # Forward round R_0

            K_q = dag_sigma_anc[0]
            K = SHA256_K(eng, i)
            K_set(eng, K, K_q)

            copy(a0, a0_sigma_fanout)
            copy(e0, e0_sigma_fanout)
            r_sigma(2, 13, 22, a0_sigma_fanout, sigma_ancilla[0])  # sigma_ancilla[0] = Σ0(a)
            r_sigma(6, 11, 25, e0_sigma_fanout, sigma_ancilla[1])  # sigma_ancilla[1] = Σ1(e)
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
            outDraper_const(eng, SHA256_K_const(eng, i + 1), W[i + 1], pre_anc[0], pre_result[pre_idx])


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
            if i != 63:
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
                    r_sigma(6, 11, 25, e0_sigma_fanout, sigma_ancilla[1])  # dag
                    r_sigma(2, 13, 22, a0_sigma_fanout, sigma_ancilla[0])  # dag
                    copy(e0, e0_sigma_fanout)  # dag
                    copy(a0, a0_sigma_fanout)  # dag


                else:
                    deferredAdd(eng, even_DrapOut_stack1[0], even_DrapOut_stack1[1], even_DrapOut_stack1[2],
                                        even_DrapOut_stack1[3])
                    deferredAdd(eng, even_DrapOut_stack2[0], even_DrapOut_stack2[1], even_DrapOut_stack2[2],
                                        even_DrapOut_stack2[3])
                    if 4 <= i <= 49:
                        deferredAdd(eng, even_DrapOut_stack3[0], even_DrapOut_stack3[1], even_DrapOut_stack3[2],
                                            even_DrapOut_stack3[3])

                    if 4 <= i <= 49:
                        reverse_adders(even_stack3)
                    reverse_adders(even_stack2)
                    reverse_adders(even_stack1)

                    copy(e0, e0_sigma_fanout)
                    copy(a0, a0_sigma_fanout)
                    ch_out_dag(e0, f0, g0, ch_result[0], maj_ch_tmp[1])
                    maj_out_dag(a0, b0, c0, maj_result[0], maj_ch_tmp[0])
                    r_sigma(6, 11, 25, e0_sigma_fanout, sigma_ancilla[1])  # dag
                    r_sigma(2, 13, 22, a0_sigma_fanout, sigma_ancilla[0])  # dag
                    copy(e0, e0_sigma_fanout)
                    copy(a0, a0_sigma_fanout)


            # Forward round R

            copy(a1, a1_sigma_fanout)
            copy(e1, e1_sigma_fanout)
            r_sigma(2, 13, 22, a1_sigma_fanout, sigma_ancilla[4])  # sigma_ancilla[4] = Σ0(a)
            r_sigma(6, 11, 25, e1_sigma_fanout, sigma_ancilla[5])  # sigma_ancilla[5] = Σ1(e)
            maj_out(a1, b1, c1, maj_result[1], maj_ch_tmp[0], add_ancilla2[1][0])  # maj_result = Maj(a,b,c)
            ch_out(e1, f1, g1, ch_result[1], maj_ch_tmp[1], add_ancilla2[1][1])  # ch_result = Ch(e,f,g)
            copy(a1, a1_sigma_fanout)
            copy(e1, e1_sigma_fanout)


            pre_idx = (i - 1) % 3
            input1 = [h1, sigma_ancilla[5], ch_result[1], maj_result[1], pre_result[pre_idx], sigma_ancilla[4]]
            input2 = [pre_result[pre_idx], d1]

            if 3 <= i <= 48:
                w_sigma(7, 18, 3, W[W_idx - 15], sigma_ancilla[6])  # sigma_ancilla[6] = σ0(W[i-15])
                w_sigma(17, 19, 10, W[W_idx - 2], sigma_ancilla[7])  # sigma_ancilla[7] = σ1(W[i-2])

                if 37 <= i <= 48 and len(free_pool) > 0:
                    output = [0, 0, free_pool.pop(0)]
                else:
                    output = [0, 0, 0]

                if i > 0 and i < 7:
                    input3 = [W[W_idx - 16], sigma_ancilla[6], sigma_ancilla[7]]
                elif i >= 10 and i < 16:
                    input3 = [W[W_idx - 7], sigma_ancilla[6], sigma_ancilla[7]]
                else:
                    input3 = [W[W_idx - 16], W[W_idx - 7], sigma_ancilla[6], sigma_ancilla[7]]

                updated_h1, updated_d1, ww, odd_stack1, odd_stack2, odd_stack3, odd_DrapOut_stack1, odd_DrapOut_stack2, odd_DrapOut_stack3 = csa1_0(
                    eng, input1, input2, input3,
                    add_ancilla1[0], add_ancilla1[1],
                    add_ancilla1[2], output)
                W.append(ww)
            else:
                if 50 <= i <= 56:
                    if i <= 51:
                        output = [pop_anc2_output_reuse(32), pop_anc2_output_reuse(32)]
                    else:
                        output = [free_pool.pop(0) if len(free_pool) > 0 else 0, pop_anc2_output_reuse(32)]
                elif i == 57 and len(free_pool) > 0:
                    output = [free_pool.pop(0), 0]
                elif i == 58 and len(free_pool) > 0:
                    output = [free_pool.pop(0), 0]
                elif 59 <= i <= 61 and late_output_reuse_idx + 64 <= len(late_output_reuse_pool):
                    output = [
                        late_output_reuse_pool[late_output_reuse_idx:late_output_reuse_idx + 32],
                        late_output_reuse_pool[late_output_reuse_idx + 32:late_output_reuse_idx + 64]
                    ]
                    late_output_reuse_idx += 64
                else:
                    output = [0, 0]

                updated_h1, updated_d1, odd_stack1, odd_stack2, odd_DrapOut_stack1, odd_DrapOut_stack2 = csa1_0_no_w(
                    eng, input1, input2,
                    add_ancilla1[0], add_ancilla1[1], output)

                if i <= 2:
                    w_sigma(7, 18, 3, W[W_idx - 15], sigma_ancilla[6])
                    w_sigma(17, 19, 10, W[W_idx - 2], sigma_ancilla[7])
                    if i > 0 and i < 7:
                        w_input = [W[W_idx - 16], sigma_ancilla[6], sigma_ancilla[7]]
                    else:
                        w_input = [W[W_idx - 16], W[W_idx - 7], sigma_ancilla[6], sigma_ancilla[7]]
                    ww = eng.allocate_qureg(32)
                    ww = csa_ww(eng, w_input, add_ancilla1[2], ww)
                    W.append(ww)


            if 3 <= i <= 49:
                w_sigma(7, 18, 3, W[W_idx - 15 - 1], sigma_ancilla[2])
                w_sigma(17, 19, 10, W[W_idx - 2 - 1], sigma_ancilla[3])


            if 36 <= i <= 54 and dag_w_idx >= 16:
                t = dag_w_idx
                i_orig = t - 15

                w_sigma(7, 18, 3, W[t - 15], dag_sigma_anc[0])
                w_sigma(17, 19, 10, W[t - 2], dag_sigma_anc[1])

                if 0 < i_orig < 7:
                    input_dag = [W[t - 16], dag_sigma_anc[0], dag_sigma_anc[1]]
                elif 10 <= i_orig < 16:
                    input_dag = [W[t - 7], dag_sigma_anc[0], dag_sigma_anc[1]]
                elif i_orig % 2 == 0:
                    input_dag = [W[t - 16], dag_sigma_anc[0], W[t - 7], dag_sigma_anc[1]]
                else:
                    input_dag = [W[t - 16], W[t - 7], dag_sigma_anc[0], dag_sigma_anc[1]]

                W[t] = csa2_d(eng, input_dag, dag_ancilla1, W[t])

                w_sigma(7, 18, 3, W[t - 15], dag_sigma_anc[0])
                w_sigma(17, 19, 10, W[t - 2], dag_sigma_anc[1])
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

            copy(a1, a0)
            copy(b1, b0)
            copy(c1, c0)
            copy(updated_d1, updated_d0)
            copy(e1, e0)
            copy(f1, f0)
            copy(g1, g0)
            copy(updated_h1, updated_h0)

            if i != 63:
                # operand reduction
                pre_idx = i % 3
                outDraper_const(eng, SHA256_K_const(eng, i + 1), W[i + 1], pre_anc[0], pre_result[pre_idx])

                if i >= 2:
                    prev2_pre_idx = (i - 2) % 3
                    outDraper_const_dag(eng, SHA256_K_const(eng, i - 1), W[i - 1], pre_anc[1],
                                        pre_result[prev2_pre_idx])

        if i > 0 and i % 2 == 0:
            # inverse operation for previous round  (R_dag)
            deferredAdd(eng, odd_DrapOut_stack1[0], odd_DrapOut_stack1[1], odd_DrapOut_stack1[2],
                                odd_DrapOut_stack1[3])
            deferredAdd(eng, odd_DrapOut_stack2[0], odd_DrapOut_stack2[1], odd_DrapOut_stack2[2],
                                odd_DrapOut_stack2[3])
            if 4 <= i <= 49:
                deferredAdd(eng, odd_DrapOut_stack3[0], odd_DrapOut_stack3[1], odd_DrapOut_stack3[2],
                                    odd_DrapOut_stack3[3])

            if 4 <= i <= 49:
                reverse_adders(odd_stack3)
            reverse_adders(odd_stack2)
            reverse_adders(odd_stack1)

            ch_out_dag(e1, f1, g1, ch_result[1], maj_ch_tmp[1])
            maj_out_dag(a1, b1, c1, maj_result[1], maj_ch_tmp[0])
            r_sigma(6, 11, 25, e1_sigma_fanout, sigma_ancilla[5])  # dag
            r_sigma(2, 13, 22, a1_sigma_fanout, sigma_ancilla[4])  # dag
            copy(e1, e1_sigma_fanout)  # dag
            copy(a1, a1_sigma_fanout)  # dag


            # Forward round R

            copy(a0, a0_sigma_fanout)
            copy(e0, e0_sigma_fanout)
            r_sigma(2, 13, 22, a0_sigma_fanout, sigma_ancilla[0])  # sigma_ancilla[0] = Σ0(a)
            maj_out(a0, b0, c0, maj_result[0], maj_ch_tmp[0], add_ancilla2[0][0])  # maj_result = Maj(a,b,c)
            r_sigma(6, 11, 25, e0_sigma_fanout, sigma_ancilla[1])  # sigma_ancilla[1] = Σ1(e)
            ch_out(e0, f0, g0, ch_result[0], maj_ch_tmp[1], add_ancilla2[0][1])  # ch_result = Ch(e,f,g)
            copy(a0, a0_sigma_fanout)
            copy(e0, e0_sigma_fanout)

            # pre_result = W[i]+K[i]
            pre_idx = (i - 1) % 3
            input1 = [h0, sigma_ancilla[1], ch_result[0], maj_result[0], pre_result[pre_idx], sigma_ancilla[0]]
            input2 = [pre_result[pre_idx], d0]

            if 3 <= i <= 48:
                w_sigma(7, 18, 3, W[W_idx - 15], sigma_ancilla[2])  # sigma_ancilla[2] = σ0(W[i-15])
                w_sigma(17, 19, 10, W[W_idx - 2], sigma_ancilla[3])  # sigma_ancilla[3] = σ1(W[i-2])

                if 37 <= i <= 48 and len(free_pool) > 0:
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

                updated_h0, updated_d0, ww, even_stack1, even_stack2, even_stack3, even_DrapOut_stack1, even_DrapOut_stack2, even_DrapOut_stack3 = csa1_0(
                    eng, input1, input2, input3,
                    add_ancilla1[0], add_ancilla1[1],
                    add_ancilla1[2], output)
                W.append(ww)

            else:
                if 50 <= i <= 56:
                    if i <= 51:
                        output = [pop_anc2_output_reuse(32), pop_anc2_output_reuse(32)]
                    else:
                        output = [free_pool.pop(0) if len(free_pool) > 0 else 0, pop_anc2_output_reuse(32)]
                elif i == 57 and len(free_pool) > 0:
                    output = [free_pool.pop(0), 0]
                elif i == 58 and len(free_pool) > 0:
                    output = [free_pool.pop(0), 0]
                elif 59 <= i <= 61 and late_output_reuse_idx + 64 <= len(late_output_reuse_pool):
                    output = [
                        late_output_reuse_pool[late_output_reuse_idx:late_output_reuse_idx + 32],
                        late_output_reuse_pool[late_output_reuse_idx + 32:late_output_reuse_idx + 64]
                    ]
                    late_output_reuse_idx += 64
                else:
                    output = [0, 0]

                updated_h0, updated_d0, even_stack1, even_stack2, even_DrapOut_stack1, even_DrapOut_stack2 = csa1_0_no_w(
                    eng, input1, input2,
                    add_ancilla1[0], add_ancilla1[1], output)

                if i <= 2:
                    w_sigma(7, 18, 3, W[W_idx - 15], sigma_ancilla[2])
                    w_sigma(17, 19, 10, W[W_idx - 2], sigma_ancilla[3])
                    if i > 0 and i < 7:
                        w_input = [W[W_idx - 16], sigma_ancilla[2], sigma_ancilla[3]]
                    else:
                        w_input = [W[W_idx - 16], W[W_idx - 7], sigma_ancilla[2], sigma_ancilla[3]]
                    ww = eng.allocate_qureg(32)
                    ww = csa_ww(eng, w_input, add_ancilla1[2], ww)
                    W.append(ww)


            if 2 <= i <= 48:
                w_sigma(7, 18, 3, W[W_idx - 15 - 1], sigma_ancilla[6])  # dag
                w_sigma(17, 19, 10, W[W_idx - 2 - 1], sigma_ancilla[7])  # dag


            if 36 <= i <= 54 and dag_w_idx >= 16:
                t = dag_w_idx
                i_orig = t - 15

                w_sigma(7, 18, 3, W[t - 15], dag_sigma_anc[0])
                w_sigma(17, 19, 10, W[t - 2], dag_sigma_anc[1])

                if 0 < i_orig < 7:
                    input_dag = [W[t - 16], dag_sigma_anc[0], dag_sigma_anc[1]]
                elif 10 <= i_orig < 16:
                    input_dag = [W[t - 7], dag_sigma_anc[0], dag_sigma_anc[1]]
                elif i_orig % 2 == 0:
                    input_dag = [W[t - 16], dag_sigma_anc[0], W[t - 7], dag_sigma_anc[1]]
                else:
                    input_dag = [W[t - 16], W[t - 7], dag_sigma_anc[0], dag_sigma_anc[1]]

                W[t] = csa2_d(eng, input_dag, dag_ancilla1, W[t])

                w_sigma(7, 18, 3, W[t - 15], dag_sigma_anc[0])  # dag
                w_sigma(17, 19, 10, W[t - 2], dag_sigma_anc[1])  # dag
                free_pool.append(W[t])
                dag_w_idx -= 1


            pre_idx = i % 3

            outDraper_const(eng, SHA256_K_const(eng, i + 1), W[i + 1], pre_anc[0], pre_result[pre_idx])


            if i >= 2:
                prev2_pre_idx = (i - 2) % 3
                outDraper_const_dag(eng, SHA256_K_const(eng, i - 1), W[i - 1], pre_anc[1],
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

        if resource_check != 1:
            print('\n')
            print("round", i)
            if i % 2 == 0:
                print_hex(eng, a1, 32)
                print_hex(eng, b1, 32)
                print_hex(eng, c1, 32)
                print_hex(eng, d1, 32)
                print_hex(eng, e1, 32)
                print_hex(eng, f1, 32)
                print_hex(eng, g1, 32)
                print_hex(eng, h1, 32)
            else:
                print_hex(eng, a0, 32)
                print_hex(eng, b0, 32)
                print_hex(eng, c0, 32)
                print_hex(eng, d0, 32)
                print_hex(eng, e0, 32)
                print_hex(eng, f0, 32)
                print_hex(eng, g0, 32)
                print_hex(eng, h0, 32)

    if resource_check != 1:
        print('\n')
        print("Final Hash (SHA-256):")
        print_hex(eng, a0, 32)
        print_hex(eng, b0, 32)
        print_hex(eng, c0, 32)
        print_hex(eng, d0, 32)
        print_hex(eng, e0, 32)
        print_hex(eng, f0, 32)
        print_hex(eng, g0, 32)
        print_hex(eng, h0, 32)

    else:
        print("round ", i)

def SHA256_preprocessing(msg, q_msg):
    global msg_bin_arr


    length = len(msg)
    msg_bin = []

    for i in range(length):
        msg_bin += make_list(ord(msg[i]), 8)
    length = len(msg_bin)
    msg_bin += ['1']

    for i in range(length + 1, 448):
        msg_bin += ['0']

    len_arr = make_list(length, 64)
    msg_bin += len_arr

    msg_bin_arr = msg_bin

    if resource_check != 1:
        for i in range(16):
            init_Ws(q_msg, i)


def init_Ws(W, idx):

    for i in range(32):
        if msg_bin_arr[idx * 32 + i] == '1':
            X | W[idx][31 - i]


def sha256(eng):
    """SHA-256 quantum circuit.

    Allocates quantum registers, loads the message and initial hash values,
    then runs the compression function.

    Flow:
      1. Allocate 8 x 32-qubit working variable registers (H[0]..H[7])
      2. Allocate 16 x 32-qubit message schedule registers (W[0]..W[15])
      3. Initialize H with SHA-256 initial hash values (FIPS 180-4 constants)
      4. Preprocess message (padding) and load into W registers
      5. Run SHA256_Compression for 64 rounds

    Simulation output note:
      This circuit computes the SHA-256 compression function only.
      The simulation prints the compression output (a, b, ..., h after 64 rounds),
      NOT the full SHA-256 hash. The full hash is: IV[i] + compression_output[i] (mod 2^32).

      SHA-256 IV = [6a09e667, bb67ae85, 3c6ef372, a54ff53a,
                    510e527f, 9b05688c, 1f83d9ab, 5be0cd19]

      Verification (compression output for "" empty string):
        Circuit output: 79a6dddb dd946d8f 5e8d0156 f41fc3ea d69fef65 c9962ac0 8511bf70 1c71eb3c
        IV + output   : e3b0c442 98fc1c14 9afbf4c8 996fb924 27ae41e4 649b934c a495991b 7852b855
        SHA-256("")   : e3b0c442 98fc1c14 9afbf4c8 996fb924 27ae41e4 649b934c a495991b 7852b855 ✓
    """
    
    H = []
    W = []

    for i in range(8):
        H.append(eng.allocate_qureg(32))

    for i in range(16):
        W.append(eng.allocate_qureg(32))

    # Input message
    msg = "abc"

    for i in range(8):
        SHA256_init_H(eng, H, i)
    SHA256_preprocessing(msg, W)

    SHA256_Compression(eng, H, W)
    ### Constant addition operation performed at the final stage is omitted ###


if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "resource"

    if mode == "simulate":
        TD = 0
        resource_check = 0
        print("SHA-256 Simulation")
        eng = MainEngine(ClassicalSimulator())
        sha256(eng)
        eng.flush()
    else:
        TD = 1
        resource_check = 1
        print("SHA-256 Resource Estimation")
        Resource = ResourceCounter()
        eng = MainEngine(Resource)
        sha256(eng)
        eng.flush()
        print(Resource)
