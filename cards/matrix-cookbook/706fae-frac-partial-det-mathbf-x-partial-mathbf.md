---
uid: 706fae
type: identity
status: approved
content_hash: 57dd04cffbe4486f
source: "Matrix Cookbook §2.8, eq. 140, p. 15"
unit: "matrix-cookbook:2.8:140"
frequency: common
derivation: short
tags: [derivatives, determinant, symmetric]
verify: false
---

## front
$\frac{\partial \det(\mathbf{X})}{\partial \mathbf{X}}$ for symmetric $\mathbf{X}$

## back
$\det(\mathbf{X})\left(2\mathbf{X}^{-1} - (\mathbf{X}^{-1} \circ \mathbf{I})\right)$

## conditions
$\mathbf{X} = \mathbf{X}^T$, varied over $X_{ij}$ with $i \le j$ only, the rest following by symmetry; $\mathbf{X}$ invertible. Denominator layout.

## prose
Here $\circ$ multiplies entry by entry (the Hadamard product).

## proof
Varying all $n^2$ entries independently gives $\det(\mathbf{X})\mathbf{X}^{-T}$; the symmetric rule $\mathbf{G} + \mathbf{G}^T - \text{diag}(\mathbf{G})$ with $\mathbf{X}^{-1}$ symmetric collapses the first two terms into $2\mathbf{X}^{-1}$.
