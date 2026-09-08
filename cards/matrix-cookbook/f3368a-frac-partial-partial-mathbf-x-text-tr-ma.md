---
uid: f3368a
type: identity
status: approved
content_hash: 8aa3984c5d843768
source: "Matrix Cookbook §2.5, eq. 117, p. 13"
unit: "matrix-cookbook:2.5:117"
frequency: common
derivation: short
tags: [derivatives, trace]
verify: true
---

## front
$\frac{\partial}{\partial \mathbf{X}}\text{Tr}(\mathbf{X}^T\mathbf{B}\mathbf{X}\mathbf{C})$

## back
$\mathbf{B}\mathbf{X}\mathbf{C}+\mathbf{B}^T\mathbf{X}\mathbf{C}^T$

## conditions
Denominator layout.

## proof
$d\,\text{Tr}(\mathbf{X}^T\mathbf{B}\mathbf{X}\mathbf{C}) = \text{Tr}(d\mathbf{X}^T\mathbf{B}\mathbf{X}\mathbf{C}) + \text{Tr}(\mathbf{C}\mathbf{X}^T\mathbf{B}\,d\mathbf{X})$, giving $\mathbf{B}\mathbf{X}\mathbf{C} + (\mathbf{C}\mathbf{X}^T\mathbf{B})^T$.

## prose
$\mathbf{C} = \mathbf{I}$ recovers $\partial\,\text{Tr}(\mathbf{X}^T\mathbf{B}\mathbf{X})/\partial\mathbf{X} = \mathbf{B}\mathbf{X} + \mathbf{B}^T\mathbf{X}$.

## verify
```python
X = randn(4, 3)
B = randn(4, 4)
C = randn(3, 3)
lhs = grad(lambda M: np.trace(M.T @ B @ M @ C), X)
rhs = B @ X @ C + B.T @ X @ C.T
```
