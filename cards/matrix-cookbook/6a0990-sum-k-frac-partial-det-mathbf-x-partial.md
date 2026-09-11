---
uid: 6a0990
type: identity
status: approved
content_hash: 51f5f558b63b9751
source: "Matrix Cookbook §2.1, eq. 47, p. 8"
unit: "matrix-cookbook:2.1:47, matrix-cookbook:2.1:50"
frequency: rare
derivation: short
tags: [derivatives, determinant, index-notation]
verify: false
---

## front
$\sum_k \frac{\partial \det(\mathbf{X})}{\partial X_{ik}} X_{jk}$

## back
$\delta_{ij}\det(\mathbf{X})$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$.

## prose
Here $\delta_{ij}$ is $1$ when $i = j$ and $0$ otherwise (the Kronecker delta), so the right-hand side is $\det(\mathbf{X})\mathbf{I}$ entry by entry.
Both sides are polynomials in the entries of $\mathbf{X}$, so the identity
survives at $\det(\mathbf{X}) = 0$ where the $\mathbf{X}^{-1}$ forms do not.

## uses
Cramer's rule and $\mathbf{X}^{-1} = \text{adj}(\mathbf{X})/\det(\mathbf{X})$, both of which are $\mathbf{X}\,\text{adj}(\mathbf{X}) = \det(\mathbf{X})\mathbf{I}$ written out entrywise.

## proof
$\partial\det(\mathbf{X})/\partial X_{ik}$ is the $(i,k)$ cofactor. Summing it
against row $i$ is Laplace expansion, giving $\det(\mathbf{X})$. Summing it
against row $j \ne i$ is the expansion of the matrix whose row $i$ has been
replaced by row $j$, which has two equal rows and so determinant $0$.

## notes
as eq. 50 in §2.1.2; both units point at this card.
