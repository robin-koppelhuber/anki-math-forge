---
uid: a59d3b
type: identity
status: approved
content_hash: 64a71d08aafdb00b
source: "Matrix Cookbook §2.1, eq. 57, p. 9"
unit: "matrix-cookbook:2.1:57"
gist: the derivative of the log absolute determinant
frequency: core
derivation: short
tags: [derivatives, determinant]
verify: true
---

## front
$\frac{\partial \ln|\det(\mathbf{X})|}{\partial \mathbf{X}}$

## back
$(\mathbf{X}^{-1})^T$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$ invertible. Denominator layout.

## prose
The matrix analogue of $(\ln|x|)' = 1/x$, and the absolute value is what lets
$\det(\mathbf{X}) < 0$ through.

## proof
Jacobi's formula gives
$\partial\ln|\det\mathbf{X}| = \text{Tr}(\mathbf{X}^{-1}\partial\mathbf{X})$;
reading the differential as $\text{Tr}(\mathbf{G}^T\partial\mathbf{X})$ gives
$\mathbf{G} = \mathbf{X}^{-T}$.

## verify
```python
X = invertible(4)
lhs = grad(lambda M: np.log(abs(np.linalg.det(M))), X)
rhs = np.linalg.inv(X).T
```

## notes
from the back as the same matrix.
