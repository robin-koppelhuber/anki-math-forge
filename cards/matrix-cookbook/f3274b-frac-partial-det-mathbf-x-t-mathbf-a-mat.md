---
uid: f3274b
type: identity
status: approved
content_hash: fc8b0c0a075d2b11
source: "Matrix Cookbook §2.1, eq. 52, p. 9"
unit: "matrix-cookbook:2.1:52"
gist: "the derivative of det(X^T A X), X square"
frequency: rare
derivation: short
tags: [derivatives, determinant]
verify: true
---

## front
$\frac{\partial \det(\mathbf{X}^T\mathbf{A}\mathbf{X})}{\partial \mathbf{X}}$ for square, invertible $\mathbf{X}$

## back
$2\det(\mathbf{X}^T\mathbf{A}\mathbf{X})\mathbf{X}^{-T}$

## conditions
$\mathbf{X}, \mathbf{A} \in \mathbb{R}^{n \times n}$; $\mathbf{X}$ invertible.
Denominator layout.

## prose
$\det(\mathbf{X}^T\mathbf{A}\mathbf{X}) = \det(\mathbf{A})\det(\mathbf{X})^2$,
so $\mathbf{A}$ leaves the derivative entirely and the square supplies the
factor $2$.

## verify
```python
A = randn(4, 4)
X = invertible(4)
lhs = grad(lambda M: np.linalg.det(M.T @ A @ M), X)
rhs = 2 * np.linalg.det(X.T @ A @ X) * np.linalg.inv(X).T
```

## notes
is square of the same size added. $\mathbf{A}$ need not be invertible: if
$\det(\mathbf{A}) = 0$ both sides are identically zero.
and gives the general formula, which collapses to this one for square
invertible $\mathbf{X}$. Two cards whose fronts differ only by an English
qualifier; decide whether to keep both.
