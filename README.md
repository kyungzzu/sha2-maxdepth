# Depth-Optimized Quantum Circuits for SHA-2 under NIST MAXDEPTH

Code for the paper of the same title, to appear in IACR Transactions on
Cryptographic Hardware and Embedded Systems (TCHES): ProjectQ implementations of
the SHA-256, SHA-384, and SHA-512 quantum circuits, the NIST test-vector
validation, and the scripts behind the resource tables.

## Contents

| Path | Description |
|------|-------------|
| `implementation/` | The SHA-256/384/512 circuits. The default mode prints the gate counts, qubit count, and full depth of Table 8. |
| `verification/` | The same circuits with a test-vector harness, and the validation outputs in `results/`. |
| `estimation/` | Scripts for Tables 10–12 and the T-layer demand check of Section 4.2. |

## Requirements

Python 3 (tested with 3.9) and [ProjectQ](https://projectq.readthedocs.io/) 0.8.0.

```bash
pip install projectq
```

## Resource estimation (Table 8)

```bash
cd implementation
python sha256.py    # likewise sha384.py, sha512.py
```

Each Toffoli gate is decomposed into 7 T, 6 CNOT, and 2 H gates (T-depth 4,
full depth 8; Amy et al., IEEE TCAD 2013), and ProjectQ's `ResourceCounter`
reports the totals:

| Variant | Qubits | CNOT | 1qCliff | T | Full depth |
|---------|-------:|-----:|--------:|--:|-----------:|
| SHA-256 | 7,245 | 751,546 | 92,147 | 516,213 | 7,504 |
| SHA-384 | 17,633 | 1,995,746 | 249,214 | 1,400,609 | 10,783 |
| SHA-512 | 17,633 | 1,995,746 | 249,235 | 1,400,609 | 10,783 |

The qubit count in Table 8 is the `Allocate` value (every qubit the circuit
uses). The `Max. width` line is not the circuit width.

The global flag `TD` selects the Toffoli implementation: `TD=1` (default) for
the decomposition above, `TD=0` for native Toffoli gates (used for simulation).

## NIST test-vector validation

```bash
cd verification
python sha256_verify.py verify        # NIST test-vector digest check
python sha256_verify.py reusecheck    # digest check + |0> check at each register reuse
# likewise sha384_verify.py, sha512_verify.py
```

The script builds the full gate-level circuit for each test message and runs it
on ProjectQ's `ClassicalSimulator` with native Toffoli gates. It reads the eight
compression-output words after the last round and adds the initial hash value
classically. As in prior quantum SHA-2 work, this fixed feed-forward addition is
not part of the quantum oracle. The resulting digest is compared with the NIST
value. In `reusecheck` mode, the same run additionally reads every register at
the moment it is reused (the reused output registers of Section 3.6, the
alternating register sets, and the K+W and Maj output slots) and checks that
it is |0⟩. The script exits with a nonzero code if any digest or reuse check
fails.

| Variant | Test vectors (FIPS 180-4, CAVP ShortMsg) | Digest | Reuse checks (per vector) |
|---------|------------------------------------------|--------|---------------------------|
| SHA-256 | "abc", empty message, Len = 8, Len = 256 | 4/4 pass | 214/214 pass |
| SHA-384 | "abc", empty message, Len = 8, Len = 440 | 4/4 pass | 262/262 pass |
| SHA-512 | "abc", empty message, Len = 8, Len = 440 | 4/4 pass | 262/262 pass |

The tested inputs, the expected and obtained digests, and the reuse-check
results are in `verification/results/Result-<variant>-verify.txt`, produced
with `reusecheck`. A `reusecheck` run writes the same file to the working
directory for comparison. On a laptop, a
run takes about 25 minutes for SHA-256 and about 2 hours each for SHA-384 and
SHA-512.

## Fault-tolerant estimation (Tables 10–12)

```bash
cd estimation
python verify_maxdepth_table.py   # Table 10: MAXDEPTH-parallelized qubit counts
python compute_ft_tables_peak.py  # Tables 11-12: surface-code and qLDPC estimates
python verify_ft_model.py         # cost model checked against published examples
python compute_phi.py all         # peak and mean T gates per T-layer (Section 4.2)
```

The factory count used in Tables 11–12 is Φ = the peak number of T gates in
one T-layer of the ASAP schedule of the decomposed circuits: 478 for SHA-256
and 972 for SHA-384/512, as measured by `compute_phi.py` (one T-layer per
distillation round, one magic state per factory per round).
`compute_phi.py` rebuilds the circuits from `implementation/` and takes about
20 minutes for SHA-256 and longer for SHA-384/512. The other scripts finish
in seconds.
