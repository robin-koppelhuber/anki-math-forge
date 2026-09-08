---
uid: 827eae
type: identity
status: approved
content_hash: b3be8dab39d592c1
source: "Matrix Cookbook §1.1, eq. 12, p. 6"
unit: "matrix-cookbook:1.1:12"
frequency: core
derivation: short
tags: [trace, eigenvalues]
verify: false
---

## front
$\sum_i \lambda_i$, the sum of the eigenvalues of $\mathbf{A}$

## back
$\text{Tr}(\mathbf{A})$

## conditions
$\mathbf{A} \in \mathbb{R}^{n \times n}$; $\lambda_1, \dots, \lambda_n$ the eigenvalues of $\mathbf{A}$ over $\mathbb{C}$, with algebraic multiplicity.

## notes
Source states no conditions. Added squareness, and that eigenvalues are counted with multiplicity over C. Without multiplicity the identity is false for any matrix with a repeated eigenvalue.
