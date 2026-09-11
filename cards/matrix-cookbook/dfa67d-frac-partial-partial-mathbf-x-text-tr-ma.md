---
uid: dfa67d
type: identity
status: approved
content_hash: 7de86747dbe77d3b
source: "Matrix Cookbook §2.5, eq. 114, p. 13"
unit: "matrix-cookbook:2.5:114"
frequency: rare
derivation: short
tags: [derivatives, trace]
verify: true
---

## front
$\frac{\partial}{\partial \mathbf{X}}\text{Tr}(\mathbf{A}\mathbf{X}\mathbf{B}\mathbf{X})$

## back
$\mathbf{A}^T\mathbf{X}^T\mathbf{B}^T+\mathbf{B}^T\mathbf{X}^T\mathbf{A}^T$

## conditions
Denominator layout.

## proof
$d\,\text{Tr}(\mathbf{A}\mathbf{X}\mathbf{B}\mathbf{X}) = \text{Tr}(\mathbf{B}\mathbf{X}\mathbf{A}\,d\mathbf{X}) + \text{Tr}(\mathbf{A}\mathbf{X}\mathbf{B}\,d\mathbf{X})$, so the answer is $(\mathbf{B}\mathbf{X}\mathbf{A})^T + (\mathbf{A}\mathbf{X}\mathbf{B})^T$.

## verify
```python
X = randn(3, 4)
A = randn(4, 3)
B = randn(4, 3)
lhs = grad(lambda M: np.trace(A @ M @ B @ M), X)
rhs = A.T @ X.T @ B.T + B.T @ X.T @ A.T
```
