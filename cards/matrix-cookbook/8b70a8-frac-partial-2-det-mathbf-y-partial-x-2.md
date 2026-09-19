---
uid: 8b70a8
type: identity
status: approved
content_hash: 574fcc28725bbf65
source: "Matrix Cookbook §2.1, eq. 48, p. 8"
unit: "matrix-cookbook:2.1:p8y617, matrix-cookbook:2.1:p8y651, matrix-cookbook:2.1:48"
gist: the second derivative of a determinant by a scalar
frequency: rare
derivation: short
tags: [derivatives, determinant]
verify: false
---

## front
$\frac{\partial^2 \det(\mathbf{Y})}{\partial x^2}$

## back
$\det(\mathbf{Y})\left(\text{Tr}\left[\mathbf{Y}^{-1}\frac{\partial^2\mathbf{Y}}{\partial x^2}\right] + \text{Tr}\left[\mathbf{Y}^{-1}\frac{\partial\mathbf{Y}}{\partial x}\right]^2 - \text{Tr}\left[\mathbf{Y}^{-1}\frac{\partial\mathbf{Y}}{\partial x}\mathbf{Y}^{-1}\frac{\partial\mathbf{Y}}{\partial x}\right]\right)$

## conditions
$\mathbf{Y}(x) \in \mathbb{R}^{n \times n}$ invertible; $x \in \mathbb{R}$.

## prose
The squared trace and the trace of the square differ, which is why two terms
that look alike do not cancel.

## proof
Differentiate $\det(\mathbf{Y})\text{Tr}[\mathbf{Y}^{-1}\mathbf{Y}']$ again. The
$\det(\mathbf{Y})$ factor contributes the squared trace,
$\partial(\mathbf{Y}^{-1})/\partial x = -\mathbf{Y}^{-1}\mathbf{Y}'\mathbf{Y}^{-1}$
contributes the last term, and $\mathbf{Y}'$ contributes the first.

## notes
units (p8y617, p8y651, 48). The $+$ joining the first two terms sits at a line
break and is legible only in a crop wide enough to span it; a wide-context crop
of p8y651 shows the whole equation and confirms it.
$\text{Tr}[\mathbf{Y}^{-1}\partial(\partial\mathbf{Y}/\partial x)/\partial x]$,
the second term as two traces multiplied, and the third with each factor
parenthesised.
differentiability added.
`## conditions`: the front already writes the second derivative, so it only
says the expression is well-formed.
