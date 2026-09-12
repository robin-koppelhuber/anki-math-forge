---
uid: ce09ba
type: identity
status: approved
content_hash: 1995b5a6ed37a60d
source: "Matrix Cookbook §2.5, eq. 119, p. 13"
unit: "matrix-cookbook:2.5:119"
gist: the derivative of a squared affine residual
frequency: core
derivation: short
tags: [derivatives, trace]
verify: true
---

## front
$\frac{\partial}{\partial \mathbf{X}}\text{Tr}\left[(\mathbf{A}\mathbf{X}\mathbf{B}+\mathbf{C})(\mathbf{A}\mathbf{X}\mathbf{B}+\mathbf{C})^T\right]$

## back
$2\mathbf{A}^T(\mathbf{A}\mathbf{X}\mathbf{B}+\mathbf{C})\mathbf{B}^T$

## conditions
Denominator layout.

## prose
The least-squares gradient: the residual $\mathbf{A}\mathbf{X}\mathbf{B} + \mathbf{C}$ sandwiched between the transposes of whatever multiplies $\mathbf{X}$.

## proof
With $\mathbf{E} = \mathbf{A}\mathbf{X}\mathbf{B} + \mathbf{C}$ the trace is $\|\mathbf{E}\|_F^2$, so $d = 2\,\text{Tr}(\mathbf{B}\mathbf{E}^T\mathbf{A}\,d\mathbf{X})$, giving $2\mathbf{A}^T\mathbf{E}\mathbf{B}^T$.

## verify
```python
X = randn(3, 4)
A = randn(5, 3)
B = randn(4, 2)
C = randn(5, 2)
lhs = grad(lambda M: np.trace((A @ M @ B + C) @ (A @ M @ B + C).T), X)
rhs = 2 * A.T @ (A @ X @ B + C) @ B.T
```
