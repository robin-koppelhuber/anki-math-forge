---
uid: b5cc4b
type: identity
status: approved
content_hash: c6af89ec25e0bef8
source: "Matrix Cookbook §2.4, eq. 83, p. 11"
unit: "matrix-cookbook:2.4:83"
gist: the derivative of a quadratic form in an affine map
frequency: common
derivation: short
tags: [derivatives, quadratic-forms]
verify: true
---

## front
$\frac{\partial}{\partial \mathbf{X}}(\mathbf{X}\mathbf{b}+\mathbf{c})^T\mathbf{D}(\mathbf{X}\mathbf{b}+\mathbf{c})$

## back
$(\mathbf{D}+\mathbf{D}^T)(\mathbf{X}\mathbf{b}+\mathbf{c})\mathbf{b}^T$

## conditions
Denominator layout.

## prose
$\mathbf{D} + \mathbf{D}^T$ collapses to $2\mathbf{D}$ only when $\mathbf{D} = \mathbf{D}^T$.

## verify
```python
X = randn(5, 3)
D = randn(5, 5)
b = randn(3, 1)
c = randn(5, 1)
lhs = grad(lambda M: ((M @ b + c).T @ D @ (M @ b + c))[0, 0], X)
rhs = (D + D.T) @ (X @ b + c) @ b.T
```
