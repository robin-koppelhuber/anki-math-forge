---
uid: a93c3a
type: identity
status: approved
content_hash: 9bf38449bb3c764e
source: "Matrix Cookbook §3.1, eq. 146, p. 17"
unit: "matrix-cookbook:3.1:146"
frequency: common
derivation: definitional
tags: [cofactor, determinant]
verify: false
---

## front
$\text{cof}(\mathbf{A}, i, j)$

## back
$(-1)^{i+j}\det([\mathbf{A}]_{ij})$

## conditions
$\mathbf{A} \in \mathbb{C}^{n \times n}$; $[\mathbf{A}]_{ij}$ is $\mathbf{A}$ with row $i$ and column $j$ deleted.

## prose
The sign $(-1)^{i+j}$ is the checkerboard, positive at $(1,1)$.
