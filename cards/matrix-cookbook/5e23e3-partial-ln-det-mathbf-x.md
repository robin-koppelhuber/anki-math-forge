---
uid: 5e23e3
type: identity
status: approved
content_hash: 1adbb8120ac03bde
source: "Matrix Cookbook §2, eq. 43, p. 8"
unit: "matrix-cookbook:2:43"
gist: the differential of the log determinant
frequency: core
derivation: short
tags: [derivatives, differential, determinant]
verify: false
---

## front
$\partial(\ln(\det(\mathbf{X})))$

## back
$\text{Tr}(\mathbf{X}^{-1}\partial\mathbf{X})$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$; $\det(\mathbf{X}) > 0$.

## prose
The matrix analogue of $d(\ln x) = dx/x$, and the reason $\det(\mathbf{X})$
disappears from the right-hand side.

## proof
Divide $\partial\det(\mathbf{X}) = \det(\mathbf{X})\text{Tr}(\mathbf{X}^{-1}\partial\mathbf{X})$
by $\det(\mathbf{X})$.

## notes
writes $\ln(\det(\mathbf{X}))$ without an absolute value here. Writing
$\ln|\det(\mathbf{X})|$ instead, as the book does in eq. 57, drops it to plain
invertibility.
