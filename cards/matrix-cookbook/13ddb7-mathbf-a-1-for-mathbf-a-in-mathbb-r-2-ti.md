---
uid: 13ddb7
type: identity
status: approved
content_hash: 597599d62ad35abb
source: "Matrix Cookbook §1.3, eq. 31, p. 7"
unit: "matrix-cookbook:1.3:31"
frequency: core
derivation: short
requires: [5f0141]
tags: [inverse, two-by-two]
verify: true
---

## front
$\mathbf{A}^{-1}$ for $\mathbf{A} \in \mathbb{R}^{2 \times 2}$

## back
$\dfrac{1}{\det(\mathbf{A})}\begin{bmatrix} A_{22} & -A_{12} \\ -A_{21} & A_{11} \end{bmatrix}$

## conditions
$\mathbf{A} \in \mathbb{R}^{2 \times 2}$; $\det(\mathbf{A}) \neq 0$.

## proof
$\begin{bmatrix} A_{22} & -A_{12} \\ -A_{21} & A_{11} \end{bmatrix}\mathbf{A} = \det(\mathbf{A})\,\mathbf{I}$ by direct multiplication (the adjugate), so dividing by $\det(\mathbf{A})$ inverts $\mathbf{A}$.

## verify
```python
A = invertible(2)
lhs = np.linalg.inv(A)
rhs = np.array([[A[1, 1], -A[0, 1]], [-A[1, 0], A[0, 0]]]) / np.linalg.det(A)
```
