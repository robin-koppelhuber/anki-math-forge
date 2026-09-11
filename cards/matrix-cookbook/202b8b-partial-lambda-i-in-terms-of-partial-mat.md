---
uid: 202b8b
type: identity
status: approved
content_hash: 8fcec841f6b0dd63
source: "Matrix Cookbook §2.3, eq. 67, p. 10"
unit: "matrix-cookbook:2.3:67"
frequency: common
derivation: short
tags: [derivatives, eigenvalues, perturbation]
verify: true
---

## front
$\partial \lambda_i$ in terms of $\partial \mathbf{A}$

## back
$\mathbf{v}_i^\top (\partial \mathbf{A})\, \mathbf{v}_i$

## conditions
$\mathbf{A} \in \mathbb{R}^{n \times n}$, $\mathbf{A} = \mathbf{A}^\top$;
$\lambda_i$ a simple eigenvalue of $\mathbf{A}$ with eigenvector
$\mathbf{v}_i$, $\mathbf{v}_i^\top\mathbf{v}_i = 1$.

## prose
The gradient of a simple eigenvalue is the rank-one projector $\mathbf{v}_i\mathbf{v}_i^\top$, so only the part of the perturbation aligned with $\mathbf{v}_i$ moves $\lambda_i$ at first order.

## proof
Differentiate $\mathbf{A}\mathbf{v}_i = \lambda_i\mathbf{v}_i$ and left-multiply by $\mathbf{v}_i^\top$:
$\mathbf{v}_i^\top(\partial\mathbf{A})\mathbf{v}_i + \mathbf{v}_i^\top\mathbf{A}\,\partial\mathbf{v}_i = \partial\lambda_i + \lambda_i\mathbf{v}_i^\top\partial\mathbf{v}_i$.
Since $\mathbf{v}_i^\top\mathbf{A} = \lambda_i\mathbf{v}_i^\top$, the two $\partial\mathbf{v}_i$ terms cancel.

## verify
```python
Q = orth(4)
A = Q @ np.diag([1.0, 2.0, 3.0, 4.0]) @ Q.T
v = Q[:, 2]
lhs = grad(lambda M: np.sort(np.linalg.eigvals(M).real)[2], A)
rhs = np.outer(v, v)
```
