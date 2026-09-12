---
uid: 8179d7
type: identity
status: approved
content_hash: 3c25f520b24eb847
source: "Matrix Cookbook §1.3, p. 7"
unit: "matrix-cookbook:1.3:p7y487"
gist: an eigenvector of a 2 by 2 matrix
frequency: common
derivation: short
requires: [2d3bf4]
tags: [eigenvectors, two-by-two]
verify: true
---

## front
an eigenvector of $\mathbf{A} \in \mathbb{R}^{2 \times 2}$ for the eigenvalue $\lambda_i$

## back
$\mathbf{v}_i \propto \begin{bmatrix} A_{12} \\ \lambda_i - A_{11} \end{bmatrix}$

## conditions
$\mathbf{A} \in \mathbb{R}^{2 \times 2}$; $\lambda_i$ an eigenvalue of $\mathbf{A}$; not both $A_{12} = 0$ and $\lambda_i = A_{11}$.

## prose
Turning the first row of $\mathbf{A} - \lambda_i\mathbf{I}$ through a right angle lands in its kernel, and for a singular $2 \times 2$ that kernel is the eigenspace.

## proof
$(\mathbf{A} - \lambda_i\mathbf{I})\mathbf{v}_i$ has first entry $(A_{11}-\lambda_i)A_{12} + A_{12}(\lambda_i - A_{11}) = 0$ and second entry $A_{21}A_{12} + (A_{22}-\lambda_i)(\lambda_i - A_{11}) = -(\lambda_i^2 - \lambda_i\text{Tr}(\mathbf{A}) + \det(\mathbf{A}))$, which vanishes by the characteristic equation.

## verify
```python
P = invertible(2)
A = P @ np.diag(randn(2)) @ np.linalg.inv(P)
lam = np.linalg.eigvals(A).real[0]
v = np.array([A[0, 1], lam - A[0, 0]])
lhs = A @ v
rhs = lam * v
```

## notes
The source states no conditions. The excluded case is real: with $A_{12} = 0$ and $\lambda_i = A_{11}$ the formula returns $\mathbf{0}$, which is not an eigenvector. Everywhere else it is one for any $\lambda_i$ solving the characteristic equation.
