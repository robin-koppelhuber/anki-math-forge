---
uid: "341688"
type: identity
status: approved
content_hash: bb9127e4c0d02650
source: "Matrix Cookbook §2.5, eq. 102, p. 12"
unit: "matrix-cookbook:2.5:102"
gist: the derivative of the trace of A X^T B
frequency: core
derivation: short
tags: [derivatives, trace]
verify: false
---

## front
$\frac{\partial}{\partial \mathbf{X}}\text{Tr}(\mathbf{A}\mathbf{X}^T\mathbf{B})$

## back
$\mathbf{B}\mathbf{A}$

## conditions
Denominator layout.

## prose
Against $\partial\,\text{Tr}(\mathbf{A}\mathbf{X}\mathbf{B})/\partial\mathbf{X} = \mathbf{A}^T\mathbf{B}^T$: transposing $\mathbf{X}$ removes the transpose from the answer and reverses the order instead.

## proof
$\text{Tr}(\mathbf{A}\mathbf{X}^T\mathbf{B}) = \text{Tr}(\mathbf{B}\mathbf{A}\mathbf{X}^T) = \sum_{ij} (\mathbf{B}\mathbf{A})_{ij} X_{ij}$.
