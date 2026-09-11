---
uid: 36ca1a
type: identity
status: approved
content_hash: 0ef79d7d46d8c634
source: "Matrix Cookbook §2.5, eq. 118, p. 13"
unit: "matrix-cookbook:2.5:118"
frequency: rare
derivation: short
tags: [derivatives, trace]
verify: true
---

## front
$\frac{\partial}{\partial \mathbf{X}}\text{Tr}(\mathbf{A}\mathbf{X}\mathbf{B}\mathbf{X}^T\mathbf{C})$

## back
$\mathbf{A}^T\mathbf{C}^T\mathbf{X}\mathbf{B}^T+\mathbf{C}\mathbf{A}\mathbf{X}\mathbf{B}$

## conditions
Denominator layout.

## proof
$d\,\text{Tr}(\mathbf{A}\mathbf{X}\mathbf{B}\mathbf{X}^T\mathbf{C}) = \text{Tr}(\mathbf{B}\mathbf{X}^T\mathbf{C}\mathbf{A}\,d\mathbf{X}) + \text{Tr}(\mathbf{C}\mathbf{A}\mathbf{X}\mathbf{B}\,d\mathbf{X}^T)$; the first term transposes and the second does not.

## verify
```python
X = randn(4, 3)
A = randn(5, 4)
B = randn(3, 3)
C = randn(4, 5)
lhs = grad(lambda M: np.trace(A @ M @ B @ M.T @ C), X)
rhs = A.T @ C.T @ X @ B.T + C @ A @ X @ B
```
