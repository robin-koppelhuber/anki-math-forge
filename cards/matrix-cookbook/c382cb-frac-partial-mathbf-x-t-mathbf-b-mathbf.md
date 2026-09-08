---
uid: c382cb
type: identity
status: approved
content_hash: ce860de30245bc9b
source: "Matrix Cookbook §2.4, eq. 81, p. 11"
unit: "matrix-cookbook:2.4:81"
frequency: core
derivation: short
tags: [derivatives, quadratic-forms]
verify: false
---

## front
$\frac{\partial \mathbf{x}^T\mathbf{B}\mathbf{x}}{\partial \mathbf{x}}$

## back
$(\mathbf{B}+\mathbf{B}^T)\mathbf{x}$

## conditions
Denominator layout.

## prose
$(\mathbf{B} + \mathbf{B}^T)\mathbf{x}$ collapses to $2\mathbf{B}\mathbf{x}$ only when $\mathbf{B} = \mathbf{B}^T$.
