---
uid: ae6e48
type: identity
status: approved
content_hash: 2c6dca05fdc218ed
source: "Matrix Cookbook §2.1, eq. 49, p. 9"
unit: "matrix-cookbook:2.1:49"
gist: the derivative of the determinant
frequency: core
derivation: short
tags: [derivatives, determinant]
verify: true
---

## front
$\frac{\partial \det(\mathbf{X})}{\partial \mathbf{X}}$

## back
$\det(\mathbf{X})(\mathbf{X}^{-1})^T$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$ invertible. Denominator layout.

## proof
$\partial\det(\mathbf{X}) = \det(\mathbf{X})\text{Tr}(\mathbf{X}^{-1}\partial\mathbf{X})$;
reading the differential as $\text{Tr}(\mathbf{G}^T\partial\mathbf{X})$ gives
$\mathbf{G} = \det(\mathbf{X})\mathbf{X}^{-T}$.

## verify
```python
X = invertible(4)
lhs = grad(lambda M: np.linalg.det(M), X)
rhs = np.linalg.det(X) * np.linalg.inv(X).T
```
