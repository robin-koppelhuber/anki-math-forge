---
uid: 5f0141
type: identity
status: approved
content_hash: 26da991204df53fb
source: "Matrix Cookbook §1.3, eq. 29, p. 7"
unit: "matrix-cookbook:1.3:29"
gist: the determinant of a 2 by 2 matrix
frequency: core
derivation: definitional
tags: [determinant, two-by-two]
verify: true
---

## front
$\det(\mathbf{A})$ for $\mathbf{A} \in \mathbb{R}^{2 \times 2}$

## back
$A_{11}A_{22} - A_{12}A_{21}$

## prose
The signed area of the parallelogram spanned by the columns of $\mathbf{A}$.

## verify
```python
A = randn(2, 2)
lhs = np.linalg.det(A)
rhs = A[0, 0] * A[1, 1] - A[0, 1] * A[1, 0]
```
