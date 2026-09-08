---
uid: 6b6d41
type: identity
status: approved
content_hash: d0f1b4cf9becd8b0
source: "Matrix Cookbook §2.4, eq. 80, p. 11"
unit: "matrix-cookbook:2.4:80"
frequency: common
derivation: short
tags: [derivatives, single-entry-matrix]
verify: false
---

## front
$\frac{\partial (\mathbf{X}^T\mathbf{B}\mathbf{X})}{\partial X_{ij}}$

## back
$\mathbf{X}^T\mathbf{B}\mathbf{J}^{ij} + \mathbf{J}^{ji}\mathbf{B}\mathbf{X}$

## conditions

## proof
Product rule with $\partial\mathbf{X}/\partial X_{ij} = \mathbf{J}^{ij}$: the
right factor gives $\mathbf{X}^T\mathbf{B}\mathbf{J}^{ij}$ and the left factor
gives $(\mathbf{J}^{ij})^T\mathbf{B}\mathbf{X}$, which is why the index pair
comes out reversed.

## prose
Here $\mathbf{J}^{ij}$ has a single $1$ at $(i,j)$ and zeros everywhere else (the single-entry matrix).
