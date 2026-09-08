---
uid: 5eae90
type: identity
status: approved
content_hash: f2cdceae4a086749
source: "Matrix Cookbook §2.5, eq. 125, p. 14"
unit: "matrix-cookbook:2.5:125"
frequency: rare
derivation: long
tags: [derivatives, trace]
verify: true
---

## front
$\frac{\partial}{\partial \mathbf{X}}\text{Tr}\left[(\mathbf{X}^T\mathbf{C}\mathbf{X})^{-1}\mathbf{A}\right]$

## back
$-\mathbf{C}\mathbf{X}(\mathbf{X}^T\mathbf{C}\mathbf{X})^{-1}(\mathbf{A}+\mathbf{A}^T)(\mathbf{X}^T\mathbf{C}\mathbf{X})^{-1}$

## conditions
$\mathbf{C}$ symmetric; $\mathbf{X}^T\mathbf{C}\mathbf{X}$ invertible. Denominator layout.

## uses
Choosing where to measure so the estimate comes out most precise, over the design matrix $\mathbf{X}$ (L-optimal design).

## proof
With $\mathbf{M} = \mathbf{X}^T\mathbf{C}\mathbf{X}$ and $d\mathbf{M} = d\mathbf{X}^T\mathbf{C}\mathbf{X} + \mathbf{X}^T\mathbf{C}\,d\mathbf{X}$, $d\,\text{Tr}(\mathbf{M}^{-1}\mathbf{A}) = -\text{Tr}(\mathbf{M}^{-1} d\mathbf{M}\,\mathbf{M}^{-1}\mathbf{A})$; the two halves of $d\mathbf{M}$ contribute $\mathbf{A}$ and $\mathbf{A}^T$.

## prose
$\mathbf{A} + \mathbf{A}^T$ appears because $\mathbf{X}$ enters $\mathbf{X}^T\mathbf{C}\mathbf{X}$ on both sides.

## verify
```python
X = randn(4, 3)
C = spd(4)
A = randn(3, 3)
Mi = np.linalg.inv(X.T @ C @ X)
lhs = grad(lambda Z: np.trace(np.linalg.inv(Z.T @ C @ Z) @ A), X)
rhs = -C @ X @ Mi @ (A + A.T) @ Mi
```
