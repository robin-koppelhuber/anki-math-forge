---
uid: b321eb
type: identity
status: approved
content_hash: fe085b4230fdf47b
source: "Matrix Cookbook §2.1, eq. 58, p. 9"
unit: "matrix-cookbook:2.1:58"
gist: the derivative of the determinant of a power
frequency: rare
derivation: short
tags: [derivatives, determinant]
verify: true
---

## front
$\frac{\partial \det(\mathbf{X}^k)}{\partial \mathbf{X}}$

## back
$k\det(\mathbf{X}^k)\mathbf{X}^{-T}$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$ invertible;
$k \in \mathbb{Z}_{>0}$. Denominator layout.

## prose
$\det(\mathbf{X}^k) = \det(\mathbf{X})^k$, so the exponent comes down as a
factor just as in $(x^k)' = kx^{k-1}$.

## verify
```python
X = invertible(4)
k = 3
lhs = grad(lambda M: np.linalg.det(np.linalg.matrix_power(M, k)), X)
rhs = k * np.linalg.det(np.linalg.matrix_power(X, k)) * np.linalg.inv(X).T
```

## notes
integer added.
