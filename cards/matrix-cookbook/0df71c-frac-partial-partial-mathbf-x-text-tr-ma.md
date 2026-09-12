---
uid: 0df71c
type: identity
status: approved
content_hash: 33fcecdc613a74ba
source: "Matrix Cookbook §2.5, eq. 108, p. 13"
unit: "matrix-cookbook:2.5:108"
gist: the derivative of the trace of X^T B X
frequency: core
derivation: short
tags: [derivatives, trace]
verify: true
---

## front
$\frac{\partial}{\partial \mathbf{X}}\text{Tr}(\mathbf{X}^T\mathbf{B}\mathbf{X})$

## back
$\mathbf{B}\mathbf{X}+\mathbf{B}^T\mathbf{X}$

## conditions
Denominator layout.

## prose
The matrix analogue of $(bx^2)' = 2bx$, which it becomes exactly when $\mathbf{B}$ is symmetric.

## proof
The trace is linear, so the differential passes through it: $d\,\text{Tr}(\mathbf{M}) = \text{Tr}(d\mathbf{M})$. The product rule on $\mathbf{X}^T\mathbf{B}\mathbf{X}$ then gives $d\,\text{Tr}(\mathbf{X}^T\mathbf{B}\mathbf{X}) = \text{Tr}((d\mathbf{X})^T\mathbf{B}\mathbf{X}) + \text{Tr}(\mathbf{X}^T\mathbf{B}\,d\mathbf{X})$. Reading each term as $\text{Tr}(\mathbf{G}^T d\mathbf{X})$ gives $\mathbf{G} = \mathbf{B}\mathbf{X} + \mathbf{B}^T\mathbf{X}$.

## verify
```python
X = randn(4, 3)
B = randn(4, 4)
lhs = grad(lambda M: np.trace(M.T @ B @ M), X)
rhs = B @ X + B.T @ X
```

## notes
