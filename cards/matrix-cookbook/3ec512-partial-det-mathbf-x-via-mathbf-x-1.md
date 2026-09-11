---
uid: 3ec512
type: identity
status: approved
content_hash: b83b13114d45067a
source: "Matrix Cookbook §2, eq. 42, p. 8"
unit: "matrix-cookbook:2:42"
frequency: core
derivation: short
requires: [5658ad]
tags: [derivatives, differential, determinant]
verify: false
---

## front
$\partial(\det(\mathbf{X}))$ via $\mathbf{X}^{-1}$

## back
$\det(\mathbf{X})\text{Tr}(\mathbf{X}^{-1}\partial\mathbf{X})$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$ invertible.

## prose
$\text{adj}(\mathbf{X})$ is built from determinants of $\mathbf{X}$ with one row and one column struck out. Substituting $\text{adj}(\mathbf{X}) = \det(\mathbf{X})\mathbf{X}^{-1}$ turns $\text{Tr}(\text{adj}(\mathbf{X})\,\partial\mathbf{X})$ into this form, and that substitution is why this one needs $\mathbf{X}$ invertible while the adjugate one does not.

## proof
Jacobi's formula in adjugate form is $\partial(\det(\mathbf{X})) = \text{Tr}(\text{adj}(\mathbf{X})\,\partial\mathbf{X})$. For invertible $\mathbf{X}$, $\text{adj}(\mathbf{X}) = \det(\mathbf{X})\mathbf{X}^{-1}$. The scalar $\det(\mathbf{X})$ then comes out of the trace.

## notes
