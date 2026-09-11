---
uid: af5ca1
type: identity
status: approved
content_hash: a387921e4a30222d
source: "Matrix Cookbook §1.2, eq. 18, p. 6"
unit: "matrix-cookbook:1.2:18"
frequency: core
derivation: short
tags: [determinant, eigenvalues]
verify: false
---

## front
$\prod_i \lambda_i$ where $\lambda_i = \text{eig}(\mathbf{A})$

## back
$\det(\mathbf{A})$

## conditions
$\mathbf{A} \in \mathbb{R}^{n \times n}$; $\lambda_1, \dots, \lambda_n$ the eigenvalues of $\mathbf{A}$ over $\mathbb{C}$, with algebraic multiplicity.
