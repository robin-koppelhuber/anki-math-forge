---
uid: 1c955d
type: identity
status: approved
content_hash: 24cdfb2f01f78e94
source: "Matrix Cookbook §2.2, eq. 62, p. 10"
unit: "matrix-cookbook:2.2:62"
gist: the derivative of the determinant of the inverse
frequency: rare
derivation: short
tags: [derivatives, inverse, determinant]
verify: true
---

## front
$\frac{\partial \det(\mathbf{X}^{-1})}{\partial \mathbf{X}}$

## back
$-\det(\mathbf{X}^{-1})\,\mathbf{X}^{-\top}$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$ invertible. Denominator layout.

## proof
$\det(\mathbf{X}^{-1}) = 1/\det(\mathbf{X})$, so the chain rule applied to
$\partial \det(\mathbf{X})/\partial\mathbf{X} = \det(\mathbf{X})\mathbf{X}^{-\top}$ gives
$-\det(\mathbf{X})\mathbf{X}^{-\top}/\det(\mathbf{X})^2$.

## verify
```python
X = randn(4, 4)
lhs = grad(lambda M: float(np.linalg.det(np.linalg.inv(M))), X)
rhs = -np.linalg.det(np.linalg.inv(X)) * np.linalg.inv(X).T
```
