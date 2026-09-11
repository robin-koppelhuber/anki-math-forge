---
uid: "644726"
type: identity
status: approved
content_hash: d5aee07934bff027
source: "Matrix Cookbook §2.5, eq. 123, p. 13"
unit: "matrix-cookbook:2.5:p13y636, matrix-cookbook:2.5:p13y667, matrix-cookbook:2.5:123"
frequency: rare
derivation: long
tags: [derivatives, trace]
verify: true
---

## front
$\frac{\partial}{\partial \mathbf{X}}\text{Tr}\left[\mathbf{B}^T\mathbf{X}^T\mathbf{C}\mathbf{X}\mathbf{X}^T\mathbf{C}\mathbf{X}\mathbf{B}\right]$

## back
$\mathbf{C}\mathbf{X}\mathbf{X}^T\mathbf{C}\mathbf{X}\mathbf{B}\mathbf{B}^T+\mathbf{C}^T\mathbf{X}\mathbf{B}\mathbf{B}^T\mathbf{X}^T\mathbf{C}^T\mathbf{X}+\mathbf{C}\mathbf{X}\mathbf{B}\mathbf{B}^T\mathbf{X}^T\mathbf{C}\mathbf{X}+\mathbf{C}^T\mathbf{X}\mathbf{X}^T\mathbf{C}^T\mathbf{X}\mathbf{B}\mathbf{B}^T$

## conditions
Denominator layout.

## prose
Four terms, one for each of the four occurrences of $\mathbf{X}$ in the trace.

## verify
```python
X = randn(4, 3)
B = randn(3, 2)
C = randn(4, 4)
lhs = grad(lambda M: np.trace(B.T @ M.T @ C @ M @ M.T @ C @ M @ B), X)
rhs = (C @ X @ X.T @ C @ X @ B @ B.T
       + C.T @ X @ B @ B.T @ X.T @ C.T @ X
       + C @ X @ B @ B.T @ X.T @ C @ X
       + C.T @ X @ X.T @ C.T @ X @ B @ B.T)
```
