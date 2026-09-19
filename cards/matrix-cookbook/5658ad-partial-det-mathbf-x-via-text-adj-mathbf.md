---
uid: 5658ad
type: identity
status: approved
content_hash: 15d9012ae1619d20
source: "Matrix Cookbook §2, eq. 41, p. 8"
unit: "matrix-cookbook:2:41"
gist: "the differential of a determinant, via the adjugate"
frequency: rare
derivation: short
requires: [a93c3a, c49127]
tags: [derivatives, differential, determinant]
verify: false
---

## front
$\partial(\det(\mathbf{X}))$ via $\text{adj}(\mathbf{X})$

## back
$\text{Tr}(\text{adj}(\mathbf{X})\,\partial\mathbf{X})$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$.

## prose
$\text{adj}(\mathbf{X})$, built from determinants of $\mathbf{X}$ with one row and one column struck out (the transposed cofactor matrix), is defined for
singular $\mathbf{X}$, so the adjugate form holds where
$\det(\mathbf{X})\text{Tr}(\mathbf{X}^{-1}\partial\mathbf{X})$ does not.

## proof
Laplace expansion makes $\partial\det(\mathbf{X})/\partial X_{ij}$ the $(i,j)$
cofactor, which is $(\text{adj}(\mathbf{X}))_{ji}$. Summing
$\sum_{ij}(\text{adj}(\mathbf{X}))_{ji}\,\partial X_{ij}$ is
$\text{Tr}(\text{adj}(\mathbf{X})\,\partial\mathbf{X})$.

## notes
invertibility is not needed, which is what separates this from eq. 42.
