---
uid: "645682"
type: identity
status: approved
content_hash: e3e7c6cc7f63922f
source: "Matrix Cookbook §2.2, eq. 63, p. 10"
unit: "matrix-cookbook:2.2:63"
frequency: common
derivation: short
tags: [derivatives, inverse, trace]
verify: true
---

## front
$\frac{\partial \operatorname{Tr}(\mathbf{A}\mathbf{X}^{-1}\mathbf{B})}{\partial \mathbf{X}}$

## back
$-(\mathbf{X}^{-1}\mathbf{B}\mathbf{A}\mathbf{X}^{-1})^\top$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$ invertible;
$\mathbf{A} \in \mathbb{R}^{p \times n}$; $\mathbf{B} \in \mathbb{R}^{n \times p}$.
Denominator layout.

## prose
Cyclicity puts $\mathbf{B}$ in front of $\mathbf{A}$, so the answer carries $\mathbf{B}\mathbf{A}$ where the trace carries $\mathbf{A}\dots\mathbf{B}$.

## proof
$d\operatorname{Tr}(\mathbf{A}\mathbf{X}^{-1}\mathbf{B}) = -\operatorname{Tr}(\mathbf{A}\mathbf{X}^{-1}(d\mathbf{X})\mathbf{X}^{-1}\mathbf{B}) = -\operatorname{Tr}(\mathbf{X}^{-1}\mathbf{B}\mathbf{A}\mathbf{X}^{-1}\, d\mathbf{X})$
by cyclicity; matching $\operatorname{Tr}(\mathbf{G}^\top d\mathbf{X})$ transposes the bracket.

## verify
```python
X = invertible(4)
A = randn(3, 4)
B = randn(4, 3)
Xi = np.linalg.inv(X)
lhs = grad(lambda M: np.trace(A @ np.linalg.inv(M) @ B), X)
rhs = -(Xi @ B @ A @ Xi).T
```

## notes
need be square is now carried by the shapes $p \times n$ and $n \times p$.
