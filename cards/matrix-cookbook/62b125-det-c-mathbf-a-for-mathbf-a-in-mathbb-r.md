---
uid: 62b125
type: identity
status: approved
content_hash: 6579aa890994a24a
source: "Matrix Cookbook §1.2, eq. 19, p. 6"
unit: "matrix-cookbook:1.2:19"
gist: scaling a matrix scales its determinant by c to the n
frequency: core
derivation: short
tags: [determinant]
verify: false
---

## front
$\det(c\mathbf{A})$ for $\mathbf{A} \in \mathbb{R}^{n \times n}$

## back
$c^n \det(\mathbf{A})$

## conditions
$c \in \mathbb{R}$.

## prose
The exponent is the dimension of $\mathbf{A}$: scaling by $c$ scales the determinant by $c^n$, not by $c$.
