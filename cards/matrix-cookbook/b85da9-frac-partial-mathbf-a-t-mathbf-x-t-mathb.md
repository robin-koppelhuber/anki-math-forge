---
uid: b85da9
type: identity
status: approved
content_hash: 74f03329a98e380d
source: "Matrix Cookbook §2.4, eq. 71, p. 10"
unit: "matrix-cookbook:2.4:71"
gist: the derivative of a bilinear form with X transposed
frequency: common
derivation: short
tags: [derivatives, linear-forms]
verify: true
---

## front
$\frac{\partial \mathbf{a}^T\mathbf{X}^T\mathbf{b}}{\partial \mathbf{X}}$

## back
$\mathbf{b}\mathbf{a}^T$

## conditions
Denominator layout.

## prose
$\mathbf{a}^T\mathbf{X}^T\mathbf{b} = \mathbf{b}^T\mathbf{X}\mathbf{a}$, which
swaps the two vectors in the outer product.

## verify
```python
X = randn(4, 3)
a = randn(3, 1)
b = randn(4, 1)
lhs = grad(lambda M: (a.T @ M.T @ b)[0, 0], X)
rhs = b @ a.T
```
