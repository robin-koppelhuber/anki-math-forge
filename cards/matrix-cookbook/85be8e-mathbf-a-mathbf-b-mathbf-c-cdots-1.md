---
uid: 85be8e
type: identity
status: approved
content_hash: 848758208ad239ad
source: "Matrix Cookbook §1, eq. 1, p. 6"
unit: "matrix-cookbook:1:1, matrix-cookbook:1:2"
gist: the inverse of a product reverses the order
frequency: core
derivation: short
tags: [inverse, products]
verify: true
---

## front
$(\mathbf{A}\mathbf{B}\mathbf{C}\cdots)^{-1}$

## back
$\cdots\mathbf{C}^{-1}\mathbf{B}^{-1}\mathbf{A}^{-1}$

## conditions
$\mathbf{A}, \mathbf{B}, \mathbf{C}, \ldots \in \mathbb{R}^{n \times n}$, each invertible.

## proof
$(\mathbf{A}\mathbf{B})(\mathbf{B}^{-1}\mathbf{A}^{-1}) = \mathbf{A}(\mathbf{B}\mathbf{B}^{-1})\mathbf{A}^{-1} = \mathbf{I}$, the inner
factors cancelling first. An inverse is unique, so $\mathbf{B}^{-1}\mathbf{A}^{-1}$ is
the inverse of $\mathbf{A}\mathbf{B}$, and induction on the number of factors gives
the general form.

## verify
```python
A = invertible(4)
B = invertible(4)
C = invertible(4)
lhs = np.linalg.inv(A @ B @ C)
rhs = np.linalg.inv(C) @ np.linalg.inv(B) @ np.linalg.inv(A)
```
