---
uid: c49127
type: identity
status: approved
content_hash: 9d93e7f8b97bf863
source: "Matrix Cookbook §3.1, eq. 148, p. 17"
unit: "matrix-cookbook:3.1:148"
gist: the adjugate as the transposed cofactor matrix
frequency: common
derivation: definitional
tags: [cofactor, inverse]
verify: false
---

## front
$\text{adj}(\mathbf{A})$

## back
$(\text{cof}(\mathbf{A}))^T$

## conditions
$\mathbf{A} \in \mathbb{C}^{n \times n}$; $(\text{cof}(\mathbf{A}))_{ij} = (-1)^{i+j}\det([\mathbf{A}]_{ij})$, the signed determinant of $\mathbf{A}$ with row $i$ and column $j$ deleted (its cofactor).

## prose
The transpose is what makes $\mathbf{A}\,\text{adj}(\mathbf{A}) = \det(\mathbf{A})\mathbf{I}$ come out; the untransposed cofactor matrix does not.
