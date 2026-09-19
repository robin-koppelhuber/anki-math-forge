---
uid: d1f31c
type: identity
status: approved
content_hash: 402c25781668aac9
source: "Matrix Cookbook §1.1, eq. 17, p. 6"
unit: "matrix-cookbook:1.1:17"
gist: an inner product as the trace of an outer product
frequency: common
derivation: short
tags: [trace, vectors]
verify: false
---

## front
$\mathbf{a}^T\mathbf{a}$

## back
$\text{Tr}(\mathbf{a}\mathbf{a}^T)$

## conditions
$\mathbf{a} \in \mathbb{R}^{n}$.

## prose
Over $\mathbb{R}$ this writes $\|\mathbf{a}\|^2$ as a trace; over $\mathbb{C}$ the identity still holds but $\mathbf{a}^T\mathbf{a} = \sum_i a_i^2$ is not the squared norm, which is $\bar{\mathbf{a}}^T\mathbf{a}$ (written $\mathbf{a}^H$).

## uses
The trace trick: $\mathbb{E}[\mathbf{a}^T\mathbf{a}] = \text{Tr}(\mathbb{E}[\mathbf{a}\mathbf{a}^T])$, which turns an expected squared error into a covariance.
