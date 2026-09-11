---
uid: 835908
type: identity
status: approved
content_hash: 5a700b07b2def7ba
source: "Matrix Cookbook §3.1, eq. 149, p. 17"
unit: "matrix-cookbook:3.1:149"
frequency: common
derivation: definitional
tags: [determinant, cofactor]
verify: false
---

## front
$\det(\mathbf{A})$ expanded along the first row

## back
$\sum_{j=1}^{n}(-1)^{j+1}A_{1j}\det([\mathbf{A}]_{1j})$

## conditions
$\mathbf{A} \in \mathbb{C}^{n \times n}$; $[\mathbf{A}]_{1j}$ is $\mathbf{A}$ with row $1$ and column $j$ deleted.

## prose
Each term is a first-row entry times the signed determinant left when its own row and column go (its cofactor), so the sum is also $\sum_j A_{1j}\,\text{cof}(\mathbf{A}, 1, j)$.
