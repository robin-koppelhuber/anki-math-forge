---
uid: 315f8d
type: identity
status: approved
content_hash: 5f4b814da6369ae3
source: "Matrix Cookbook §1, eq. 5, p. 6"
unit: "matrix-cookbook:1:5, matrix-cookbook:1:6"
gist: the transpose of a product reverses the order
frequency: core
derivation: short
tags: [transpose, products]
verify: true
---

## front
$(\mathbf{A}\mathbf{B}\mathbf{C}\cdots)^T$

## back
$\cdots\mathbf{C}^T\mathbf{B}^T\mathbf{A}^T$

## conditions
$\mathbf{A}, \mathbf{B}, \mathbf{C}, \ldots$ conformable, so that the product is defined. None of them need be square.

## prose
With $\mathbf{A}$ of size $m \times n$ and $\mathbf{B}$ of size $n \times p$,
$(\mathbf{A}\mathbf{B})^T$ is $p \times m$, and reversing the factors is the only
order whose shapes still fit.

## verify
```python
A = randn(4, 3)
B = randn(3, 5)
C = randn(5, 2)
lhs = (A @ B @ C).T
rhs = C.T @ B.T @ A.T
```
