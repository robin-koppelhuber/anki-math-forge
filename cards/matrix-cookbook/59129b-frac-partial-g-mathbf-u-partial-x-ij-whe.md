---
uid: 59129b
type: identity
status: approved
content_hash: 96a6cc68c0098b2e
source: "Matrix Cookbook §2.8, eqs. 133, 136-137, pp. 14-15"
unit: "matrix-cookbook:2.8:133, matrix-cookbook:2.8:136, matrix-cookbook:2.8:137"
frequency: common
derivation: short
tags: [derivatives, chain-rule]
verify: false
---

## front
$\frac{\partial g(\mathbf{U})}{\partial X_{ij}}$ where $\mathbf{U} = f(\mathbf{X})$

## back
$\text{Tr}\left[\left(\frac{\partial g(\mathbf{U})}{\partial \mathbf{U}}\right)^T \frac{\partial \mathbf{U}}{\partial X_{ij}}\right]$

## conditions
$\mathbf{X} \in \mathbb{R}^{m \times n}$; $f : \mathbb{R}^{m \times n} \to \mathbb{R}^{p \times q}$; $g : \mathbb{R}^{p \times q} \to \mathbb{R}$. Denominator layout.

## prose
Differentiating a structured $\mathbf{A}$ is the case $\mathbf{U} = \mathbf{X} = \mathbf{A}$: the structure lives entirely in $\frac{\partial \mathbf{A}}{\partial A_{ij}}$, which is the single-entry matrix $\mathbf{J}^{ij}$ only when the entries of $\mathbf{A}$ vary independently of one another.

## proof
Summing the scalar chain rule over the entries of $\mathbf{U}$ gives $\sum_{k}\sum_{l}\frac{\partial g(\mathbf{U})}{\partial u_{kl}}\frac{\partial u_{kl}}{\partial x_{ij}}$, and that double sum is the trace of $\left(\frac{\partial g}{\partial \mathbf{U}}\right)^T\frac{\partial \mathbf{U}}{\partial X_{ij}}$.
