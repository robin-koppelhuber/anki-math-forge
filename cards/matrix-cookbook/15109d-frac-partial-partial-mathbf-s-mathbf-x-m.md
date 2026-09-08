---
uid: 15109d
type: identity
status: approved
content_hash: 57e89c91a1938983
source: "Matrix Cookbook §2.4, eq. 84, p. 11"
unit: "matrix-cookbook:2.4:84"
frequency: core
derivation: short
tags: [derivatives, least-squares]
verify: true
---

## front
$\frac{\partial}{\partial \mathbf{s}}(\mathbf{x}-\mathbf{A}\mathbf{s})^T\mathbf{W}(\mathbf{x}-\mathbf{A}\mathbf{s})$

## back
$-2\mathbf{A}^T\mathbf{W}(\mathbf{x}-\mathbf{A}\mathbf{s})$

## conditions
$\mathbf{W}$ symmetric. Denominator layout.

## prose
Setting it to zero gives the weighted normal equations
$\mathbf{A}^T\mathbf{W}\mathbf{A}\mathbf{s} = \mathbf{A}^T\mathbf{W}\mathbf{x}$.

## verify
```python
A = randn(5, 3)
W = sym(5)
x = randn(5, 1)
s = randn(3, 1)
lhs = grad(lambda v: ((x - A @ v).T @ W @ (x - A @ v))[0, 0], s)
rhs = -2 * A.T @ W @ (x - A @ s)
```
