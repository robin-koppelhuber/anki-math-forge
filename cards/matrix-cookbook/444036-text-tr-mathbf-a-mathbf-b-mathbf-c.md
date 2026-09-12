---
uid: "444036"
type: identity
status: approved
content_hash: b7e4bd86c8f94b61
source: "Matrix Cookbook §1.1, eq. 16, p. 6"
unit: "matrix-cookbook:1.1:16"
gist: cyclic permutation inside a trace
frequency: core
derivation: short
tags: [trace, cyclic]
verify: false
---

## front
$\text{Tr}(\mathbf{A}\mathbf{B}\mathbf{C})$

## back
$\text{Tr}(\mathbf{B}\mathbf{C}\mathbf{A}) = \text{Tr}(\mathbf{C}\mathbf{A}\mathbf{B})$

## conditions
$\mathbf{A} \in \mathbb{R}^{m \times n}$; $\mathbf{B} \in \mathbb{R}^{n \times p}$; $\mathbf{C} \in \mathbb{R}^{p \times m}$.

## prose
Only cyclic permutations: $\text{Tr}(\mathbf{B}\mathbf{A}\mathbf{C})$ is a different quantity.
