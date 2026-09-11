---
uid: b8a504
type: identity
status: approved
content_hash: d63c47bd80e139c4
source: "Matrix Cookbook §2.5, eq. 111, p. 13"
unit: "matrix-cookbook:2.5:111"
frequency: core
derivation: short
tags: [derivatives, trace]
verify: true
---

## front
$\frac{\partial}{\partial \mathbf{X}}\text{Tr}(\mathbf{X}\mathbf{B}\mathbf{X}^T)$

## back
$\mathbf{X}\mathbf{B}^T+\mathbf{X}\mathbf{B}$

## conditions
Denominator layout.

## prose
$\mathbf{B}$ ends up on the right of $\mathbf{X}$ here, and on the left in $\partial\,\text{Tr}(\mathbf{X}^T\mathbf{B}\mathbf{X})/\partial\mathbf{X} = \mathbf{B}\mathbf{X} + \mathbf{B}^T\mathbf{X}$.

## proof
$d\,\text{Tr}(\mathbf{X}\mathbf{B}\mathbf{X}^T) = \text{Tr}(\mathbf{B}\mathbf{X}^T d\mathbf{X}) + \text{Tr}(d\mathbf{X}^T \mathbf{X}\mathbf{B})$, giving $(\mathbf{B}\mathbf{X}^T)^T + \mathbf{X}\mathbf{B}$.

## verify
```python
X = randn(3, 4)
B = randn(4, 4)
lhs = grad(lambda M: np.trace(M @ B @ M.T), X)
rhs = X @ B.T + X @ B
```
