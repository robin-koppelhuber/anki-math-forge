---
uid: 32b498
type: identity
status: approved
content_hash: 3292b8436cbf50b9
source: "Matrix Cookbook §2.5, eq. 127, p. 14"
unit: "matrix-cookbook:2.5:p14y256, matrix-cookbook:2.5:127"
frequency: rare
derivation: long
tags: [derivatives, trace]
verify: true
---

## front
$\frac{\partial}{\partial \mathbf{X}}\text{Tr}\left[(\mathbf{A}+\mathbf{X}^T\mathbf{C}\mathbf{X})^{-1}(\mathbf{X}^T\mathbf{B}\mathbf{X})\right]$

## back
$-2\mathbf{C}\mathbf{X}\mathbf{M}^{-1}\mathbf{X}^T\mathbf{B}\mathbf{X}\mathbf{M}^{-1}+2\mathbf{B}\mathbf{X}\mathbf{M}^{-1}$, where $\mathbf{M}=\mathbf{A}+\mathbf{X}^T\mathbf{C}\mathbf{X}$

## conditions
$\mathbf{A}$, $\mathbf{B}$, $\mathbf{C}$ symmetric; $\mathbf{A} + \mathbf{X}^T\mathbf{C}\mathbf{X}$ invertible. Denominator layout.

## prose
$\mathbf{A} = \mathbf{0}$ gives the same identity for $\text{Tr}[(\mathbf{X}^T\mathbf{C}\mathbf{X})^{-1}(\mathbf{X}^T\mathbf{B}\mathbf{X})]$.

## uses
Finding the projection that spreads several classes furthest apart (the multiclass Fisher discriminant).

## proof
$d\,\text{Tr}(\mathbf{M}^{-1}\mathbf{N}) = -\text{Tr}(\mathbf{M}^{-1} d\mathbf{M}\,\mathbf{M}^{-1}\mathbf{N}) + \text{Tr}(\mathbf{M}^{-1} d\mathbf{N})$ with $\mathbf{N} = \mathbf{X}^T\mathbf{B}\mathbf{X}$; each of $d\mathbf{M}$ and $d\mathbf{N}$ splits into two halves that are equal because $\mathbf{M}$ and $\mathbf{N}$ are symmetric, which is where both factors of 2 come from.

## verify
```python
X = randn(4, 3)
A = spd(3)
B = sym(4)
C = spd(4)
lhs = grad(lambda Z: np.trace(np.linalg.inv(A + Z.T @ C @ Z) @ (Z.T @ B @ Z)), X)
Mi = np.linalg.inv(A + X.T @ C @ X)
rhs = -2 * C @ X @ Mi @ X.T @ B @ X @ Mi + 2 * B @ X @ Mi
```

## notes
Source assumes only $\mathbf{B}$ and $\mathbf{C}$ symmetric. Symmetry of $\mathbf{A}$ added: the halves of the differential collapse into the factors of 2 only if $\mathbf{M} = \mathbf{A} + \mathbf{X}^T\mathbf{C}\mathbf{X}$ is symmetric, and $\mathbf{X}^T\mathbf{C}\mathbf{X}$ already is. With $\mathbf{A}$ general the answer is $-\mathbf{C}\mathbf{X}(\mathbf{M}^{-1}\mathbf{N}\mathbf{M}^{-1} + \mathbf{M}^{-T}\mathbf{N}\mathbf{M}^{-T}) + \mathbf{B}\mathbf{X}(\mathbf{M}^{-1} + \mathbf{M}^{-T})$. Invertibility of $\mathbf{M}$ also added.
