---
uid: b2907c
type: identity
status: approved
content_hash: bba721aa027631f2
source: "Matrix Cookbook §2.4, eq. 73, p. 10"
unit: "matrix-cookbook:2.4:73"
frequency: common
derivation: definitional
tags: [derivatives, single-entry-matrix]
verify: false
---

## front
$\frac{\partial \mathbf{X}}{\partial X_{ij}}$

## back
$\mathbf{J}^{ij}$

## conditions
$\mathbf{X} \in \mathbb{R}^{m \times n}$, every entry varied independently of the others; $\mathbf{J}^{ij} \in \mathbb{R}^{m \times n}$ has a single $1$ at $(i,j)$ and zeros everywhere else (the single-entry matrix).

## prose
A symmetric or otherwise constrained $\mathbf{X}$ has a different derivative, so the independence of the entries is what makes the answer a single entry.
