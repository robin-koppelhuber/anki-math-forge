---
uid: d6e003
type: identity
status: approved
content_hash: 8c37b1d8ba76b60c
source: "Matrix Cookbook §3.1, eq. 152, p. 18"
unit: "matrix-cookbook:3.1:152"
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
