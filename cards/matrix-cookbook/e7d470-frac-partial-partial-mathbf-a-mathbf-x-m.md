---
uid: e7d470
type: identity
status: approved
content_hash: e66950c463936000
source: "Matrix Cookbook §2.4, eq. 88, p. 11"
unit: "matrix-cookbook:2.4:88"
frequency: common
derivation: short
tags: [derivatives, least-squares]
verify: true
---

## front
$\frac{\partial}{\partial \mathbf{A}}(\mathbf{x}-\mathbf{A}\mathbf{s})^T\mathbf{W}(\mathbf{x}-\mathbf{A}\mathbf{s})$

## back
$-2\mathbf{W}(\mathbf{x}-\mathbf{A}\mathbf{s})\mathbf{s}^T$

## conditions
$\mathbf{W} = \mathbf{W}^T$. Denominator layout.

## verify
```python
A = randn(5, 3)
W = sym(5)
x = randn(5, 1)
s = randn(3, 1)
lhs = grad(lambda M: ((x - M @ s).T @ W @ (x - M @ s))[0, 0], A)
rhs = -2 * W @ (x - A @ s) @ s.T
```
