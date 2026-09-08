---
uid: "055428"
type: identity
status: approved
content_hash: 19283eb9e5abfc15
source: "Matrix Cookbook §2.2, eq. 59, p. 9"
unit: "matrix-cookbook:2.2:59"
frequency: core
derivation: short
tags: [derivatives, inverse]
verify: false
---

## front
$\frac{\partial \mathbf{Y}^{-1}}{\partial x}$

## back
$-\mathbf{Y}^{-1}\frac{\partial \mathbf{Y}}{\partial x}\mathbf{Y}^{-1}$

## conditions
$\mathbf{Y}(x) \in \mathbb{R}^{n \times n}$ invertible; $x \in \mathbb{R}$.

## proof
Differentiate $\mathbf{Y}\mathbf{Y}^{-1} = \mathbf{I}$:
$\frac{\partial \mathbf{Y}}{\partial x}\mathbf{Y}^{-1} + \mathbf{Y}\frac{\partial \mathbf{Y}^{-1}}{\partial x} = \mathbf{0}$,
then left-multiply by $\mathbf{Y}^{-1}$.

## prose
The matrix analogue of $(1/y)' = -y'/y^2$, with the two factors of $\mathbf{Y}^{-1}$ kept on opposite sides of $\partial\mathbf{Y}/\partial x$ because matrices do not commute.

## notes
front already writes the derivative, so it only says the expression is
well-formed.
