---
uid: "241951"
type: identity
status: approved
content_hash: 2cfbcc50d38bb400
source: "Matrix Cookbook §1.2, eq. 26, p. 6"
unit: "matrix-cookbook:1.2:26"
frequency: rare
derivation: long
tags: [determinant]
verify: false
---

## front
$\det(\mathbf{I}+\mathbf{A})$ for $\mathbf{A} \in \mathbb{R}^{3 \times 3}$

## back
$1 + \det(\mathbf{A}) + \text{Tr}(\mathbf{A}) + \frac{1}{2}\text{Tr}(\mathbf{A})^2 - \frac{1}{2}\text{Tr}(\mathbf{A}^2)$

## prose
The terms are the sums of all products of $k$ distinct eigenvalues of $\mathbf{A}$ (the elementary symmetric polynomials), which run out at the dimension, so each dimension has its own formula.
