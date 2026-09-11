---
uid: 67a723
type: identity
status: approved
content_hash: 0564c70a3d3c8b28
source: "Matrix Cookbook §2.5, eq. 100, p. 12"
unit: "matrix-cookbook:2.5:100"
frequency: core
derivation: short
tags: [derivatives, trace]
verify: false
---

## front
$\frac{\partial}{\partial \mathbf{X}}\text{Tr}(\mathbf{X}\mathbf{A})$

## back
$\mathbf{A}^T$

## conditions
Denominator layout.

## prose
$\text{Tr}(\mathbf{X}\mathbf{A})$ is the entrywise inner product of $\mathbf{X}$ with $\mathbf{A}^T$, and the gradient of a linear form is its coefficient matrix.

## proof
$\text{Tr}(\mathbf{X}\mathbf{A}) = \sum_{ij} X_{ij} A_{ji}$, so $\partial / \partial X_{ij} = A_{ji}$.
