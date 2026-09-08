---
uid: 039c65
type: identity
status: approved
content_hash: 6f72e20836b3ef5d
source: "Matrix Cookbook §2.1, eq. 46, p. 8"
unit: "matrix-cookbook:2.1:46"
frequency: common
derivation: short
tags: [derivatives, determinant]
verify: false
---

## front
$\frac{\partial \det(\mathbf{Y})}{\partial x}$

## back
$\det(\mathbf{Y})\text{Tr}\left[\mathbf{Y}^{-1}\frac{\partial \mathbf{Y}}{\partial x}\right]$

## conditions
$\mathbf{Y}(x) \in \mathbb{R}^{n \times n}$ invertible; $x \in \mathbb{R}$.

## proof
$\partial\det(\mathbf{Y}) = \det(\mathbf{Y})\text{Tr}(\mathbf{Y}^{-1}\partial\mathbf{Y})$;
dividing through by $\partial x$ is the chain rule for a scalar parameter.

## notes
front already writes the derivative, so it only says the expression is
well-formed.
