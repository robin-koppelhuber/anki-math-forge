---
uid: d33b7a
type: identity
status: approved
content_hash: 43fe9fb39d77fee6
source: "Matrix Cookbook §1.2, eq. 25, p. 6"
unit: "matrix-cookbook:1.2:25"
frequency: common
derivation: short
tags: [determinant]
verify: false
---

## front
$\det(\mathbf{I}+\mathbf{A})$ for $\mathbf{A} \in \mathbb{R}^{2 \times 2}$

## back
$1 + \det(\mathbf{A}) + \text{Tr}(\mathbf{A})$

## prose
The right-hand side stops at $\text{Tr}(\mathbf{A})$ because the sums of products of $k$ distinct eigenvalues (the elementary symmetric polynomials) run out at the dimension, so each dimension has its own formula.

## notes
The source prints 'For n = 2:' as a separate line above this equation, so the dimension is in no crop. Without it this card would claim a general identity that is false for every n other than 2, and eq. 28, the book's one confirmed error, is what this family looks like when the dimension is dropped.
