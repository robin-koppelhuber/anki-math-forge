---
uid: 4cedf2
type: identity
status: approved
content_hash: 66db7e7d6cdb7ed7
source: "Matrix Cookbook §3.1, eq. 153, p. 18"
unit: "matrix-cookbook:3.1:153"
gist: the condition number as a product of norms
frequency: common
derivation: definitional
tags: [condition-number, norms]
verify: false
---

## front
$\|\mathbf{A}\| \cdot \|\mathbf{A}^{-1}\|$

## back
$c(\mathbf{A})$, the condition number of $\mathbf{A}$

## conditions
$\mathbf{A} \in \mathbb{C}^{n \times n}$ nonsingular; $\|\cdot\|$ any matrix norm.

## prose
Only in the $2$-norm is this the singular-value ratio $d_+/d_-$; each norm gives its own condition number.
