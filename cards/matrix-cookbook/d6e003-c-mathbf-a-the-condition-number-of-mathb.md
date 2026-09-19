---
uid: d6e003
type: identity
status: approved
content_hash: 1d8f2401c2777c95
source: "Matrix Cookbook §3.1, eq. 152, p. 18"
unit: "matrix-cookbook:3.1:152"
gist: the condition number as a ratio of singular values
frequency: common
derivation: definitional
tags: [condition-number, singular-values]
verify: false
---

## front
$c(\mathbf{A})$, the condition number of $\mathbf{A}$

## back
$\frac{d_+}{d_-}$, the largest singular value of $\mathbf{A}$ over the smallest

## prose
A large $c(\mathbf{A})$ says $\mathbf{A}$ is near singular: $d_- \to 0$ sends the ratio to infinity.
