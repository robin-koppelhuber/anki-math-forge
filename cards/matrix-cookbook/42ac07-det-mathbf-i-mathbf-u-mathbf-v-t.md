---
uid: 42ac07
type: identity
status: approved
content_hash: 890a0ae402000bae
source: "Matrix Cookbook §1.2, eq. 24, p. 6"
unit: "matrix-cookbook:1.2:24"
frequency: core
derivation: short
tags: [determinant, rank-one]
verify: false
---

## front
$\det(\mathbf{I} + \mathbf{u}\mathbf{v}^T)$

## back
$1 + \mathbf{u}^T\mathbf{v}$

## conditions
$\mathbf{u}, \mathbf{v} \in \mathbb{R}^{n}$; $\mathbf{I} \in \mathbb{R}^{n \times n}$.

## uses
How a determinant moves under a rank-one update (the matrix determinant lemma); it hits zero exactly where Sherman-Morrison fails.
