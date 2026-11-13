"""Exact McNemar power (normal approximation to the chi-square test) + sign-test framing.

McNemar (chi-square, continuity-corrected) rejects H0 when:
    |b - c| >= 1 + z_{1-alpha/2} * sqrt(b+c)          (chi2_1, .95 = 3.8415)

Under H1: b ~ Bin(n, theta) indep c ~ Bin(n, psi), theta = P(A passes, B fails),
psi = P(A fails, B passes);  d = theta + psi (discordance rate), Delta = theta - psi.

Also the equivalent conditional framing: given m = b+c discordant pairs, the test is a
sign test on the win rate theta_cond = theta/(theta+psi) = 0.5 + Delta/(2d).
"""

import math
from math import comb, sqrt, erf

Z_ALPHA = 1.959963984540054   # two-sided alpha = 0.05
Z_BETA = 0.8416212335729143   # 80% power


def phi(x):
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def log_binom_pmf(k, n, p):
    if p <= 0.0:
        return 0.0 if k == 0 else -math.inf
    if p >= 1.0:
        return 0.0 if k == n else -math.inf
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
            + k * math.log(p) + (n - k) * math.log1p(-p))


def mcnemar_power(n, theta, psi):
    """Exact power of the continuity-corrected McNemar chi-square test."""
    total = 0.0
    for b in range(n + 1):
        lb = log_binom_pmf(b, n, theta)
        if lb < -700:
            continue
        pb = math.exp(lb)
        for c in range(n + 1):
            if b + c == 0:
                continue
            lc = log_binom_pmf(c, n, psi)
            if lc < -700:
                continue
            if abs(b - c) >= 1.0 + Z_ALPHA * sqrt(b + c):
                total += pb * math.exp(lc)
    return total


def min_n_for_power(delta, d, target=0.80):
    """Smallest n with power >= target (searched on a grid, then refined)."""
    theta = (d + delta) / 2.0
    psi = (d - delta) / 2.0
    if theta <= 0 or psi < 0:
        return None
    lo, hi = 10, 4000
    # coarse scan
    step = 20
    prev = None
    n = step
    while n <= hi:
        p = mcnemar_power(n, theta, psi)
        if p >= target:
            # binary search between prev and n
            a, b = (prev or step), n
            while b - a > 1:
                mid = (a + b) // 2
                if mcnemar_power(mid, theta, psi) >= target:
                    b = mid
                else:
                    a = mid
            return b
        prev = n
        n += step
    return None


def sign_test_formula_n(delta, d):
    """n from the conditional sign-test derivation: n = (z_a+z_b)^2 * d / Delta^2."""
    return ((Z_ALPHA + Z_BETA) ** 2) * d / (delta ** 2)


def detectable_delta(n, d):
    """Delta giving 80% power at sample size n (normal approximation)."""
    # solve  sqrt(n)*Delta = z_a*sqrt(d) + z_b*sqrt(Var), Var = d - (d^2 + Delta^2)/2
    Delta = 0.05
    for _ in range(200):
        var = d - (d * d + Delta * Delta) / 2.0
        if var <= 0:
            var = 1e-9
        rhs = Z_ALPHA * sqrt(d) + Z_BETA * sqrt(var)
        new = rhs / sqrt(n)
        if abs(new - Delta) < 1e-10:
            Delta = new
            break
        Delta = new
    return Delta


def mcnemar_power_closed(n, theta, psi):
    """Normal-approximation power, for comparison with the exact sum."""
    var = n * (theta * (1 - theta) + psi * (1 - psi))
    crit = Z_ALPHA * sqrt(n * (theta + psi))
    return phi((n * (theta - psi) - crit) / sqrt(var))


print("=" * 92)
print("TABLE A: Minimum paired tasks n for 80% power, two-sided alpha = 0.05")
print("         (exact continuity-corrected McNemar; sign-test derivation in brackets)")
print("=" * 92)
print(f"{'discordance d':>14} | {'Delta=5pp':>18} | {'Delta=10pp':>18} | {'Delta=15pp':>18}")
for d in [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50]:
    row = []
    for delta in [0.05, 0.10, 0.15]:
        n = min_n_for_power(delta, d)
        row.append(f"{n} [{sign_test_formula_n(delta, d):.0f}]")
    print(f"{d:>14.2f} | {row[0]:>18} | {row[1]:>18} | {row[2]:>18}")

print()
print("=" * 92)
print("TABLE B: Power at fixed n, Delta = 5 pp  (exact McNemar / normal approx)")
print("=" * 92)
ns = [200, 300, 400, 600, 800, 1000, 1200, 1600]
print(f"{'d':>6} | " + " | ".join(f"{('n=' + str(n)):>12}" for n in ns))
for d in [0.10, 0.20, 0.30, 0.40, 0.50]:
    vals = []
    for n in ns:
        theta, psi = (d + 0.05) / 2.0, (d - 0.05) / 2.0
        vals.append(f"{mcnemar_power_closed(n, theta, psi):.2f}/{mcnemar_power(n, theta, psi):.2f}")
    print(f"{d:>6.2f} | " + " | ".join(f"{v:>12}" for v in vals))

print()
print("=" * 92)
print("TABLE C: Detectable difference (80% power) at n = 200 and n = 400")
print("=" * 92)
print(f"{'d':>6} | {'n=200':>18} | {'n=400':>18} | {'n=920 (S3)':>18} | {'n=540 (S2)':>18}")
for d in [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]:
    print(f"{d:>6.2f} | "
          f"{detectable_delta(200, d) * 100:>17.1f}pp | "
          f"{detectable_delta(400, d) * 100:>17.1f}pp | "
          f"{detectable_delta(920, d) * 100:>17.1f}pp | "
          f"{detectable_delta(540, d) * 100:>17.1f}pp")

print()
print("=" * 92)
print("SANITY: null case (theta = psi) -> power should equal alpha = 0.05")
print("=" * 92)
for n in [200, 400, 800]:
    print(f"  n={n:>4}  exact={mcnemar_power(n, 0.25, 0.25):.4f}   approx={mcnemar_power_closed(n, 0.25, 0.25):.4f}")

print()
print("=" * 92)
print("SANITY: sign-test closed form vs exact at d=0.30, Delta=0.05")
print("=" * 92)
n_form = sign_test_formula_n(0.05, 0.30)
print(f"  formula n = {n_form:.1f} -> exact min n = {min_n_for_power(0.05, 0.30)}")
print(f"  power at n={n_form:.0f} (exact) = {mcnemar_power(int(round(n_form)), 0.175, 0.125):.4f}")
