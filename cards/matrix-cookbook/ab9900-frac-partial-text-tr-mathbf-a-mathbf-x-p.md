---
uid: ab9900
type: identity
status: approved
content_hash: 58b8c98f4e4dea8d
source: "Matrix Cookbook §2.8, eq. 142, p. 15"
unit: "matrix-cookbook:2.8:142"
gist: "the derivative of a trace, X diagonal"
frequency: common
derivation: short
tags: [derivatives, trace, diagonal]
verify: false
---

## front
$\frac{\partial \text{Tr}(\mathbf{A}\mathbf{X})}{\partial \mathbf{X}}$ for diagonal $\mathbf{X}$

## back
$\mathbf{A} \circ \mathbf{I}$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$; $X_{ij} = 0$ for $i \neq j$, varied over the diagonal entries $X_{ii}$ alone. Denominator layout.

## prose
Here $\circ$ multiplies entry by entry (the Hadamard product). $\text{Tr}(\mathbf{A}\mathbf{X}) = \sum_i A_{ii} X_{ii}$ once $\mathbf{X}$ is diagonal, so only the diagonal of $\mathbf{A}$ survives.
