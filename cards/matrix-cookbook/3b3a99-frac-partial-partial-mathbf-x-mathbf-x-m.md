---
uid: 3b3a99
type: identity
status: approved
content_hash: 5351fdf23599ee4b
source: "Matrix Cookbook §2.4, eq. 87, p. 11"
unit: "matrix-cookbook:2.4:87"
gist: the weighted least squares gradient in the data
frequency: common
derivation: short
tags: [derivatives, least-squares]
verify: false
---

## front
$\frac{\partial}{\partial \mathbf{x}}(\mathbf{x}-\mathbf{A}\mathbf{s})^T\mathbf{W}(\mathbf{x}-\mathbf{A}\mathbf{s})$

## back
$2\mathbf{W}(\mathbf{x}-\mathbf{A}\mathbf{s})$

## conditions
$\mathbf{W}$ symmetric. Denominator layout.
