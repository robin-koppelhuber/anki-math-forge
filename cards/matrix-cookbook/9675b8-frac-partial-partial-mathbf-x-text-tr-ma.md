---
uid: 9675b8
type: identity
status: approved
content_hash: c6bc3bfb669d1c96
source: "Matrix Cookbook §2.5, eq. 101, p. 12"
unit: "matrix-cookbook:2.5:101"
gist: the derivative of the trace of AXB
frequency: core
derivation: short
tags: [derivatives, trace]
verify: false
---

## front
$\frac{\partial}{\partial \mathbf{X}}\text{Tr}(\mathbf{A}\mathbf{X}\mathbf{B})$

## back
$\mathbf{A}^T\mathbf{B}^T$

## conditions
Denominator layout.

## prose
$\mathbf{A}^T\mathbf{B}^T = (\mathbf{B}\mathbf{A})^T$: rotate $\mathbf{X}$ to the front of the trace, then transpose what is left, so the order does not reverse.

## proof
$\text{Tr}(\mathbf{A}\mathbf{X}\mathbf{B}) = \text{Tr}(\mathbf{X}\mathbf{B}\mathbf{A})$, and $\partial\,\text{Tr}(\mathbf{X}\mathbf{M})/\partial\mathbf{X} = \mathbf{M}^T$ with $\mathbf{M} = \mathbf{B}\mathbf{A}$.
