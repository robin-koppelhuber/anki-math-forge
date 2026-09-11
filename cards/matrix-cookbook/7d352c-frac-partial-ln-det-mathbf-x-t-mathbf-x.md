---
uid: 7d352c
type: identity
status: approved
content_hash: e6b0076ef129ca2a
source: "Matrix Cookbook §2.1, eq. 55, p. 9"
unit: "matrix-cookbook:2.1:55"
frequency: rare
derivation: short
tags: [derivatives, determinant, pseudo-inverse]
verify: true
---

## front
$\frac{\partial \ln\det(\mathbf{X}^T\mathbf{X})}{\partial \mathbf{X}}$

## back
$2(\mathbf{X}^+)^T$

## conditions
$\mathbf{X} \in \mathbb{R}^{m \times n}$; $\text{rank}(\mathbf{X}) = n$.
Denominator layout.

## prose
$(\mathbf{X}^+)^T = \mathbf{X}(\mathbf{X}^T\mathbf{X})^{-1}$, which has the shape
of $\mathbf{X}$; $\mathbf{X}^{-T}$ does not exist for rectangular $\mathbf{X}$.

## uses
Choosing where to measure so the estimate comes out most precise: maximise $\ln\det(\mathbf{X}^T\mathbf{X})$ over the design $\mathbf{X}$ (D-optimal design).

## verify
```python
X = randn(5, 3)
lhs = grad(lambda M: np.log(np.linalg.det(M.T @ M)), X)
rhs = 2 * np.linalg.pinv(X).T
```

## notes
eq. 55, with no opening bar. Dropped: $\det(\mathbf{X}^T\mathbf{X}) \ge 0$ for
real $\mathbf{X}$, so no absolute value is needed.
CLAUDE.md's wording for denominator layout says $\partial(\text{scalar})/\partial\mathbf{X}$
has the shape of $\mathbf{X}^T$, but `verify.grad` documents the opposite ("the
result has the shape of `x`, matching the cards"), the worked example in the
card-writing skill gives $\mathbf{X}^{-T}$ for $\partial\log\det\mathbf{X}/\partial\mathbf{X}$,
and the Cookbook agrees with both. Followed the code and the source. This is the
one card in §2.1 where the two readings visibly disagree, because $\mathbf{X}$ is
rectangular. Worth fixing CLAUDE.md's sentence.
