---
uid: 15109d
type: identity
status: approved
content_hash: 865d4efca2b08a55
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

## proof
Write $\mathbf{r} = \mathbf{x}-\mathbf{A}\mathbf{s}$, so $\partial\mathbf{r}/\partial\mathbf{s} = -\mathbf{A}$. With $\mathbf{W}$ symmetric, $\partial(\mathbf{r}^T\mathbf{W}\mathbf{r})/\partial\mathbf{r} = 2\mathbf{W}\mathbf{r}$, and the chain rule contributes the $-\mathbf{A}^T$ in front.

## verify
```python
A = randn(5, 3)
W = sym(5)
x = randn(5, 1)
s = randn(3, 1)
lhs = grad(lambda v: ((x - A @ v).T @ W @ (x - A @ v))[0, 0], s)
rhs = -2 * A.T @ W @ (x - A @ s)
```

## notes
