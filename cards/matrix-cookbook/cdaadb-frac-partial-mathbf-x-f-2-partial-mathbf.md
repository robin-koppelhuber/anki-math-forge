---
uid: cdaadb
type: identity
status: approved
content_hash: dbc84db3896fee34
source: "Matrix Cookbook §2.7, eq. 132, p. 14"
unit: "matrix-cookbook:2.7:132"
gist: the gradient of a squared Frobenius norm
frequency: core
derivation: short
tags: [derivatives, norms, frobenius]
verify: false
---

## front
$\frac{\partial \|\mathbf{X}\|_F^2}{\partial \mathbf{X}}$

## back
$2\mathbf{X}$

## conditions
Denominator layout.

## proof
$\|\mathbf{X}\|_F^2 = \operatorname{Tr}(\mathbf{X}\mathbf{X}^\top) = \sum_{ij}X_{ij}^2$, so $\partial\|\mathbf{X}\|_F^2/\partial X_{ij} = 2X_{ij}$.
